"""Support provider-scoped identities and general source footprints.

Revision ID: 20260701_0002
Revises: 20260630_0001
"""

from alembic import op

revision = "20260701_0002"
down_revision = "20260630_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_observation_area_source", "observations", type_="unique")
    op.create_unique_constraint(
        "uq_observation_area_provider_source",
        "observations",
        ["watch_area_id", "source", "source_item_id"],
    )
    op.execute(
        "ALTER TABLE observations ALTER COLUMN footprint "
        "TYPE geometry(GEOMETRY, 4326) USING footprint::geometry"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM observations
            WHERE GeometryType(footprint) <> 'POLYGON'
          ) THEN
            RAISE EXCEPTION 'Cannot downgrade: non-Polygon observation footprints exist';
          END IF;
        END $$
        """
    )
    op.execute(
        "ALTER TABLE observations ALTER COLUMN footprint "
        "TYPE geometry(POLYGON, 4326) USING footprint::geometry"
    )
    op.drop_constraint(
        "uq_observation_area_provider_source", "observations", type_="unique"
    )
    op.create_unique_constraint(
        "uq_observation_area_source",
        "observations",
        ["watch_area_id", "source_item_id"],
    )
