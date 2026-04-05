from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
import aiosqlite

from api.database import get_db
from api.models.api_key import APIKey
from api.services.key_service import get_key_by_hash

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_key(
    raw_key: str | None = Security(_api_key_header),
    db: aiosqlite.Connection = Depends(get_db),
) -> APIKey:
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    row = await get_key_by_hash(db, raw_key)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )
    return APIKey(
        id=row["id"],
        email=row["email"],
        key_hash=row["key_hash"],
        tier=row["tier"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )
