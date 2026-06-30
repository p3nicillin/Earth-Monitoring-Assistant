import uuid

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("SecurePassword123")
    assert hashed != "SecurePassword123"
    assert verify_password("SecurePassword123", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_contains_scoped_claims() -> None:
    user_id = str(uuid.uuid4())
    token, expires_at = create_access_token(user_id, role="analyst")
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "analyst"
    assert payload["type"] == "access"
    assert expires_at.isoformat()
