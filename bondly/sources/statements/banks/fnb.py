"""
FNB (First National Bank) home loan statement parser.

FNB statements use labels like:
  "Current Balance"             R 2 184 500.00
  "Home Loan Rate"              11.25% per annum  (Prime + 0.25%)
  "Monthly Repayment"           R 24 150.00
  "Arrears"                     R 0.00
  "Account Number"              62XXXXXXXXXX
"""
import re
from bondly.models.property import PaymentRecord, StatementData
from bondly.sources.statements.utils import (
    normalise_amount,
    extract_amount_near_label,
    extract_prime_linkage,
    extract_rate,
)


def parse(full_text: str, first_page: str) -> StatementData:
    data = StatementData(bank="FNB (First National Bank)")

    m = re.search(r"(?:Account\s+Number|Acc\s+No\.?)[:\s]+(\d[\d\s]{7,15})", full_text, re.I)
    if m:
        data.account_number = re.sub(r"\s", "", m.group(1))

    m = re.search(r"(?:Account\s+Holder|Name)[:\s]+([A-Z][A-Z\s]{2,40})\n", full_text, re.I)
    if m:
        data.account_holder = m.group(1).strip().title()

    m = re.search(r"(?:Statement|Closing)\s+Date[:\s]+(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}\s+\w+\s+\d{4})", full_text, re.I)
    if m:
        data.statement_date = m.group(1)

    m = re.search(r"Statement\s+Period[:\s]+(.+?)(?:\n|$)", full_text, re.I)
    if m:
        data.statement_period = m.group(1).strip()

    data.outstanding_balance = extract_amount_near_label(
        r"(?:Current|Outstanding|Closing)\s+Balance", full_text
    )
    data.original_loan_amount = extract_amount_near_label(
        r"(?:Loan|Original|Approved)\s+Amount", full_text
    )

    prime_link, effective_rate = extract_prime_linkage(full_text)
    data.prime_linkage = prime_link
    data.current_interest_rate = effective_rate or extract_rate(
        full_text,
        r"(?:Home\s+Loan\s+Rate|Interest\s+Rate|Applicable\s+Rate)[:\s]+([\d.]+\s*%)",
        r"(?:rate|interest)[^\n]{0,30}?([\d.]+)%\s*(?:per\s+annum|p\.a\.)",
    )

    data.monthly_repayment = extract_amount_near_label(
        r"(?:Monthly\s+)?Repayment", full_text
    )
    data.arrears_amount = extract_amount_near_label(r"Arrears", full_text)

    m = re.search(r"(?:Payment|Debit)\s+Due\s+Date[:\s]+(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})", full_text, re.I)
    if m:
        data.next_payment_date = m.group(1)

    m = re.search(r"(?:Remaining\s+)?Term[:\s]+(\d+)\s*months?", full_text, re.I)
    if m:
        data.remaining_term_months = int(m.group(1))

    data.service_fee = extract_amount_near_label(r"(?:Monthly\s+)?Service\s+Fee", full_text)

    rows = []
    for m in re.finditer(
        r"(\d{2}\s+\w{3}\s+\d{4}|\d{4}-\d{2}-\d{2})\s+([\w\s/-]{5,50}?)\s{2,}"
        r"(-?R?\s*[\d\s,]+\.\d{2})(?:\s+(-?R?\s*[\d\s,]+\.\d{2}))?",
        full_text,
    ):
        rows.append(PaymentRecord(
            date=m.group(1),
            description=m.group(2).strip(),
            amount=normalise_amount(m.group(3)),
            balance_after=normalise_amount(m.group(4)) if m.group(4) else None,
        ))
    data.payment_history = rows[:24]

    return data
