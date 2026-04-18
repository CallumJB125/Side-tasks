import os
import aiosqlite
from bondly.config import get_settings

_settings = get_settings()


def _db_path() -> str:
    path = _settings.db_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


async def get_db():
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    async with aiosqlite.connect(_db_path()) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                id_number     TEXT    NOT NULL,       -- SA ID number (hashed at rest)
                full_name     TEXT    NOT NULL,
                active        INTEGER NOT NULL DEFAULT 0,  -- activated after payment
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL REFERENCES users(id),
                stripe_session_id   TEXT,
                status              TEXT NOT NULL DEFAULT 'pending',
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                activated_at        TEXT
            );

            CREATE TABLE IF NOT EXISTS search_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id),
                query        TEXT    NOT NULL,
                result_found INTEGER NOT NULL DEFAULT 0,
                ts           TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS financial_profiles (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL REFERENCES users(id),
                period           TEXT    NOT NULL,           -- "2024-01"
                statement_period TEXT,
                gross_income     REAL    NOT NULL DEFAULT 0,
                net_income       REAL    NOT NULL DEFAULT 0,
                total_expenses   REAL    NOT NULL DEFAULT 0,
                net_cash_flow    REAL    NOT NULL DEFAULT 0,
                expense_breakdown TEXT,                      -- JSON: {category: amount}
                transactions     TEXT,                       -- JSON: [{date, desc, amount, category}]
                bank_detected    TEXT,
                parse_confidence REAL    DEFAULT 0,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        await db.commit()
