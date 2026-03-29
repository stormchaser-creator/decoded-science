"""Decoded auth utilities — JWT + password hashing (stdlib PBKDF2)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

SECRET_KEY = os.environ.get("DECODED_JWT_SECRET", "")
if not SECRET_KEY:
    import warnings
    warnings.warn(
        "DECODED_JWT_SECRET is not set — using a random ephemeral secret. "
        "Tokens will not survive restarts. Set DECODED_JWT_SECRET in your environment.",
        stacklevel=1,
    )
    SECRET_KEY = secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

_ITERATIONS = 260_000
_HASH = "sha256"


def hash_password(password: str) -> str:
    """Return 'pbkdf2$salt$hash' string."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(_HASH, password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, salt, expected_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(_HASH, plain.encode(), salt.encode(), _ITERATIONS)
    return hmac.compare_digest(dk.hex(), expected_hex)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
