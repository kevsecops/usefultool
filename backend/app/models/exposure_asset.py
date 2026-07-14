"""Exposure asset ORM model."""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExposureAsset(Base):
    __tablename__ = "exposure_assets"
    __table_args__ = (
        UniqueConstraint("source", "source_asset_id", name="uq_exposure_assets_source_id"),
        Index("ix_exposure_assets_asset_type", "asset_type"),
        Index("ix_exposure_assets_country_code", "country_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(256))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    importance_level: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_fixture")
    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_asset_id: Mapped[str | None] = mapped_column(String(256))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    exposures: Mapped[list["EventAssetExposure"]] = relationship(
        "EventAssetExposure",
        back_populates="asset",
        cascade="all, delete-orphan",
    )
