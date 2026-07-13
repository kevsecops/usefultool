"""Add canonical_events and canonical_event_links tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "003_canonical_events"
down_revision: Union[str, None] = "002_observed_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(256)),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("geometry", Geometry(geometry_type="GEOMETRY", srid=4326)),
        sa.Column("geometry_json", postgresql.JSONB()),
        sa.Column("spatial_scope", sa.String(16), nullable=False, server_default="local"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("primary_source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correlation_reason", sa.Text()),
        sa.Column("correlation_version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index(
        "ix_canonical_events_active_severity_started",
        "canonical_events",
        ["is_active", "severity", "started_at"],
    )
    op.create_index(
        "ix_canonical_events_event_type",
        "canonical_events",
        ["event_type"],
    )
    op.execute(
        "CREATE INDEX ix_canonical_events_geometry ON canonical_events USING GIST (geometry)"
    )

    op.create_table(
        "canonical_event_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "canonical_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_type", sa.String(16), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_confidence", sa.String(16), nullable=False),
        sa.Column("link_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "member_type",
            "member_id",
            name="uq_canonical_event_links_member",
        ),
    )
    op.create_index(
        "ix_canonical_event_links_event_id",
        "canonical_event_links",
        ["canonical_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_canonical_event_links_event_id", table_name="canonical_event_links")
    op.drop_table("canonical_event_links")
    op.drop_index("ix_canonical_events_geometry", table_name="canonical_events")
    op.drop_index("ix_canonical_events_event_type", table_name="canonical_events")
    op.drop_index("ix_canonical_events_active_severity_started", table_name="canonical_events")
    op.drop_table("canonical_events")
