"""Shared helper functions for bank statement parsers."""
from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# Amount normalisation
# ---------------------------------------------------------------------------

# Matches all SA bank amount formats:
#   R 1 450 231.55   (spaces as thousands separator)
#   R1,450,231.55    (commas as thousands separator)
#   R1450231.55      (no separator)
#   1 450 231.55     (no R prefix)
#   1,450,231.55
_AMOUNT_CORE = r"R?\s*(\d[\d\s,]*\.?\d{0,2})"


def normalise_amount(raw: str) -> str:
    """
    Normalise any SA ZAR amount string to canonical form: 'R 1 450 231.55'
    Handles: spaces, commas, or no thousands separator; optional R prefix.
    """
    raw = raw.strip()
    # Strip existing R prefix
    without_r = re.sub(r"^R\s*", "", raw).strip()
    # Remove thousands separators (spaces and commas)
    digits = re.sub(r"[\s,](?=\d{3}(?:[.,\s]|$))", "", without_r)
    # Ensure decimal point (not comma) and two decimal places
    digits = digits.replace(",", ".")
    if "." not in digits:
        digits += ".00"
    try:
        value = float(digits)
        # Format as 'R 1 450 231.55'
        integer_part = f"{int(value):,}".replace(",", " ")
        decimal_part = f"{value:.2f}".split(".")[1]
        return f"R {integer_part}.{decimal_part}"
    except ValueError:
        return f"R {raw}" if not raw.startswith("R") else raw


def clean_amount(s: str) -> str:
    """Lightweight clean — just ensures R prefix. Used by parsers for raw regex matches."""
    s = s.strip()
    if s and not s.startswith("R"):
        s = "R " + s
    return s


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_amount(pattern: str, text: str) -> str | None:
    """
    Search for pattern in text and return normalised ZAR amount.
    The pattern must have one capture group containing the numeric value.
    Handles label-on-one-line, value-on-next-line layout:
      e.g. 'Outstanding Balance\\n                R 1 450 231.55'
    """
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return normalise_amount(m.group(1).strip())
    return None


def extract_amount_near_label(label_pattern: str, text: str, window: int = 120) -> str | None:
    """
    Find a label in text and look for a ZAR amount within `window` characters after it.
    Handles cases where label and value are on separate lines.
    """
    m = re.search(label_pattern, text, re.IGNORECASE)
    if not m:
        return None
    # Search for amount in the window after the label
    window_text = text[m.end(): m.end() + window]
    amt = re.search(r"R?\s*(\d[\d\s,]+\.?\d{0,2})", window_text)
    if amt:
        return normalise_amount(amt.group(1))
    return None


def extract_rate(text: str, *patterns: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            return val if val.endswith("%") else val + "%"
    return None


def extract_prime_linkage(text: str) -> tuple[str | None, str | None]:
    """
    Extract both the prime-linked expression and the effective rate.
    Returns (linkage_str, effective_rate) e.g. ("Prime + 0.25%", "11.50%")

    Handles formats like:
      Prime + 0.25% = 11.50%              -> ("Prime + 0.25%", "11.50%")
      11.25% per annum (Prime + 0.00%)    -> ("Prime + 0.00%", "11.25%")
      11.75% (Prime rate + 0.50%)         -> ("Prime rate + 0.50%", "11.75%")
      Prime - 0.25% (11.00%)             -> ("Prime - 0.25%", "11.00%")
    """
    # "Prime ± margin = effective" or "Prime ± margin per annum ... effective"
    m = re.search(
        r"(Prime(?:\s+rate)?\s*[+\-]\s*[\d.]+%?)"
        r"[^%\n]{0,40}?=\s*([\d.]+)\s*%",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip() + "%"

    # "effective% ... (Prime ± margin)" — rate comes before the prime expression
    m = re.search(
        r"([\d.]+)\s*%[^(\n]{0,40}\(\s*(Prime(?:\s+rate)?\s*[+\-]\s*[\d.]+%?)\s*\)",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(2).strip(), m.group(1).strip() + "%"

    # "Prime ± margin (effective%)"
    m = re.search(
        r"(Prime(?:\s+rate)?\s*[+\-]\s*[\d.]+%?)[^(\n]{0,20}\(\s*([\d.]+)\s*%\s*\)",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip() + "%"

    # Fallback: any standalone percentage near the word "prime" (not the margin itself)
    m = re.search(
        r"Prime(?:\s+rate)?[^\n]{0,60}?(?<!\d)(1[0-9]\.\d+)\s*%",
        text, re.IGNORECASE,
    )
    if m:
        return "Prime-linked", m.group(1).strip() + "%"

    return None, None
