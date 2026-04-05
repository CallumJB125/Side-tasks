"""
Absa home loan statement parser.

Absa statements use labels like:
  "Outstanding Balance"         R 1 450 231.55
  "Current Interest Rate"       11.75% per annum
  "Monthly Instalment"          R 18 240.00
  "Arrears"                     R 0.00
  "Home Loan Account Number"    4048XXXXXXXX
"""
import re
from bondly.models.property import PaymentRecord, StatementData
from bondly.sources.statements.utils import clean_amount as _clean_amount, extract_amount as _extract_amount, extract_rate as _extract_rate


def parse(full_text: str, first_page: str) -> StatementData:
    data = StatementData(bank="Absa Bank")

    # Account number — Absa home loan accounts start with 4
    m = re.search(r"(?:home\s+loan\s+account|account\s+number)[:\s]+(\d[\d\s]{7,15})", full_text, re.I)
    if m:
        data.account_number = m.group(1).replace(" ", "")

    m = re.search(r"(?:dear\s+(?:mr\.?|ms\.?|mrs\.?)\s+|client[:\s]+)([A-Z][A-Z\s]{2,40})", full_text, re.I)
    if m:
        data.account_holder = m.group(1).strip().title()

    m = re.search(r"Statement\s+Date[:\s]+(\d{1,2}\s+\w+\s+\d{4})", full_text, re.I)
    if m:
        data.statement_date = m.group(1)

    data.outstanding_balance = _extract_amount(
        r"Outstanding\s+Balance[:\s]+R?\s*([\d\s,]+\.?\d{0,2})", full_text
    )
    data.original_loan_amount = _extract_amount(
        r"(?:Original|Initial)\s+Loan\s+Amount[:\s]+R?\s*([\d\s,]+\.?\d{0,2})", full_text
    )
    data.current_interest_rate = _extract_rate(
        full_text,
        r"(?:Current\s+Interest\s+Rate|Interest\s+Rate)[:\s]+([\d.]+\s*%)",
        r"Prime\s*(?:rate)?\s*[+\-]\s*[\d.]+%?\s*=\s*([\d.]+)%",
    )
    data.monthly_repayment = _extract_amount(
        r"Monthly\s+Instalment[:\s]+R?\s*([\d\s,]+\.?\d{0,2})", full_text
    )
    data.arrears_amount = _extract_amount(
        r"Arrears[:\s]+R?\s*([\d\s,]+\.?\d{0,2})", full_text
    )

    m = re.search(r"Next\s+(?:Payment|Debit)\s+Date[:\s]+(\d{1,2}\s+\w+\s+\d{4})", full_text, re.I)
    if m:
        data.next_payment_date = m.group(1)

    m = re.search(r"Remaining\s+Term[:\s]+(\d+)\s*months?", full_text, re.I)
    if m:
        data.remaining_term_months = int(m.group(1))

    data.service_fee = _extract_amount(
        r"(?:Service|Administration|Admin)\s+Fee[:\s]+R?\s*([\d\s,]+\.?\d{0,2})", full_text
    )

    rows = []
    for m in re.finditer(
        r"(\d{2}\s+\w{3}\s+\d{4})\s+([\w\s/-]{5,50}?)\s{2,}([\d\s,]+\.\d{2})\s+([\d\s,]+\.\d{2})?",
        full_text,
    ):
        rows.append(PaymentRecord(
            date=m.group(1),
            description=m.group(2).strip(),
            amount=_clean_amount(m.group(3)),
            balance_after=_clean_amount(m.group(4)) if m.group(4) else None,
        ))
    data.payment_history = rows[:24]

    return data
