import os
import aiosqlite
from api.config import get_settings

_settings = get_settings()


def _db_path() -> str:
    path = _settings.db_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


async def get_db() -> aiosqlite.Connection:
    """FastAPI dependency – yields an open DB connection."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    """Create tables on startup."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT    NOT NULL,
                key_hash     TEXT    NOT NULL UNIQUE,
                tier         TEXT    NOT NULL DEFAULT 'basic',
                active       INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rates_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                bank        TEXT NOT NULL,
                type        TEXT NOT NULL,
                product     TEXT NOT NULL,
                rate        TEXT NOT NULL,
                details     TEXT,
                scraped_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS request_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id  INTEGER NOT NULL,
                ts      TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_request_log_key_ts
                ON request_log (key_id, ts);
        """)
        await db.commit()
