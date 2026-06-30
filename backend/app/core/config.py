from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Earth Monitoring Assistant"
    api_prefix: str = "/api/v1"
    environment: Literal["development", "test", "production"] = "development"
    secret_key: str = "development-secret-change-before-production"
    access_token_minutes: int = 60
    database_url: str = "postgresql+asyncpg://earth:earth@localhost:5432/earth_monitor"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    seed_demo_data: bool = False
    allow_public_registration: bool = False
    demo_user_email: EmailStr = "analyst@example.com"
    demo_user_password: str = "ChangeMe123!"
    stac_api_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    stac_collection: str = "sentinel-2-l2a"
    request_timeout_seconds: float = 20.0
    rate_limit_per_minute: int = 120
    log_level: str = "INFO"

    @field_validator("secret_key")
    @classmethod
    def validate_secret(cls, value: str, info: object) -> str:
        # The development default keeps first-run ergonomics; production is checked at startup.
        if len(value) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def assert_safe_for_production(self) -> None:
        if self.environment == "production" and "development-secret" in self.secret_key:
            raise RuntimeError("Production requires a unique SECRET_KEY")
        if self.environment == "production" and self.seed_demo_data:
            raise RuntimeError("SEED_DEMO_DATA must be false in production")
        if self.environment == "production" and "*" in self.cors_origins:
            raise RuntimeError("Production CORS origins must be explicit")


@lru_cache
def get_settings() -> Settings:
    return Settings()
