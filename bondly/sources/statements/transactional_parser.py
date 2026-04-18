"""
Parse transactional (current/cheque account) bank statement PDFs.

Unlike the home-loan statement parsers that extract bond metrics, this parser
extracts individual transaction lines, detects income, and categorises spend.
The output feeds the affordability calculator and behaviour tracker.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz

from bondly.models.profile import (
    CustomerProfile,
    ExpenseBreakdown,
    Transaction,
    TransactionCategory,
)
from bondly.services.categoriser import categorise

# ---------------------------------------------------------------------------
# Date pattern matching — SA bank statements use several formats
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    r"\d{2}\s+[A-Za-z]{3}\s+\d{4}",   # 01 Jan 2024
    r"\d{4}-\d{2}-\d{2}",              # 2024-01-01
    r"\d{2}/\d{2}/\d{4}",              # 01/01/2024
    r"\d{2}-\d{2}-\d{4}",              # 01-01-2024
    r"\d{2}\s+[A-Za-z]{3}",            # 01 Jan  (no year — common in running tables)
]
_DATE_RE = re.compile(r"^(?:" + "|".join(_DATE_PATTERNS) + r")")

# Matches a ZAR amount: optional R, digits with spaces/commas, decimal
_AMOUNT_RE = re.compile(r"-?\s*R?\s*([\d][\d\s,]*\.?\d{0,2})")


def _parse_float(raw: str) -> float | None:
    clean = re.sub(r"[R\s,]", "", raw)
    try:
        return float(clean)
    except ValueError:
        return None


def _detect_bank(text: str) -> str | None:
    checks = {
        "ABSA": ["absa bank", "absa limited"],
        "FNB": ["first national bank", "firstrand bank", " fnb "],
        "Nedbank": ["nedbank"],
        "Standard Bank": ["standard bank"],
        "Capitec": ["capitec bank"],
    }
    lower = text.lower()
    for bank, keywords in checks.items():
        if any(k in lower for k in keywords):
            return bank
    return None


def _extract_period(text: str) -> str | None:
    # "Statement period: 01/01/2024 - 31/01/2024"
    m = re.search(
        r"(?:statement\s+(?:date|period)|period)[:\s]+([^\n]{5,50})",
        text, re.I,
    )
    if m:
        return m.group(1).strip()
    # Bare date range
    m = re.search(
        r"(\d{2}[/\-]\d{2}[/\-]\d{4})\s*[-\u2013to]+\s*(\d{2}[/\-]\d{2}[/\-]\d{4})",
        text,
    )
    if m:
        return f"{m.group(1)} \u2013 {m.group(2)}"
    return None


def _period_key(period_str: str | None) -> str:
    """Best-effort 'YYYY-MM' extraction from a period description string."""
    if not period_str:
        return "unknown"
    # "2024-01-01 – 2024-01-31" — take the first date
    m = re.search(r"(\d{4})-(\d{2})", period_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    # "01/01/2024"
    m = re.search(r"(\d{2})[/\-](\d{4})", period_str)
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}"
    # At least a year
    m = re.search(r"(\d{4})", period_str)
    if m:
        return m.group(1)
    return "unknown"


# ---------------------------------------------------------------------------
# Transaction extraction
# ---------------------------------------------------------------------------

def _extract_transactions(text: str) -> list[Transaction]:
    """
    Heuristic line-by-line parser.

    A transaction line starts with a date and contains at least one ZAR amount.
    The rightmost amount on the line is treated as the running balance and skipped;
    the second-rightmost is the transaction amount.

    For lines where the description wraps to the next line, we peek at the next
    line and merge it if it contains no date.
    """
    lines = [ln.rstrip() for ln in text.split("\n")]
    transactions: list[Transaction] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        date_m = _DATE_RE.match(line.strip())
        if not date_m:
            i += 1
            continue

        date_str = date_m.group(0)
        body = line.strip()[len(date_str):].strip()

        # Peek at next line — merge if it has no date and has content
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and not _DATE_RE.match(nxt) and len(nxt) < 80:
                body = body + " " + nxt
                i += 1  # consume the continuation line

        # Find all amounts in body
        amounts_raw = re.findall(r"-?\s*R?\s*([\d][\d\s,]+\.\d{2})", body)
        if not amounts_raw:
            i += 1
            continue

        # Parse floats; skip if only one (likely just a balance)
        amounts = [_parse_float(a) for a in amounts_raw if _parse_float(a) is not None]
        if not amounts:
            i += 1
            continue

        # The last amount is usually the running balance — skip it
        # The transaction amount is the second-to-last (or only, if just one)
        txn_amount = amounts[-2] if len(amounts) >= 2 else amounts[-1]

        # Detect debit: negative sign or "(debit)" pattern
        raw_body = body
        is_debit = bool(re.search(r"-\s*R?\s*[\d]", raw_body))
        if is_debit and txn_amount > 0:
            txn_amount = -txn_amount

        # Description: everything before the first amount
        desc_end = re.search(r"\s+-?\s*R?\s*[\d][\d\s,]*\.\d{2}", body)
        description = body[:desc_end.start()].strip() if desc_end else body.strip()
        description = re.sub(r"\s{2,}", " ", description)

        if not description:
            i += 1
            continue

        category, is_income = categorise(description, txn_amount)

        transactions.append(Transaction(
            date=date_str,
            description=description,
            amount=round(txn_amount, 2),
            category=category,
            is_income=is_income,
            raw_description=line.strip(),
        ))

        i += 1

    return transactions


# ---------------------------------------------------------------------------
# Breakdown aggregation
# ---------------------------------------------------------------------------

def _build_breakdown(transactions: list[Transaction]) -> ExpenseBreakdown:
    total_income = 0.0
    total_expenses = 0.0
    by_category: dict[str, float] = {}
    count: dict[str, int] = {}
    salary_credits: list[float] = []

    for t in transactions:
        cat = t.category.value
        if t.amount > 0:
            total_income += t.amount
            if t.is_income:
                salary_credits.append(t.amount)
        else:
            spend = abs(t.amount)
            total_expenses += spend
            by_category[cat] = by_category.get(cat, 0.0) + spend
            count[cat] = count.get(cat, 0) + 1

    largest = sorted(
        [t for t in transactions if t.amount < 0],
        key=lambda t: t.amount,
    )[:5]

    return ExpenseBreakdown(
        total_income=round(total_income, 2),
        total_expenses=round(total_expenses, 2),
        net_cash_flow=round(total_income - total_expenses, 2),
        by_category={k: round(v, 2) for k, v in by_category.items()},
        transaction_count=count,
        salary_credits=salary_credits,
        largest_expenses=[
            {
                "date": t.date,
                "description": t.description,
                "amount": round(abs(t.amount), 2),
                "category": t.category.value,
            }
            for t in largest
        ],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_transactional_statement(pdf_path: str | Path, user_id: int) -> CustomerProfile:
    """
    Parse a current/cheque account bank statement PDF.
    Returns a CustomerProfile with categorised transactions and expense breakdown.
    The PDF is read-only and never stored by this function.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Statement not found: {path}")

    pages: list[str] = []
    with fitz.open(str(path)) as pdf:
        for page in pdf:
            pages.append(page.get_text() or "")

    full_text = "\n".join(pages)

    bank = _detect_bank(full_text)
    period_str = _extract_period(full_text)
    transactions = _extract_transactions(full_text)
    breakdown = _build_breakdown(transactions)

    # Gross income: prefer detected salary credits; fall back to all positive flows
    gross = sum(breakdown.salary_credits) if breakdown.salary_credits else breakdown.total_income

    # Confidence: fraction of transactions that got a specific category
    n = len(transactions)
    categorised = sum(1 for t in transactions if t.category != TransactionCategory.OTHER)
    confidence = round((categorised / n if n else 0.0) + (0.2 if gross > 0 else 0.0), 2)
    confidence = min(1.0, confidence)

    income_sources = list({t.description for t in transactions if t.is_income})[:5]

    return CustomerProfile(
        user_id=user_id,
        period=_period_key(period_str),
        statement_period=period_str,
        gross_monthly_income=round(gross, 2),
        net_monthly_income=round(breakdown.net_cash_flow + breakdown.total_expenses, 2),
        income_sources=income_sources,
        expense_breakdown=breakdown,
        transactions=transactions,
        bank_detected=bank,
        parse_confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
