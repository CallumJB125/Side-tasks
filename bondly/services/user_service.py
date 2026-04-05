import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import aiosqlite

from bondly.config import get_settings

_settings = get_settings()


# ---------------------------------------------------------------------------
# Minimal HS256 JWT implementation (avoids broken cryptography lib on this host)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _hash_id_number(id_number: str) -> str:
    return hashlib.sha256(id_number.strip().encode()).hexdigest()


def hash_password(plain: str) -> str:
    salt = base64.b64encode(hashlib.sha256(plain.encode()).digest()[:8]).decode()
    return hashlib.sha256(f"{salt}{plain}".encode()).hexdigest() + ":" + salt


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, salt = stored.rsplit(":", 1)
        return hashlib.sha256(f"{salt}{plain}".encode()).hexdigest() + ":" + salt == stored
    except Exception:
        return False


def create_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_settings.jwt_expire_minutes)
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": str(user_id),
        "email": email,
        "exp": int(expire.timestamp()),
    }).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url_encode(
        hmac.new(_settings.jwt_secret.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header, payload_b64, sig = parts
    expected_sig = _b64url_encode(
        hmac.new(
            _settings.jwt_secret.encode(),
            f"{header}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid token signature")
    data = json.loads(_b64url_decode(payload_b64))
    if data.get("exp", 0) < datetime.now(timezone.utc).timestamp():
        raise ValueError("Token expired")
    return data


async def create_user(
    db: aiosqlite.Connection,
    email: str,
    password: str,
    full_name: str,
    id_number: str,
) -> int:
    pw_hash = hash_password(password)
    id_hash = _hash_id_number(id_number)
    cursor = await db.execute(
        "INSERT INTO users (email, password_hash, id_number, full_name) VALUES (?, ?, ?, ?)",
        (email, pw_hash, id_hash, full_name),
    )
    await db.commit()
    return cursor.lastrowid


async def get_user_by_email(db: aiosqlite.Connection, email: str):
    async with db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cur:
        return await cur.fetchone()


async def get_user_by_id(db: aiosqlite.Connection, user_id: int):
    async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        return await cur.fetchone()


async def activate_user(db: aiosqlite.Connection, email: str) -> None:
    await db.execute("UPDATE users SET active = 1 WHERE email = ?", (email,))
    await db.commit()
