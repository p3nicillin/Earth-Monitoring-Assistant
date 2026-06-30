import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


JSONType = JSON().with_variant(JSONB(), "postgresql")


class Role(StrEnum):
    viewer = "viewer"
    analyst = "analyst"
    admin = "admin"


class EventCategory(StrEnum):
    environment = "environment"
    agriculture = "agriculture"
    urban = "urban"
    infrastructure = "infrastructure"
    disaster = "disaster"
    maritime = "maritime"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class JobStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ReviewOutcome(StrEnum):
    unreviewed = "unreviewed"
    confirmed = "confirmed"
    rejected = "rejected"
    uncertain = "uncertain"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.analyst)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(7), default="#4ade80")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[User] = relationship(back_populates="projects")
    watch_areas: Mapped[list["WatchArea"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(back_populates="project")


class WatchArea(TimestampMixin, Base):
    __tablename__ = "watch_areas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    geometry: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True))
    categories: Mapped[list[str]] = mapped_column(JSONType, default=list)
    schedule: Mapped[str] = mapped_column(String(64), default="daily")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="watch_areas")
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="watch_area", cascade="all, delete-orphan"
    )


class Observation(TimestampMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("watch_area_id", "source_item_id", name="uq_observation_area_source"),
        CheckConstraint(
            "cloud_cover IS NULL OR (cloud_cover >= 0 AND cloud_cover <= 100)",
            name="ck_observation_cloud_cover",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watch_area_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_areas.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(80))
    source_item_id: Mapped[str] = mapped_column(String(255))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cloud_cover: Mapped[float | None] = mapped_column(Float)
    footprint: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326))
    assets: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.completed)

    watch_area: Mapped[WatchArea] = relationship(back_populates="observations")
    events: Mapped[list["Event"]] = relationship(back_populates="observation")


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_event_confidence"),
        CheckConstraint("area_sq_km IS NULL OR area_sq_km >= 0", name="ck_event_area"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observations.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory), index=True)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    geometry: Mapped[Any] = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=True))
    area_sq_km: Mapped[float | None] = mapped_column(Float)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    detector_name: Mapped[str] = mapped_column(String(120))
    detector_version: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_outcome: Mapped[ReviewOutcome] = mapped_column(
        Enum(ReviewOutcome), default=ReviewOutcome.unreviewed
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="events")
    observation: Mapped[Observation | None] = relationship(back_populates="events")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (CheckConstraint("period_end > period_start", name="ck_report_period"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    report_type: Mapped[str] = mapped_column(String(80), default="executive")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content: Mapped[dict[str, Any]] = mapped_column(JSONType)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.completed)


Index("ix_events_project_detected", Event.project_id, Event.detected_at.desc())
Index("ix_observations_watch_captured", Observation.watch_area_id, Observation.captured_at.desc())
