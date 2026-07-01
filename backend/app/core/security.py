import uuid
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
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": expires_at,
    }
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "type", "iat", "exp", "iss", "aud", "jti"]},
    )
