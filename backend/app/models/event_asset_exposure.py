"""Event-to-asset exposure ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EventAssetExposure(Base):
    __tablename__ = "event_asset_exposures"
    __table_args__ = (
        UniqueConstraint("event_id", "asset_id", name="uq_event_asset_exposures_event_asset"),
        Index("ix_event_asset_exposures_event_id", "event_id"),
        Index("ix_event_asset_exposures_asset_id", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exposure_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    exposure_type: Mapped[str] = mapped_column(String(32), nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float)
    overlap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    rationale: Mapped[str | None] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")

    asset: Mapped["ExposureAsset"] = relationship("ExposureAsset", back_populates="exposures")
    canonical_event: Mapped["CanonicalEvent"] = relationship("CanonicalEvent")
