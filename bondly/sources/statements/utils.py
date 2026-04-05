"""Shared helper functions for bank statement parsers."""
import re


def clean_amount(s: str) -> str:
    """Normalise ZAR amount string — ensure it starts with R."""
    s = s.strip()
    if s and not s.startswith("R"):
        s = "R " + s
    return s


def extract_amount(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return clean_amount(m.group(1).strip())
    return None


def extract_rate(text: str, *patterns: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            return val if val.endswith("%") else val + "%"
    return None
