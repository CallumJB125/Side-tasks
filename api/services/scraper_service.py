"""
Async wrapper around the existing sa_bank_rates scraper.
Runs the synchronous scrapers in a thread pool and persists
results into the rates_cache table.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import aiosqlite

# Import individual scrapers from the existing module
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sa_bank_rates import (
    scrape_nedbank,
    scrape_absa,
    scrape_standardbank,
    scrape_investec,
    scrape_africanbank,
    scrape_fnb,
    scrape_capitec,
    deduplicate,
)

SCRAPERS = [
    scrape_nedbank,
    scrape_absa,
    scrape_standardbank,
    scrape_investec,
    scrape_africanbank,
    scrape_fnb,
    scrape_capitec,
]

_executor = ThreadPoolExecutor(max_workers=4)


def _run_all_scrapers() -> list[dict]:
    """Run all scrapers synchronously (called in a thread)."""
    results = []
    for scraper in SCRAPERS:
        result = scraper()
        result["rates"] = deduplicate(result["rates"])
        results.append(result)
    return results


async def refresh_rates(db: aiosqlite.Connection) -> int:
    """
    Fetch fresh rates from all banks and replace the rates_cache table.
    Returns the number of rows inserted.
    """
    loop = asyncio.get_event_loop()
    bank_results = await loop.run_in_executor(_executor, _run_all_scrapers)

    scraped_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for bank_result in bank_results:
        if bank_result.get("blocked"):
            continue
        bank_name = bank_result["bank"]
        for r in bank_result["rates"]:
            rows.append((
                bank_name,
                r["type"],
                r["product"],
                r["rate"],
                r.get("details", ""),
                scraped_at,
            ))

    await db.execute("DELETE FROM rates_cache")
    await db.executemany(
        "INSERT INTO rates_cache (bank, type, product, rate, details, scraped_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    await db.commit()
    return len(rows)


async def get_cached_rates(
    db: aiosqlite.Connection,
    bank: str | None = None,
    rate_type: str | None = None,
) -> list[dict]:
    """Query the rates_cache table with optional filters."""
    conditions = []
    params: list = []

    if bank:
        conditions.append("LOWER(bank) LIKE ?")
        params.append(f"%{bank.lower()}%")
    if rate_type:
        conditions.append("LOWER(type) LIKE ?")
        params.append(f"%{rate_type.lower()}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT bank, type, product, rate, details, scraped_at FROM rates_cache {where} ORDER BY bank, type"

    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
        return [dict(row) for row in rows]


async def get_available_banks(db: aiosqlite.Connection) -> list[str]:
    async with db.execute("SELECT DISTINCT bank FROM rates_cache ORDER BY bank") as cur:
        rows = await cur.fetchall()
        return [row["bank"] for row in rows]


async def seed_from_json(db: aiosqlite.Connection) -> None:
    """On first startup, load the existing sa_bank_rates.json snapshot if the DB is empty."""
    import json

    async with db.execute("SELECT COUNT(*) as cnt FROM rates_cache") as cur:
        row = await cur.fetchone()
        if row["cnt"] > 0:
            return

    json_path = os.path.join(os.path.dirname(__file__), "..", "..", "sa_bank_rates.json")
    if not os.path.exists(json_path):
        return

    with open(json_path) as f:
        data = json.load(f)

    scraped_at = data.get("scraped_date", datetime.now(timezone.utc).isoformat())
    rows = []
    for bank_result in data.get("banks", []):
        if bank_result.get("blocked"):
            continue
        bank_name = bank_result["bank"]
        for r in bank_result["rates"]:
            rows.append((
                bank_name,
                r["type"],
                r["product"],
                r["rate"],
                r.get("details", ""),
                scraped_at,
            ))

    if rows:
        await db.executemany(
            "INSERT INTO rates_cache (bank, type, product, rate, details, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        await db.commit()
