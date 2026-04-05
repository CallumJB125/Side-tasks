from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from bondly.database import get_db
from bondly.middleware.auth import require_active_subscription
from bondly.models.mortgage import MortgageReport, MortgageSearchRequest
from bondly.services.lightstone import get_client

router = APIRouter(prefix="/mortgage", tags=["mortgage"])


@router.get("/search")
async def search_property(
    address: str = Query(..., description="Property street address to search"),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Search for a property by address.
    Returns a list of matching properties with their erf keys.
    Use the erf_key from this response in GET /mortgage/report.
    """
    client = get_client()
    try:
        results = client.search_property(address)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Lightstone error: {exc}")

    await db.execute(
        "INSERT INTO search_log (user_id, query, result_found) VALUES (?, ?, ?)",
        (user["id"], address, int(len(results) > 0)),
    )
    await db.commit()

    return {"results": results, "count": len(results)}


@router.get("/report", response_model=MortgageReport)
async def get_mortgage_report(
    erf_key: str = Query(..., description="Erf key from /mortgage/search"),
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Retrieve the full mortgage report for a property.

    Returns:
    - Property details (erf, title deed, address, size)
    - Ownership record (owner name, transfer date, purchase price)
    - Bond registration (registered amount, bank, registration date)
    - Property valuation (AVM estimate and band)

    NOTE: Outstanding balance and current interest rate are NOT available here.
    Those require a direct query to your bank. Bondly can help you with that next step.
    """
    client = get_client()
    try:
        report = client.get_mortgage_report(erf_key, user["id_number"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Lightstone error: {exc}")

    await db.execute(
        "INSERT INTO search_log (user_id, query, result_found) VALUES (?, ?, 1)",
        (user["id"], f"report:{erf_key}"),
    )
    await db.commit()

    return report


@router.get("/me/history")
async def my_search_history(
    user=Depends(require_active_subscription),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return the authenticated user's search history."""
    async with db.execute(
        "SELECT query, result_found, ts FROM search_log WHERE user_id = ? ORDER BY ts DESC LIMIT 50",
        (user["id"],),
    ) as cur:
        rows = await cur.fetchall()
    return {"history": [dict(r) for r in rows]}
