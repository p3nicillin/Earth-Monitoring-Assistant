from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrbitalElementSet(BaseModel):
    """CelesTrak OMM fields required by SGP4 propagation."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    object_name: str = Field(alias="OBJECT_NAME")
    object_id: str = Field(alias="OBJECT_ID")
    epoch: str = Field(alias="EPOCH")
    mean_motion: float = Field(alias="MEAN_MOTION")
    eccentricity: float = Field(alias="ECCENTRICITY")
    inclination: float = Field(alias="INCLINATION")
    right_ascension: float = Field(alias="RA_OF_ASC_NODE")
    argument_of_pericenter: float = Field(alias="ARG_OF_PERICENTER")
    mean_anomaly: float = Field(alias="MEAN_ANOMALY")
    ephemeris_type: int = Field(default=0, alias="EPHEMERIS_TYPE")
    classification_type: str = Field(default="U", alias="CLASSIFICATION_TYPE")
    norad_catalog_id: int = Field(alias="NORAD_CAT_ID")
    element_set_number: int = Field(alias="ELEMENT_SET_NO")
    revolution_at_epoch: int | None = Field(default=None, alias="REV_AT_EPOCH")
    bstar: float = Field(alias="BSTAR")
    mean_motion_dot: float = Field(alias="MEAN_MOTION_DOT")
    mean_motion_ddot: float = Field(alias="MEAN_MOTION_DDOT")


class MissionProfile(BaseModel):
    family: str
    operator: str
    instruments: list[str]
    nominal_swath_km: float
    nominal_revisit: str
    orbit_class: str
    color: str
    sensor_status: str


class TrackedSatellite(BaseModel):
    id: str
    name: str
    international_designator: str
    norad_catalog_id: int
    element_epoch: datetime
    profile: MissionProfile
    omm: OrbitalElementSet


class SatelliteCatalog(BaseModel):
    source: str
    source_updated_at: datetime
    cache_expires_at: datetime
    count: int
    satellites: list[TrackedSatellite]


class EarthquakeFeature(BaseModel):
    id: str
    title: str
    magnitude: float | None
    occurred_at: datetime
    longitude: float
    latitude: float
    depth_km: float
    detail_url: str | None
    tsunami: bool
    place: str | None
    properties: dict[str, Any] = Field(default_factory=dict)


class EarthquakeFeed(BaseModel):
    source: str
    generated_at: datetime
    cache_expires_at: datetime
    count: int
    earthquakes: list[EarthquakeFeature]
