import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from shapely.geometry import shape

from app.models.entities import EventCategory, ReviewOutcome, Role, Severity


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(ApiModel):
    message: str


class UserCreate(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not (any(c.isupper() for c in value) and any(c.islower() for c in value)):
            raise ValueError("Password must contain upper and lower case letters")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain a number")
        return value


class UserRead(ApiModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: Role
    is_active: bool


class Token(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserRead


class ProjectCreate(ApiModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    color: str = Field(default="#4ade80", pattern=r"^#[0-9a-fA-F]{6}$")


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_archived: bool | None = None


class ProjectRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    color: str
    is_archived: bool
    created_at: datetime
    watch_area_count: int = 0
    event_count: int = 0


class GeoJSONPolygon(ApiModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]

    @field_validator("coordinates")
    @classmethod
    def closed_valid_polygon(cls, value: list[list[list[float]]]) -> list[list[list[float]]]:
        if not value or any(len(ring) < 4 for ring in value):
            raise ValueError("Every polygon ring needs at least four positions")
        if sum(len(ring) for ring in value) > 10_000:
            raise ValueError("A watch area may contain at most 10,000 positions")
        for ring in value:
            if ring[0] != ring[-1]:
                raise ValueError("Every polygon ring must be closed")
            for position in ring:
                if len(position) < 2 or not (
                    -180 <= position[0] <= 180 and -90 <= position[1] <= 90
                ):
                    raise ValueError("Coordinates must be valid WGS84 longitude/latitude positions")
        polygon = shape({"type": "Polygon", "coordinates": value})
        if polygon.is_empty or not polygon.is_valid or polygon.area == 0:
            raise ValueError("Polygon geometry must be non-empty and topologically valid")
        return value


class WatchAreaCreate(ApiModel):
    name: str = Field(min_length=2, max_length=160)
    geometry: GeoJSONPolygon
    categories: list[EventCategory] = Field(min_length=1)
    schedule: Literal["manual", "daily", "weekly"] = "daily"


class WatchAreaRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    geometry: dict[str, Any]
    categories: list[str]
    schedule: str
    is_active: bool
    last_checked_at: datetime | None
    created_at: datetime


class EventRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    summary: str
    event_type: str
    category: EventCategory
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    geometry: dict[str, Any]
    area_sq_km: float | None
    detected_at: datetime
    detector_name: str
    detector_version: str
    evidence: dict[str, Any]
    is_reviewed: bool
    review_outcome: ReviewOutcome
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None


class EventReview(ApiModel):
    outcome: Literal["confirmed", "rejected", "uncertain"]
    note: str | None = Field(default=None, max_length=2000)


class EventCollection(ApiModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int


class GeoJSONFeatureCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]


class DashboardSummary(ApiModel):
    active_projects: int
    watch_areas: int
    events_24h: int
    critical_events: int
    reviewed_percentage: float
    category_counts: dict[str, int]
    severity_counts: dict[str, int]
    processing_status: Literal["operational", "degraded"] = "operational"


class MonitoringRequest(ApiModel):
    watch_area_id: uuid.UUID
    provider: Literal["demo", "planetary-computer"] = "demo"
    max_cloud_cover: float = Field(default=30, ge=0, le=100)


class MonitoringResult(ApiModel):
    run_id: uuid.UUID
    source_items: int
    observations_created: int
    events_created: int
    status: Literal["completed", "no_imagery"]
    message: str


class AssistantRequest(ApiModel):
    question: str = Field(min_length=3, max_length=1000)
    project_id: uuid.UUID | None = None


class AssistantResponse(ApiModel):
    answer: str
    interpreted_filters: dict[str, Any]
    result_count: int
    features: GeoJSONFeatureCollection
    suggestions: list[str]


class ReportCreate(ApiModel):
    project_id: uuid.UUID
    report_type: Literal["executive", "environmental", "disaster", "agricultural"] = "executive"
    period_start: datetime
    period_end: datetime

    @model_validator(mode="after")
    def chronological_period(self) -> "ReportCreate":
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be later than period_start")
        return self


class ReportRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    report_type: str
    period_start: datetime
    period_end: datetime
    content: dict[str, Any]
    status: str
    created_at: datetime
