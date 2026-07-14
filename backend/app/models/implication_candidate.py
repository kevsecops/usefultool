"""Implication candidate ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ImplicationCandidate(Base):
    __tablename__ = "implication_candidates"
    __table_args__ = (
        Index("ix_implication_candidates_event_id", "canonical_event_id"),
        Index("ix_implication_candidates_category", "category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    affected_region: Mapped[str | None] = mapped_column(String(256))
    related_asset_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    supporting_source_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    evidence_level: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    missing_data: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="rule_based")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    canonical_event: Mapped["CanonicalEvent"] = relationship("CanonicalEvent")
