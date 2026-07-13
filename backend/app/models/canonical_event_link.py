"""Canonical event link ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CanonicalEventLink(Base):
    __tablename__ = "canonical_event_links"
    __table_args__ = (
        UniqueConstraint("member_type", "member_id", name="uq_canonical_event_links_member"),
        Index("ix_canonical_event_links_event_id", "canonical_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_type: Mapped[str] = mapped_column(String(16), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    link_confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    link_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    canonical_event: Mapped["CanonicalEvent"] = relationship(
        "CanonicalEvent",
        back_populates="links",
    )
