from fastapi import Depends, HTTPException, status
import aiosqlite

from api.database import get_db
from api.middleware.auth import get_current_key
from api.models.api_key import APIKey


async def check_rate_limit(
    api_key: APIKey = Depends(get_current_key),
    db: aiosqlite.Connection = Depends(get_db),
) -> APIKey:
    limit = api_key.daily_limit
    if limit is None:
        # Unlimited tier — just log and pass through
        await db.execute(
            "INSERT INTO request_log (key_id) VALUES (?)", (api_key.id,)
        )
        await db.commit()
        return api_key

    async with db.execute(
        """
        SELECT COUNT(*) as cnt FROM request_log
        WHERE key_id = ?
          AND ts >= datetime('now', '-1 day')
        """,
        (api_key.id,),
    ) as cur:
        row = await cur.fetchone()
        count = row["cnt"]

    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit of {limit} requests exceeded. Upgrade your plan.",
            headers={"Retry-After": "86400"},
        )

    await db.execute(
        "INSERT INTO request_log (key_id) VALUES (?)", (api_key.id,)
    )
    await db.commit()
    return api_key
