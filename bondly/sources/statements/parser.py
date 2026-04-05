"""
Bank statement PDF parser.

Detects which SA bank the statement is from and runs the appropriate parser.
Falls back to a generic parser if the bank cannot be identified.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # pymupdf

from bondly.models.property import PaymentRecord, StatementData
from bondly.sources.statements.utils import clean_amount as _clean_amount, extract_amount as _extract_amount, extract_rate as _extract_rate
from bondly.sources.statements.banks import absa, fnb, nedbank, standardbank, capitec

# Map of bank name keywords → parser module
_BANK_PARSERS = {
    "absa": absa,
    "firstrand": fnb,
    "fnb": fnb,
    "first national": fnb,
    "nedbank": nedbank,
    "standard bank": standardbank,
    "standardbank": standardbank,
    "capitec": capitec,
}


def _detect_bank(text: str) -> str | None:
    lower = text.lower()
    for keyword in _BANK_PARSERS:
        if keyword in lower:
            return keyword
    return None


def _clean_amount(s: str) -> str:
    """Normalise ZAR amount string — ensure it starts with R."""
    s = s.strip()
    if s and not s.startswith("R"):
        s = "R " + s
    return s


def _extract_amount(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return _clean_amount(m.group(1).strip())
    return None


def _extract_rate(text: str, *patterns: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip() + "%" if not m.group(1).strip().endswith("%") else m.group(1).strip()
    return None


def parse_statement(pdf_path: str | Path) -> StatementData:
    """
    Parse a SA bank home loan statement PDF.
    Returns a StatementData object with all extractable fields populated.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Statement file not found: {path}")

    pages_text: list[str] = []
    with fitz.open(str(path)) as pdf:
        for page in pdf:
            t = page.get_text() or ""
            pages_text.append(t)

    full_text = "\n".join(pages_text)
    first_page = pages_text[0] if pages_text else ""

    # Detect bank
    bank_key = _detect_bank(full_text)
    parser_mod = _BANK_PARSERS.get(bank_key) if bank_key else None

    if parser_mod:
        return parser_mod.parse(full_text, first_page)

    # Generic fallback
    return _generic_parse(full_text, first_page)


def _generic_parse(full_text: str, first_page: str) -> StatementData:
    """
    Generic parser using common South African home loan statement patterns.
    Works across most banks with reasonable accuracy.
    """
    data = StatementData(bank="Unknown (generic parser)")

    # Account number
    m = re.search(r"(?:account\s+(?:number|no\.?|#))[:\s]+([0-9\s\-]{8,20})", full_text, re.I)
    if m:
        data.account_number = m.group(1).strip().replace(" ", "")

    # Account holder
    m = re.search(r"(?:account\s+holder|client\s+name|dear\s+mr\.?|dear\s+ms\.?)[:\s]+([A-Z][A-Z\s]+)", full_text, re.I)
    if m:
        data.account_holder = m.group(1).strip().title()

    # Statement date
    m = re.search(r"(?:statement\s+date|date\s+of\s+statement)[:\s]+(\d{1,2}[\s/\-]\w+[\s/\-]\d{4})", full_text, re.I)
    if m:
        data.statement_date = m.group(1).strip()

    # Outstanding balance — many label variants
    data.outstanding_balance = _extract_amount(
        r"(?:outstanding\s+balance|current\s+balance|balance\s+outstanding|loan\s+balance|amount\s+outstanding)"
        r"[:\s]+R?\s*([\d\s,]+\.?\d{0,2})",
        full_text,
    )

    # Original loan amount
    data.original_loan_amount = _extract_amount(
        r"(?:original\s+(?:loan|bond)\s+amount|loan\s+amount|bond\s+amount|principal\s+amount)"
        r"[:\s]+R?\s*([\d\s,]+\.?\d{0,2})",
        full_text,
    )

    # Interest rate
    data.current_interest_rate = _extract_rate(
        full_text,
        r"(?:interest\s+rate|current\s+rate|applicable\s+rate)[:\s]+([\d.]+\s*%)",
        r"(?:prime\s*[+\-]\s*[\d.]+%?)[^\n]*?([\d.]+%)",
        r"rate[:\s]+([\d.]+)\s*%\s*(?:per\s+annum|p\.?a\.?)",
    )

    # Monthly repayment
    data.monthly_repayment = _extract_amount(
        r"(?:monthly\s+(?:instalment|repayment|payment)|instalment\s+amount|repayment\s+amount)"
        r"[:\s]+R?\s*([\d\s,]+\.?\d{0,2})",
        full_text,
    )

    # Next payment date
    m = re.search(
        r"(?:next\s+payment|payment\s+due|due\s+date)[:\s]+(\d{1,2}[\s/\-]\w+[\s/\-]\d{4})",
        full_text, re.I,
    )
    if m:
        data.next_payment_date = m.group(1).strip()

    # Arrears
    data.arrears_amount = _extract_amount(
        r"(?:arrears|overdue\s+amount|amount\s+in\s+arrears)[:\s]+R?\s*([\d\s,]+\.?\d{0,2})",
        full_text,
    )

    # Last payment
    m = re.search(
        r"(?:last\s+payment|previous\s+payment)[:\s]+.*?R?\s*([\d\s,]+\.?\d{0,2})",
        full_text, re.I,
    )
    if m:
        data.last_payment_amount = _clean_amount(m.group(1).strip())

    # Remaining term
    m = re.search(r"(?:remaining\s+term|term\s+remaining)[:\s]+(\d+)\s*(?:months?|mths?)", full_text, re.I)
    if m:
        data.remaining_term_months = int(m.group(1))

    # Service fee
    data.service_fee = _extract_amount(
        r"(?:service\s+fee|monthly\s+fee|admin\s+fee)[:\s]+R?\s*([\d\s,]+\.?\d{0,2})",
        full_text,
    )

    # Payment history rows: date + description + amount
    payment_rows: list[PaymentRecord] = []
    for m in re.finditer(
        r"(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{4})\s+([A-Za-z][\w\s]{3,50}?)\s+R?\s*([\d\s,]+\.\d{2})",
        full_text,
    ):
        payment_rows.append(PaymentRecord(
            date=m.group(1).strip(),
            description=m.group(2).strip(),
            amount=_clean_amount(m.group(3).strip()),
        ))
    data.payment_history = payment_rows[:24]  # cap at 24 months

    return data
