from fastapi import APIRouter, Depends, Query
import aiosqlite

from api.database import get_db
from api.middleware.rate_limit import check_rate_limit
from api.models.api_key import APIKey
from api.models.rate import Rate
from api.services import scraper_service

router = APIRouter(prefix="/api/v1/rates", tags=["rates"])


@router.get("/banks")
async def list_banks(
    _: APIKey = Depends(check_rate_limit),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all banks available in the current dataset."""
    banks = await scraper_service.get_available_banks(db)
    return {"banks": banks, "count": len(banks)}


@router.get("", response_model=list[Rate])
async def get_rates(
    bank: str | None = Query(None, description="Filter by bank name (partial match)"),
    type: str | None = Query(None, description="Filter by rate type (partial match)"),
    _: APIKey = Depends(check_rate_limit),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Return all cached interest rates.

    Filter examples:
    - `?bank=nedbank`
    - `?bank=investec&type=fixed`
    - `?type=home`
    """
    rows = await scraper_service.get_cached_rates(db, bank=bank, rate_type=type)
    return rows


@router.get("/compare")
async def compare_rates(
    type: str = Query("fixed deposit", description="Rate type to compare across banks"),
    _: APIKey = Depends(check_rate_limit),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Compare a specific rate type side-by-side across all banks.
    E.g. `?type=fixed+deposit`
    """
    rows = await scraper_service.get_cached_rates(db, rate_type=type)
    by_bank: dict[str, list] = {}
    for r in rows:
        by_bank.setdefault(r["bank"], []).append(r)

    return {
        "type_filter": type,
        "scraped_at": rows[0]["scraped_at"] if rows else None,
        "banks": [
            {"bank": bank, "count": len(entries), "rates": entries}
            for bank, entries in by_bank.items()
        ],
    }


@router.post("/refresh")
async def trigger_refresh(
    api_key: APIKey = Depends(check_rate_limit),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Trigger an immediate refresh of scraped rate data.
    Pro tier only.
    """
    if api_key.tier not in ("pro", "unlimited"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Rate refresh requires a Pro plan.")
    count = await scraper_service.refresh_rates(db)
    return {"status": "refreshed", "rows_inserted": count}
