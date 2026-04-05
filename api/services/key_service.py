import hashlib
import secrets

import aiosqlite


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def provision_key(db: aiosqlite.Connection, email: str, tier: str) -> str:
    """Generate a new API key, store only its hash, return the raw key (shown once)."""
    raw = "sa_" + secrets.token_urlsafe(32)
    key_hash = _hash(raw)
    await db.execute(
        "INSERT INTO api_keys (email, key_hash, tier) VALUES (?, ?, ?)",
        (email, key_hash, tier),
    )
    await db.commit()
    return raw


async def deactivate_keys_for_email(db: aiosqlite.Connection, email: str) -> None:
    await db.execute(
        "UPDATE api_keys SET active = 0 WHERE email = ?", (email,)
    )
    await db.commit()


async def get_key_by_hash(db: aiosqlite.Connection, raw: str):
    key_hash = _hash(raw)
    async with db.execute(
        "SELECT * FROM api_keys WHERE key_hash = ? AND active = 1", (key_hash,)
    ) as cur:
        return await cur.fetchone()
