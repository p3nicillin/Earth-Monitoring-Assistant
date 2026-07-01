import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_development_secret() -> None:
    settings = Settings(environment="production", bootstrap_local_workspace=False)
    with pytest.raises(RuntimeError, match="unique SECRET_KEY"):
        settings.assert_safe_for_production()


def test_production_rejects_local_bootstrap() -> None:
    settings = Settings(
        environment="production",
        secret_key="a-production-secret-with-more-than-32-characters",
        bootstrap_local_workspace=True,
    )
    with pytest.raises(RuntimeError, match="BOOTSTRAP_LOCAL_WORKSPACE"):
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


def test_production_rejects_wildcard_hosts_and_public_registration() -> None:
    with pytest.raises(RuntimeError, match="allowed hosts"):
        Settings(
            environment="production",
            secret_key="a-production-secret-with-more-than-32-characters",
            allowed_hosts=["*"],
        ).assert_safe_for_production()
    with pytest.raises(RuntimeError, match="registration"):
        Settings(
            environment="production",
            secret_key="a-production-secret-with-more-than-32-characters",
            allow_public_registration=True,
        ).assert_safe_for_production()
