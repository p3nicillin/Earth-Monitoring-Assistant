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
    swpc_base_url: str = "https://services.swpc.noaa.gov"
    cad_api_url: str = "https://ssd-api.jpl.nasa.gov/cad.api"
    eonet_events_url: str = "https://eonet.gsfc.nasa.gov/api/v3/events"
    space_weather_cache_seconds: int = 60
    neo_cache_seconds: int = 3600
    earth_events_cache_seconds: int = 300
    neo_lookahead_days: int = 7
    neo_max_distance_au: float = 0.05
    earth_events_lookback_days: int = 14
    solar_stream_interval_seconds: int = 30
    request_timeout_seconds: float = 20.0
    provider_max_attempts: int = 3
    provider_backoff_seconds: float = 0.25
    # 200, not the original 20: a large watch area spans multiple Sentinel-2
    # tiles, and the vegetation-change detector needs enough items per run to
    # find a same-tile pair separated by detector_min_days_between_pair. A
    # single STAC search request supports this size without pagination.
    provider_max_items: int = 200
    monitoring_lookback_days: int = 30
    max_request_body_bytes: int = 1_048_576
    rate_limit_per_minute: int = 120
    log_level: str = "INFO"
    detector_max_window_pixels: int = 4_000_000
    detector_cloud_cover_max: float = 20.0
    detector_min_days_between_pair: int = 3
    detector_ndvi_threshold: float = 0.15
    detector_min_change_fraction: float = 0.005
    monitoring_scheduler_enabled: bool = True
    scheduler_poll_interval_seconds: int = 900
    scheduler_startup_delay_seconds: int = 60
    scheduler_max_concurrent_runs: int = 3
    global_stream_interval_seconds: int = 60
    # Local appliance mode: the API auto-provisions a local operator account and
    # /auth/session issues its token without credentials. Meant for trusted-LAN,
    # self-hosted deployments (e.g. a Proxmox VM); leave off for shared hosts.
    local_mode: bool = False
    local_operator_email: EmailStr = "operator@terralens.app"
    # Continuous space-weather history capture powering adaptive baselines and
    # forecast self-scoring. Interval trades DB growth against series fidelity.
    learning_enabled: bool = True
    learning_interval_seconds: int = 300
    learning_min_baseline_samples: int = 288
    learning_baseline_window_days: int = 60
    learning_forecast_horizons_hours: list[int] = [3, 6, 12, 24]
    learning_forecast_match_tolerance_minutes: int = 45
    learning_retention_days: int = 365
    # Autonomous capture of notable live space imagery (SDO, SOHO, SUVI, EPIC).
    imagery_enabled: bool = True
    imagery_dir: str = "./data/imagery"
    imagery_interval_seconds: int = 900
    imagery_max_captures_per_source: int = 400
    imagery_max_bytes: int = 8_388_608
    epic_api_url: str = "https://epic.gsfc.nasa.gov"

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
