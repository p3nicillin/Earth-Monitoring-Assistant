"""Initial auditable monitoring schema.

Revision ID: 20260630_0001
Revises:
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260630_0001"
down_revision = None
branch_labels = None
depends_on = None

role_enum = postgresql.ENUM("viewer", "analyst", "admin", name="role", create_type=False)
category_enum = postgresql.ENUM(
    "environment",
    "agriculture",
    "urban",
    "infrastructure",
    "disaster",
    "maritime",
    name="eventcategory",
    create_type=False,
)
severity_enum = postgresql.ENUM(
    "low", "medium", "high", "critical", name="severity", create_type=False
)
status_enum = postgresql.ENUM(
    "queued", "processing", "completed", "failed", name="jobstatus", create_type=False
)
review_enum = postgresql.ENUM(
    "unreviewed",
    "confirmed",
    "rejected",
    "uncertain",
    name="reviewoutcome",
    create_type=False,
)


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for enum_type in (role_enum, category_enum, severity_enum, status_enum, review_enum):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "watch_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schedule", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_watch_areas_geometry",
        "watch_areas",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
    )

    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("watch_area_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_item_id", sa.String(length=255), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cloud_cover", sa.Float(), nullable=True),
        sa.Column(
            "footprint",
            geoalchemy2.Geometry("POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("assets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "cloud_cover IS NULL OR (cloud_cover >= 0 AND cloud_cover <= 100)",
            name="ck_observation_cloud_cover",
        ),
        sa.ForeignKeyConstraint(["watch_area_id"], ["watch_areas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watch_area_id", "source_item_id", name="uq_observation_area_source"),
    )
    op.create_index("ix_observations_captured_at", "observations", ["captured_at"])
    op.create_index(
        "idx_observations_footprint",
        "observations",
        ["footprint"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_observations_watch_captured",
        "observations",
        ["watch_area_id", sa.text("captured_at DESC")],
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("category", category_enum, nullable=False),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("area_sq_km", sa.Float(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detector_name", sa.String(length=120), nullable=False),
        sa.Column("detector_version", sa.String(length=40), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_reviewed", sa.Boolean(), nullable=False),
        sa.Column("review_outcome", review_enum, nullable=False),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("area_sq_km IS NULL OR area_sq_km >= 0", name="ck_event_area"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_event_confidence"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_category", "events", ["category"])
    op.create_index("ix_events_detected_at", "events", ["detected_at"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_severity", "events", ["severity"])
    op.create_index(
        "ix_events_project_detected",
        "events",
        ["project_id", sa.text("detected_at DESC")],
    )
    op.create_index(
        "idx_events_geometry", "events", ["geometry"], unique=False, postgresql_using="gist"
    )

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("report_type", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        *timestamps(),
        sa.CheckConstraint("period_end > period_start", name="ck_report_period"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("reports")
    op.drop_table("events")
    op.drop_table("observations")
    op.drop_table("watch_areas")
    op.drop_table("projects")
    op.drop_table("users")
    for enum_type in (review_enum, status_enum, severity_enum, category_enum, role_enum):
        enum_type.drop(bind, checkfirst=True)
