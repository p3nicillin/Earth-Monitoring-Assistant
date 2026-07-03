"""Add a non-interactive 'system' role for the global-monitoring bootstrap account.

Revision ID: 20260703_0003
Revises: 20260701_0002
"""

from alembic import op

revision = "20260703_0003"
down_revision = "20260701_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'system'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value without recreating the type and
    # remapping every dependent column. An unused extra label is harmless, so
    # this is intentionally a no-op rather than a risky type rebuild.
    pass
