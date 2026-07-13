"""Add observed_events and source_status tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "002_observed_events"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "observed_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_event_id", sa.String(512), nullable=False),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("event_type", sa.String(256)),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("country_code", sa.String(2)),
        sa.Column("region", sa.String(256)),
        sa.Column("location_name", sa.String(512)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("geometry", Geometry(geometry_type="GEOMETRY", srid=4326)),
        sa.Column("geometry_json", postgresql.JSONB()),
        sa.Column("spatial_scope", sa.String(16), nullable=False, server_default="local"),
        sa.Column("affected_latitude_min", sa.Float()),
        sa.Column("affected_latitude_max", sa.Float()),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at_source", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB()),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.UniqueConstraint("fingerprint", name="uq_observed_events_fingerprint"),
        sa.UniqueConstraint("source", "source_event_id", name="uq_observed_events_source_id"),
    )
    op.create_index(
        "ix_observed_events_active_severity_issued",
        "observed_events",
        ["is_active", "severity", "issued_at"],
    )
    op.create_index(
        "ix_observed_events_source_category",
        "observed_events",
        ["source", "category"],
    )
    op.execute(
        "CREATE INDEX ix_observed_events_geometry ON observed_events USING GIST (geometry)"
    )

    op.create_table(
        "source_status",
        sa.Column("source", sa.String(16), primary_key=True),
        sa.Column("record_type", sa.String(32), nullable=False, server_default="alert"),
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("ingest_mode", sa.String(16)),
        sa.Column("records_fetched", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_status")
    op.drop_index("ix_observed_events_geometry", table_name="observed_events")
    op.drop_index("ix_observed_events_source_category", table_name="observed_events")
    op.drop_index("ix_observed_events_active_severity_issued", table_name="observed_events")
    op.drop_table("observed_events")
