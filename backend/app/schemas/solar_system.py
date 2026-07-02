"""API contracts for live solar-system monitoring and spot detections."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "watch", "warning", "critical"]
DetectionBody = Literal["sun", "earth", "interplanetary"]


class PlanetState(BaseModel):
    name: str
    body_class: str
    x_au: float
    y_au: float
    z_au: float
    ecliptic_longitude_deg: float
    ecliptic_latitude_deg: float
    distance_from_sun_au: float
    distance_from_earth_au: float
    elongation_deg: float
    light_time_minutes: float
    orbital_period_days: float
    radius_km: float
    display_color: str


class EphemerisSnapshot(BaseModel):
    computed_at: datetime
    source: str
    valid_range: str
    planets: list[PlanetState]


class XrayFluxPoint(BaseModel):
    time_tag: datetime
    flux_watts_m2: float


class KpEntry(BaseModel):
    time_tag: datetime
    kp: float


class SolarWindPoint(BaseModel):
    time_tag: datetime
    speed_km_s: float | None = None
    density_p_cm3: float | None = None
    bz_nt: float | None = None
    bt_nt: float | None = None


class FlareEvent(BaseModel):
    began_at: datetime | None
    peaked_at: datetime | None
    ended_at: datetime | None
    max_class: str | None
    in_progress: bool


class SpaceWeather(BaseModel):
    source: str
    generated_at: datetime
    cache_expires_at: datetime
    xray_flux: list[XrayFluxPoint]
    current_xray_class: str | None
    latest_flare: FlareEvent | None
    kp_index: list[KpEntry]
    current_kp: float | None
    solar_wind: list[SolarWindPoint]
    current_solar_wind: SolarWindPoint | None
    proton_flux_10mev_pfu: float | None


class SolarImage(BaseModel):
    key: str
    title: str
    description: str
    url: str
    source: str


class NeoApproach(BaseModel):
    designation: str
    close_approach_at: datetime
    distance_au: float
    distance_lunar: float
    velocity_km_s: float
    absolute_magnitude_h: float | None
    estimated_diameter_m: float | None


class NeoFeed(BaseModel):
    source: str
    generated_at: datetime
    cache_expires_at: datetime
    lookahead_days: int
    count: int
    approaches: list[NeoApproach]


class EarthEvent(BaseModel):
    id: str
    title: str
    category_id: str
    category_title: str
    longitude: float | None
    latitude: float | None
    observed_at: datetime | None
    magnitude_value: float | None
    magnitude_unit: str | None
    source_url: str | None


class EarthEventFeed(BaseModel):
    source: str
    generated_at: datetime
    cache_expires_at: datetime
    lookback_days: int
    count: int
    events: list[EarthEvent]


class SpotDetection(BaseModel):
    id: str
    detector: str
    detector_version: str
    category: str
    severity: Severity
    body: DetectionBody
    title: str
    summary: str
    observed_at: datetime
    source: str
    source_url: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class DetectionFeed(BaseModel):
    generated_at: datetime
    count: int
    detections: list[SpotDetection]


class FeedStatus(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class SolarSystemOverview(BaseModel):
    generated_at: datetime
    feed_status: list[FeedStatus]
    space_weather: SpaceWeather | None
    ephemeris: EphemerisSnapshot
    neo: NeoFeed | None
    earth_events: EarthEventFeed | None
    solar_images: list[SolarImage]
    detections: DetectionFeed
