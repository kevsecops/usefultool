"""Add exposure_assets and event_asset_exposures tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "004_exposure_assets"
down_revision: Union[str, None] = "003_canonical_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exposure_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("country_code", sa.String(2)),
        sa.Column("region", sa.String(256)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("geometry", Geometry(geometry_type="POINT", srid=4326)),
        sa.Column("importance_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("source", sa.String(64), nullable=False, server_default="demo_fixture"),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("source_asset_id", sa.String(256)),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "source",
            "source_asset_id",
            name="uq_exposure_assets_source_id",
        ),
    )
    op.create_index("ix_exposure_assets_asset_type", "exposure_assets", ["asset_type"])
    op.create_index("ix_exposure_assets_country_code", "exposure_assets", ["country_code"])
    op.execute(
        "CREATE INDEX ix_exposure_assets_geometry ON exposure_assets USING GIST (geometry)"
    )

    op.create_table(
        "event_asset_exposures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exposure_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exposure_type", sa.String(32), nullable=False),
        sa.Column("distance_km", sa.Float()),
        sa.Column("overlap", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("rationale", sa.Text()),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("analysis_version", sa.String(16), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "event_id",
            "asset_id",
            name="uq_event_asset_exposures_event_asset",
        ),
    )
    op.create_index(
        "ix_event_asset_exposures_event_id",
        "event_asset_exposures",
        ["event_id"],
    )
    op.create_index(
        "ix_event_asset_exposures_asset_id",
        "event_asset_exposures",
        ["asset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_asset_exposures_asset_id", table_name="event_asset_exposures")
    op.drop_index("ix_event_asset_exposures_event_id", table_name="event_asset_exposures")
    op.drop_table("event_asset_exposures")
    op.drop_index("ix_exposure_assets_geometry", table_name="exposure_assets")
    op.drop_index("ix_exposure_assets_country_code", table_name="exposure_assets")
    op.drop_index("ix_exposure_assets_asset_type", table_name="exposure_assets")
    op.drop_table("exposure_assets")
