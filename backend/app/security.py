"""Password hashing (bcrypt) and JWT access tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; we enforce a max length in the schema.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
