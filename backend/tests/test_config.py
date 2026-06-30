import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_development_secret() -> None:
    settings = Settings(environment="production", seed_demo_data=False)
    with pytest.raises(RuntimeError, match="unique SECRET_KEY"):
        settings.assert_safe_for_production()


def test_production_rejects_demo_seed() -> None:
    settings = Settings(
        environment="production",
        secret_key="a-production-secret-with-more-than-32-characters",
        seed_demo_data=True,
    )
    with pytest.raises(RuntimeError, match="SEED_DEMO_DATA"):
        settings.assert_safe_for_production()


def test_short_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="32 characters"):
        Settings(secret_key="short")


def test_comma_separated_cors_origins_are_supported() -> None:
    settings = Settings(cors_origins="https://one.example, https://two.example")  # type: ignore[arg-type]
    assert settings.cors_origins == ["https://one.example", "https://two.example"]


def test_production_rejects_wildcard_cors() -> None:
    settings = Settings(
        environment="production",
        secret_key="a-production-secret-with-more-than-32-characters",
        cors_origins=["*"],
    )
    with pytest.raises(RuntimeError, match="CORS"):
        settings.assert_safe_for_production()
