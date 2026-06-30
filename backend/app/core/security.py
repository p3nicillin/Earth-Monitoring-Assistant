from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

ALGORITHM = "HS256"
password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(subject: str, *, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    claims: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": datetime.now(UTC),
        "exp": expires_at,
    }
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
