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
    jwt_issuer: str = "earth-monitor-api"
    jwt_audience: str = "earth-monitor-web"
    database_url: str = "postgresql+asyncpg://earth:earth@localhost:5432/earth_monitor"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    bootstrap_local_workspace: bool = False
    allow_public_registration: bool = False
    local_user_email: EmailStr = "analyst@terralens.app"
    local_user_password: str = "LocalAccess123!"
    stac_api_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    stac_collection: str = "sentinel-2-l2a"
    celestrak_gp_url: str = "https://celestrak.org/NORAD/elements/gp.php"
    orbital_groups: list[str] = ["resource", "weather", "planet"]
    orbital_cache_seconds: int = 7200
    planet_satellite_limit: int = 24
    usgs_earthquake_feed_url: str = (
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    )
    hazard_cache_seconds: int = 60
    request_timeout_seconds: float = 20.0
    provider_max_attempts: int = 3
    provider_backoff_seconds: float = 0.25
    provider_max_items: int = 20
    monitoring_lookback_days: int = 30
    max_request_body_bytes: int = 1_048_576
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
        if self.environment == "production" and self.bootstrap_local_workspace:
            raise RuntimeError("BOOTSTRAP_LOCAL_WORKSPACE must be false in production")
        if self.environment == "production" and "*" in self.cors_origins:
            raise RuntimeError("Production CORS origins must be explicit")
        if self.environment == "production" and "*" in self.allowed_hosts:
            raise RuntimeError("Production allowed hosts must be explicit")
        if self.environment == "production" and self.allow_public_registration:
            raise RuntimeError("Public registration must be disabled in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
