"""
Bank statement PDF parser.

Detects which SA bank the statement is from and runs the appropriate parser.
Falls back to a generic parser if the bank cannot be identified.

Key improvements over naive regex:
- extract_amount_near_label() handles label and value on separate lines
- normalise_amount() handles all SA amount formats (R 1 234.56 / R1,234.56 / 1234.56)
- extract_prime_linkage() captures "Prime + 0.25%" alongside the effective rate
- parse_confidence score reflects how many key fields were found
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # pymupdf

from bondly.models.property import PaymentRecord, StatementData
from bondly.sources.statements.utils import (
    clean_amount,
    extract_amount_near_label,
    extract_prime_linkage,
    extract_rate,
    normalise_amount,
)
from bondly.sources.statements.banks import absa, fnb, nedbank, standardbank, capitec

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

_KEY_FIELDS = [
    "account_number",
    "outstanding_balance",
    "current_interest_rate",
    "monthly_repayment",
    "arrears_amount",
    "next_payment_date",
]


def _detect_bank(text: str) -> str | None:
    lower = text.lower()
    for keyword in _BANK_PARSERS:
        if keyword in lower:
            return keyword
    return None


def _score_confidence(data: StatementData) -> StatementData:
    """
    Calculate what fraction of key fields were successfully extracted
    and list which ones are missing.
    """
    missing = [f for f in _KEY_FIELDS if not getattr(data, f)]
    found = len(_KEY_FIELDS) - len(missing)
    data.parse_confidence = round(found / len(_KEY_FIELDS), 2)
    data.missing_fields = missing
    return data


def parse_statement(pdf_path: str | Path) -> StatementData:
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

    bank_key = _detect_bank(full_text)
    parser_mod = _BANK_PARSERS.get(bank_key) if bank_key else None

    data = parser_mod.parse(full_text, first_page) if parser_mod else _generic_parse(full_text, first_page)
    return _score_confidence(data)


def _generic_parse(full_text: str, first_page: str) -> StatementData:
    """
    Generic parser using near-label extraction and common SA patterns.
    Handles both same-line and next-line label/value layouts.
    """
    data = StatementData(bank="Unknown (generic parser)")

    # Account number
    m = re.search(r"(?:account\s+(?:number|no\.?|#))[:\s]+([0-9\s\-]{8,20})", full_text, re.I)
    if m:
        data.account_number = re.sub(r"[\s\-]", "", m.group(1))

    # Account holder
    m = re.search(r"(?:account\s+holder|client\s+name|dear\s+(?:mr|ms|mrs)\.?\s+)([A-Z][A-Z\s]{2,40})", full_text, re.I)
    if m:
        data.account_holder = m.group(1).strip().title()

    # Statement date
    m = re.search(r"(?:statement\s+date|date\s+of\s+statement)[:\s]+(\d{1,2}[\s/\-]\w+[\s/\-]\d{4})", full_text, re.I)
    if m:
        data.statement_date = m.group(1).strip()

    # Outstanding balance — try near-label first, then inline
    data.outstanding_balance = (
        extract_amount_near_label(
            r"outstanding\s+balance|balance\s+outstanding|current\s+balance|loan\s+balance|amount\s+outstanding",
            full_text,
        )
    )

    # Original loan amount
    data.original_loan_amount = extract_amount_near_label(
        r"original\s+(?:loan|bond)\s+amount|loan\s+amount|bond\s+amount|principal\s+amount",
        full_text,
    )

    # Interest rate + prime linkage
    prime_link, effective_rate = extract_prime_linkage(full_text)
    data.prime_linkage = prime_link
    data.current_interest_rate = effective_rate or extract_rate(
        full_text,
        r"(?:interest\s+rate|current\s+rate|applicable\s+rate)[:\s]+([\d.]+\s*%)",
        r"rate[:\s]+([\d.]+)\s*%\s*(?:per\s+annum|p\.?a\.?)",
    )

    # Monthly repayment
    data.monthly_repayment = extract_amount_near_label(
        r"monthly\s+(?:instalment|repayment|payment)|instalment\s+amount|repayment\s+amount",
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
    data.arrears_amount = extract_amount_near_label(
        r"arrears|overdue\s+amount|amount\s+in\s+arrears",
        full_text,
    )

    # Last payment
    m = re.search(r"(?:last|previous)\s+payment[^\n]{0,60}R?\s*([\d\s,]+\.\d{2})", full_text, re.I)
    if m:
        data.last_payment_amount = normalise_amount(m.group(1))

    # Remaining term
    m = re.search(r"(?:remaining\s+term|term\s+remaining)[:\s]+(\d+)\s*(?:months?|mths?)", full_text, re.I)
    if m:
        data.remaining_term_months = int(m.group(1))

    # Service fee
    data.service_fee = extract_amount_near_label(
        r"service\s+fee|monthly\s+fee|admin(?:istration)?\s+fee",
        full_text,
    )

    # Payment history
    rows: list[PaymentRecord] = []
    for m in re.finditer(
        r"(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{4}|\d{4}-\d{2}-\d{2})"
        r"\s+([\w][\w\s/-]{3,50}?)\s{2,}"
        r"(-?R?\s*[\d\s,]+\.\d{2})"
        r"(?:\s+(-?R?\s*[\d\s,]+\.\d{2}))?",
        full_text,
    ):
        rows.append(PaymentRecord(
            date=m.group(1).strip(),
            description=m.group(2).strip(),
            amount=normalise_amount(m.group(3)),
            balance_after=normalise_amount(m.group(4)) if m.group(4) else None,
        ))
    data.payment_history = rows[:24]

    return data
