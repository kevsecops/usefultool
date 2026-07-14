"""Add implication_candidates table."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_implication_candidates"
down_revision: Union[str, None] = "004_exposure_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "implication_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "canonical_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("affected_region", sa.String(256)),
        sa.Column(
            "related_asset_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "supporting_source_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("evidence_level", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("missing_data", sa.Text()),
        sa.Column("generated_by", sa.String(16), nullable=False, server_default="rule_based"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_implication_candidates_event_id",
        "implication_candidates",
        ["canonical_event_id"],
    )
    op.create_index(
        "ix_implication_candidates_category",
        "implication_candidates",
        ["category"],
    )


def downgrade() -> None:
    op.drop_index("ix_implication_candidates_category", table_name="implication_candidates")
    op.drop_index("ix_implication_candidates_event_id", table_name="implication_candidates")
    op.drop_table("implication_candidates")
