"""Initial schema with PostGIS."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_alert_id", sa.String(512), nullable=False),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("instruction", sa.Text()),
        sa.Column("country_code", sa.String(2)),
        sa.Column("country_name", sa.String(128)),
        sa.Column("region", sa.String(256)),
        sa.Column("location_name", sa.String(512)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("geometry", Geometry(geometry_type="GEOMETRY", srid=4326)),
        sa.Column("geometry_json", postgresql.JSONB()),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(256)),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("urgency", sa.String(16)),
        sa.Column("certainty", sa.String(16)),
        sa.Column("status", sa.String(16), nullable=False, server_default="actual"),
        sa.Column("language", sa.String(16)),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at_source", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.UniqueConstraint("fingerprint", name="uq_alerts_fingerprint"),
        sa.UniqueConstraint("source", "source_alert_id", name="uq_alerts_source_id"),
    )
    op.create_index("ix_alerts_active_severity_issued", "alerts", ["is_active", "severity", "issued_at"])
    op.create_index("ix_alerts_country_category", "alerts", ["country_code", "category"])
    op.execute(
        "CREATE INDEX ix_alerts_geometry ON alerts USING GIST (geometry)"
    )

    op.create_table(
        "ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("alerts_fetched", sa.Integer(), server_default="0"),
        sa.Column("alerts_created", sa.Integer(), server_default="0"),
        sa.Column("alerts_updated", sa.Integer(), server_default="0"),
        sa.Column("alerts_deactivated", sa.Integer(), server_default="0"),
        sa.Column("errors", postgresql.JSONB()),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
    )

    op.create_table(
        "briefings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("overall_risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_confidence", sa.String(16), nullable=False, server_default="low"),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("source_alert_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("llm_model", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("briefings")
    op.drop_table("ingest_runs")
    op.drop_index("ix_alerts_geometry", table_name="alerts")
    op.drop_index("ix_alerts_country_category", table_name="alerts")
    op.drop_index("ix_alerts_active_severity_issued", table_name="alerts")
    op.drop_table("alerts")
