from fastapi import APIRouter, Depends
import aiosqlite

from api.database import get_db
from api.middleware.auth import get_current_key
from api.models.api_key import APIKey, TIER_LIMITS

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


@router.get("/me")
async def get_my_key_info(
    api_key: APIKey = Depends(get_current_key),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return metadata about the authenticated API key."""
    async with db.execute(
        """
        SELECT COUNT(*) as cnt FROM request_log
        WHERE key_id = ? AND ts >= datetime('now', '-1 day')
        """,
        (api_key.id,),
    ) as cur:
        row = await cur.fetchone()
        requests_today = row["cnt"]

    limit = api_key.daily_limit
    async with db.execute(
        "SELECT scraped_at FROM rates_cache ORDER BY scraped_at DESC LIMIT 1"
    ) as cur:
        cache_row = await cur.fetchone()
        last_scraped = cache_row["scraped_at"] if cache_row else None

    return {
        "email": api_key.email,
        "tier": api_key.tier,
        "daily_limit": limit if limit is not None else "unlimited",
        "requests_today": requests_today,
        "remaining_today": max(0, limit - requests_today) if limit is not None else "unlimited",
        "created_at": api_key.created_at,
        "data_last_scraped": last_scraped,
    }
