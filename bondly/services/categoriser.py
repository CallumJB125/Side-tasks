"""
Transaction categorisation using SA merchant keyword matching.
Works on raw description strings from bank statement transaction lines.
"""
from __future__ import annotations
from bondly.models.profile import TransactionCategory

# Keys are category, values are lowercase substrings to match against description
_KEYWORD_MAP: list[tuple[TransactionCategory, list[str]]] = [
    # Alcohol — check before groceries (Tops at Spar, Checkers Liquor, etc.)
    (TransactionCategory.ALCOHOL, [
        "liquor", "bottle store", "checkers liquor", "ultra liquors",
        "tops at spar", "tops-at-spar", "norman goodfellows", "makro liquor",
        "woolworths wine", "pick n pay liquor", "wine cellar", "craft beer",
        "breweries", "shebeen", "bar tab", "pubcrawl",
    ]),
    # Gambling
    (TransactionCategory.GAMBLING, [
        "hollywoodbets", "betway", "supabets", "sunbet", "bankbet",
        "sportingbet", "bet365", "casino", "gold circle", "phumelela",
        "lucky numbers", "jackpot", "bookmaker", "tab payment", "lotto",
        "powerball",
    ]),
    # Fast food / dining — before groceries so KFC doesn't match "food lovers"
    (TransactionCategory.FOOD_DINING, [
        "mcdonalds", "mcdonald", "kfc", "steers", "nandos", "nando's",
        "pizza hut", "pizza", "burger king", "fishaways", "hungry lion",
        "wimpy", "roman's pizza", "debonairs", "panarottis", "spur",
        "ocean basket", "john dory's", "tashas", "seattle coffee",
        "starbucks", "coffee shop", "cafe", "restaurant", "diner",
        "uber eats", "mr delivery", "dineplan", "checkers sixty60",
    ]),
    # Groceries
    (TransactionCategory.GROCERIES, [
        "checkers", "pick n pay", "woolworths food", "shoprite", "spar",
        "food lovers", "makro", "ok foods", "superspar", "freshstop",
        "game stores",
    ]),
    # Fuel
    (TransactionCategory.FUEL, [
        "engen", "caltex", "sasol", "shell", "bp ", " bp\t", "astron",
        "total petroleum", "exaro", "petrol", "diesel", "fuel ",
    ]),
    # Transport (after fuel so Uber doesn't match Uber Eats — Uber Eats is food_dining)
    (TransactionCategory.TRANSPORT, [
        "uber*trip", "uber trip", "bolt ", "taxify", "gautrain",
        "myciti", "prasa", "metrobus", "intercape", "greyhound",
        "flixbus", "e-toll", "sanral toll", "parking meter", "parkade",
    ]),
    # Insurance
    (TransactionCategory.INSURANCE, [
        "discovery insure", "momentum insure", "liberty life", "old mutual",
        "sanlam", "outsurance", "santam", "miway", "king price",
        "budget insurance", "dial direct", "hollard", "metropolitan life",
        "medshield", "bonitas", "gems medical", "bestmed", "profmed",
        "discovery health", "momentum health",
    ]),
    # Medical
    (TransactionCategory.MEDICAL, [
        "clicks", "dischem", "pharmacy", "medicross", "netcare",
        "mediclinic", "life healthcare", "intercare", "akeso",
        "dental", "optometrist", "dr ", "doctor", "physiotherapy",
        "pathcare", "lancet", "ampath",
    ]),
    # Education
    (TransactionCategory.EDUCATION, [
        "school fees", "university", "tuition", "varsity", "college",
        "unisa", "wits", "uct", "ukzn", "nwu", "udemy", "coursera",
        "skillshare", "edx", "nsfas", "bursary",
    ]),
    # Subscriptions / streaming
    (TransactionCategory.SUBSCRIPTIONS, [
        "netflix", "showmax", "dstv", "multichoice", "spotify",
        "apple.com", "apple music", "google play", "amazon prime",
        "microsoft 365", "adobe", "dropbox", "icloud", "youtube premium",
        "disney+", "disney plus", "hbo", "norton", "kaspersky",
        "1password", "antivirus",
    ]),
    # Clothing
    (TransactionCategory.CLOTHING, [
        "mr price", "truworths", "foschini", "edgars", "jet stores",
        "pep stores", "ackermans", "cotton on", "h&m", "zara",
        "nike", "adidas", "sportscene", "totalsports", "woolworths clothing",
    ]),
    # Savings / investments
    (TransactionCategory.SAVINGS, [
        "fixed deposit", "notice deposit", "easy equities", "satrix",
        "sygnia", "etf purchase", "retirement annuity", "ra contribution",
        "old mutual invest", "discovery invest", "nedgroup invest",
        "stanlib", "coronation", "10x invest", "outvest",
    ]),
    # Housing (rates, levies)
    (TransactionCategory.HOUSING, [
        " rates ", "municipal rates", "levy ", "levies", "homeowners assoc",
        "body corporate", "sectional levy", "hoa ",
    ]),
    # Bond repayment
    (TransactionCategory.BOND_REPAYMENT, [
        "bond repayment", "home loan", "homeloan", "mortgage repayment",
        "bond instalment", "bond payment",
    ]),
    # Bank fees
    (TransactionCategory.FEES, [
        "service fee", "monthly fee", "account fee", "bank charge",
        "atm fee", "overdraft fee", "interest charge", "admin fee",
        "maintenance fee", "card fee", "transaction fee",
    ]),
]

_INCOME_KEYWORDS = [
    "salary", "payroll", "wages", "commission", "bonus", "remuneration",
    "net pay", "nett pay", "employer ", "from payroll", "payslip",
    "from employer", "salaris",
]


def categorise(description: str, amount: float) -> tuple[TransactionCategory, bool]:
    """
    Returns (category, is_income).
    amount: positive = credit (income), negative = debit (expense).
    """
    desc_lower = description.lower()

    # Income: salary/wages credits first
    if amount > 0:
        for kw in _INCOME_KEYWORDS:
            if kw in desc_lower:
                return TransactionCategory.INCOME, True
        # Large unqualified credit likely salary
        if amount >= 5000:
            return TransactionCategory.INCOME, True

    # Expense categorisation
    for category, keywords in _KEYWORD_MAP:
        for kw in keywords:
            if kw in desc_lower:
                return category, False

    # Peer / internal transfers
    if amount > 0 and any(k in desc_lower for k in ["transfer from", "payment from", "received from"]):
        return TransactionCategory.TRANSFERS, False
    if amount < 0 and any(k in desc_lower for k in ["transfer to", "payment to", "sent to", "eft to"]):
        return TransactionCategory.TRANSFERS, False

    return TransactionCategory.OTHER, False
