"""
South African Bank Interest Rates Scraper
Fetches publicly available interest rates from major SA banks.

Banks covered:
  - Nedbank       (investment-interest-rates page)
  - Absa          (rates-and-fees page)
  - Standard Bank (fixed deposit + saveup pages)
  - Investec      (daily-rates page)
  - African Bank  (fixed-deposits page)
  - FNB           (blocked by bot protection – noted in output)
  - Capitec       (blocked by Cloudflare JS challenge – noted in output)
"""

import json
import re
import sys
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag
from tabulate import tabulate

# Firefox headers – avoids brotli encoding issues and passes most bot checks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
        "Gecko/20100101 Firefox/122.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-ZA,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

TIMEOUT = 25


def get_page(url: str) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.HTTPError as exc:
        print(f"  [warn] HTTP {exc.response.status_code} for {url}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"  [warn] Failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def nearest_heading(element: Tag) -> str:
    """Walk backwards through siblings/parents to find the nearest heading."""
    for sibling in element.find_all_previous(["h1", "h2", "h3", "h4", "caption"]):
        text = clean(sibling.get_text())
        if text:
            return text
    return ""


def parse_table(table: Tag, category: str, product_prefix: str = "") -> list[dict]:
    rows = table.find_all("tr")
    if not rows:
        return []

    # Identify header row
    header_cells = [clean(th.get_text()) for th in rows[0].find_all(["th", "td"])]
    first_header = header_cells[0] if header_cells else ""

    results = []
    data_rows = rows[1:] if any(header_cells) else rows

    for row in data_rows:
        cells = [clean(td.get_text()) for td in row.find_all(["td", "th"])]
        if not cells or not any(cells):
            continue

        rate_cells = [(i, c) for i, c in enumerate(cells) if re.search(r"\d+(?:[,.]\d+)?\s*%", c)]
        if not rate_cells:
            continue

        product = cells[0] if cells[0] else first_header
        if product_prefix:
            product = f"{product_prefix} – {product}" if product else product_prefix

        primary_rate = rate_cells[0][1]

        detail_parts = []
        for i in range(1, len(cells)):
            if i < len(header_cells) and header_cells[i]:
                detail_parts.append(f"{header_cells[i]}: {cells[i]}")
            else:
                detail_parts.append(cells[i])

        results.append({
            "type": category,
            "product": product,
            "rate": primary_rate,
            "details": " | ".join(detail_parts),
        })

    return results


# ---------------------------------------------------------------------------
# Nedbank
# ---------------------------------------------------------------------------

def scrape_nedbank() -> dict:
    bank = "Nedbank"
    rates = []

    pages = [
        ("Investment Rates",
         "https://personal.nedbank.co.za/home/investment-interest-rates.html"),
        ("Fixed Deposit",
         "https://personal.nedbank.co.za/save-and-invest/accounts/end-of-term/fixed-deposit/interest-rates-and-fees.html"),
        ("JustInvest",
         "https://personal.nedbank.co.za/save-and-invest/accounts/in-24hrs/justinvest/interest-rates-and-fees.html"),
    ]

    for category, url in pages:
        soup = get_page(url)
        if soup is None:
            continue
        for table in soup.find_all("table"):
            heading = nearest_heading(table)
            rates.extend(parse_table(table, category, heading))

    return {"bank": bank, "rates": rates, "source": [p[1] for p in pages],
            "blocked": False}


# ---------------------------------------------------------------------------
# Absa Bank
# ---------------------------------------------------------------------------

def scrape_absa() -> dict:
    bank = "Absa Bank"
    rates = []

    pages = [
        ("Rates & Fees",
         "https://www.absa.co.za/rates-and-fees/"),
        ("Fixed Deposit",
         "https://www.absa.co.za/personal/save-invest/products/fixed-deposit/"),
    ]

    for category, url in pages:
        soup = get_page(url)
        if soup is None:
            continue
        for table in soup.find_all("table"):
            heading = nearest_heading(table)
            # Skip tables that look like navigation/layout (no percentage values at all)
            table_text = table.get_text()
            if not re.search(r"\d+(?:[,.]\d+)?\s*%", table_text):
                continue
            rates.extend(parse_table(table, category, heading))

    return {"bank": bank, "rates": rates, "source": [p[1] for p in pages],
            "blocked": False}


# ---------------------------------------------------------------------------
# Standard Bank
# ---------------------------------------------------------------------------

def scrape_standardbank() -> dict:
    bank = "Standard Bank"
    rates = []

    pages = [
        ("Fixed Deposit",
         "https://www.standardbank.co.za/southafrica/personal/products-and-services/grow-your-money/savings-and-investment/our-accounts/fixed-deposit-investment-account"),
        ("SaveUp Account",
         "https://www.standardbank.co.za/southafrica/personal/products-and-services/grow-your-money/savings-and-investment/our-accounts/saveup-savings-account"),
    ]

    for category, url in pages:
        soup = get_page(url)
        if soup is None:
            continue
        for table in soup.find_all("table"):
            heading = nearest_heading(table)
            table_text = table.get_text()
            if not re.search(r"\d+(?:[,.]\d+)?\s*%", table_text):
                continue
            rates.extend(parse_table(table, category, heading))

    return {"bank": bank, "rates": rates, "source": [p[1] for p in pages],
            "blocked": False}


# ---------------------------------------------------------------------------
# Investec
# ---------------------------------------------------------------------------

def scrape_investec() -> dict:
    bank = "Investec"
    rates = []

    pages = [
        ("Savings & Fixed Deposits",
         "https://www.investec.com/en_za/savings-accounts/daily-rates.html"),
    ]

    for category, url in pages:
        soup = get_page(url)
        if soup is None:
            continue
        for table in soup.find_all("table"):
            # Investec tables have the product type in the first header cell
            rows = table.find_all("tr")
            if not rows:
                continue

            # First row first cell is typically the product group name
            first_row_cells = [clean(td.get_text()) for td in rows[0].find_all(["th", "td"])]
            product_name = first_row_cells[0] if first_row_cells else ""

            # Use remaining rows as data, with column headers from first row
            for row in rows[1:]:
                cells = [clean(td.get_text()) for td in row.find_all(["td", "th"])]
                if not cells:
                    continue
                rate_cells = [(i, c) for i, c in enumerate(cells)
                              if re.search(r"\d+(?:[,.]\d+)?\s*%", c)]
                if not rate_cells:
                    continue

                product = f"{product_name} – {cells[0]}" if cells[0] else product_name
                primary_rate = rate_cells[0][1]

                # Build details from remaining cells using header labels
                detail_parts = []
                for idx, c in enumerate(cells[1:], start=1):
                    label = first_row_cells[idx] if idx < len(first_row_cells) else ""
                    detail_parts.append(f"{label}: {c}" if label else c)

                rates.append({
                    "type": category,
                    "product": product,
                    "rate": primary_rate,
                    "details": " | ".join(detail_parts),
                })

    return {"bank": bank, "rates": rates, "source": [p[1] for p in pages],
            "blocked": False}


# ---------------------------------------------------------------------------
# African Bank
# ---------------------------------------------------------------------------

def scrape_africanbank() -> dict:
    bank = "African Bank"
    rates = []

    pages = [
        ("Fixed Deposits",
         "https://www.africanbank.co.za/en/home/invest/fixed-deposits/"),
        ("Access Accumulator",
         "https://www.africanbank.co.za/en/home/product-access-accumulator/"),
    ]

    for category, url in pages:
        soup = get_page(url)
        if soup is None:
            continue
        for table in soup.find_all("table"):
            heading = nearest_heading(table)
            table_text = table.get_text()
            if not re.search(r"\d+(?:[,.]\d+)?\s*%", table_text):
                continue
            rates.extend(parse_table(table, category, heading or "Fixed Deposit"))

    return {"bank": bank, "rates": rates, "source": [p[1] for p in pages],
            "blocked": False}


# ---------------------------------------------------------------------------
# FNB – blocked by Radware CAPTCHA
# ---------------------------------------------------------------------------

def scrape_fnb() -> dict:
    return {
        "bank": "FNB (First National Bank)",
        "rates": [],
        "source": [
            "https://www.fnb.co.za/rates/savings-and-investments/index.html",
            "https://www.fnb.co.za/rates/LendingRates.html",
        ],
        "blocked": True,
        "blocked_reason": "Radware Bot Manager CAPTCHA – requires browser with JS execution",
        "manual_url": "https://www.fnb.co.za/rates/savings-and-investments/index.html",
    }


# ---------------------------------------------------------------------------
# Capitec – blocked by Cloudflare JS challenge
# ---------------------------------------------------------------------------

def scrape_capitec() -> dict:
    return {
        "bank": "Capitec Bank",
        "rates": [],
        "source": [
            "https://www.capitecbank.co.za/personal/save/save-fees-and-rates/",
            "https://www.capitecbank.co.za/personal/credit/rates-and-fees/",
        ],
        "blocked": True,
        "blocked_reason": "Cloudflare JS challenge – requires browser with JS execution",
        "manual_url": "https://www.capitecbank.co.za/personal/save/save-fees-and-rates/",
    }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(rates: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in rates:
        key = (r["type"], r["product"][:60], r["rate"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCRAPERS = [
    scrape_nedbank,
    scrape_absa,
    scrape_standardbank,
    scrape_investec,
    scrape_africanbank,
    scrape_fnb,
    scrape_capitec,
]


def main():
    all_results = []
    table_rows = []

    print(f"South African Bank Interest Rates — {date.today()}\n")

    for scraper in SCRAPERS:
        name = scraper.__name__.replace("scrape_", "").upper()
        print(f"Fetching {name} ...", flush=True)
        result = scraper()
        result["rates"] = deduplicate(result["rates"])
        all_results.append(result)

        if result.get("blocked"):
            print(f"  [blocked] {result.get('blocked_reason', '')}")
            continue

        for r in result["rates"]:
            table_rows.append([
                result["bank"],
                r["type"],
                r["product"][:55],
                r["rate"],
                r["details"][:65] if r["details"] else "–",
            ])

    print()

    if table_rows:
        print(tabulate(
            table_rows,
            headers=["Bank", "Category", "Product", "Rate", "Details"],
            tablefmt="rounded_outline",
            maxcolwidths=[20, 22, 55, 12, 65],
        ))
    else:
        print("No rates scraped.")

    print()
    # Summary of blocked banks
    blocked = [r for r in all_results if r.get("blocked")]
    if blocked:
        print("Banks requiring manual browser visit (bot-protected):")
        for b in blocked:
            print(f"  • {b['bank']}: {b.get('manual_url', '')}")
            print(f"    Reason: {b.get('blocked_reason', '')}")

    output = {
        "scraped_date": str(date.today()),
        "banks": all_results,
    }
    out_path = "sa_bank_rates.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    scraped = [r for r in all_results if not r.get("blocked")]
    total = sum(len(r["rates"]) for r in scraped)
    print(f"\nScraped {total} rate entries across {len(scraped)} banks.")
    print(f"Full results saved to: {out_path}")


if __name__ == "__main__":
    main()
