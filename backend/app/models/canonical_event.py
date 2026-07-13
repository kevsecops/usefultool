"""Canonical event ORM model."""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CanonicalEvent(Base):
    __tablename__ = "canonical_events"
    __table_args__ = (
        Index("ix_canonical_events_active_severity_started", "is_active", "severity", "started_at"),
        Index("ix_canonical_events_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    geometry = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)
    geometry_json: Mapped[dict | None] = mapped_column(JSONB)
    spatial_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    primary_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    correlation_reason: Mapped[str | None] = mapped_column(Text)
    correlation_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    links: Mapped[list["CanonicalEventLink"]] = relationship(
        "CanonicalEventLink",
        back_populates="canonical_event",
        cascade="all, delete-orphan",
    )
