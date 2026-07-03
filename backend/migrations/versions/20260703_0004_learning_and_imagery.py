"""Adaptive-learning metric archive, self-scored forecasts, and the space
imagery capture catalogue.

Revision ID: 20260703_0004
Revises: 20260703_0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260703_0004"
down_revision = "20260703_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_samples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("metric", sa.String(80), nullable=False, index=True),
        sa.Column("time_tag", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("metric", "time_tag", name="uq_metric_sample"),
    )
    op.create_index(
        "ix_metric_samples_metric_time",
        "metric_samples",
        ["metric", sa.text("time_tag DESC")],
    )
    op.create_table(
        "metric_forecasts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("metric", sa.String(80), nullable=False, index=True),
        sa.Column("model_name", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("abs_error", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "imagery_captures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_key", sa.String(80), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("upstream_url", sa.String(500), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("metadata_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_key", "content_hash", name="uq_imagery_capture_hash"),
    )
    op.create_index(
        "ix_imagery_captures_source_captured",
        "imagery_captures",
        ["source_key", sa.text("captured_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_imagery_captures_source_captured", table_name="imagery_captures")
    op.drop_table("imagery_captures")
    op.drop_table("metric_forecasts")
    op.drop_index("ix_metric_samples_metric_time", table_name="metric_samples")
    op.drop_table("metric_samples")
