"""Pydantic schemas for observed events."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    Category,
    Confidence,
    DataSource,
    ObservedEventStatus,
    Severity,
    SpatialScope,
)


class CanonicalObservedEvent(BaseModel):
    """Normalized observed event before persistence."""

    model_config = ConfigDict(from_attributes=True)

    source: DataSource
    source_event_id: str
    source_url: str | None = None
    title: str
    description: str | None = None
    event_type: str | None = None
    category: Category
    severity: Severity
    status: ObservedEventStatus = ObservedEventStatus.UNKNOWN
    confidence: Confidence = Confidence.MEDIUM
    country_code: str | None = None
    region: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict[str, Any] | None = None
    spatial_scope: SpatialScope = SpatialScope.LOCAL
    affected_latitude_min: float | None = None
    affected_latitude_max: float | None = None
    issued_at: datetime
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    updated_at_source: datetime | None = None
    raw_payload: dict[str, Any]
    source_metadata: dict[str, Any] | None = None


class ObservedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: DataSource
    source_event_id: str
    source_url: str | None = None
    title: str
    description: str | None = None
    event_type: str | None = None
    category: Category
    severity: Severity
    status: ObservedEventStatus
    confidence: Confidence
    country_code: str | None = None
    region: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict[str, Any] | None = None
    spatial_scope: SpatialScope
    affected_latitude_min: float | None = None
    affected_latitude_max: float | None = None
    issued_at: datetime
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    updated_at_source: datetime | None = None
    ingested_at: datetime
    raw_payload: dict[str, Any] | None = None
    source_metadata: dict[str, Any] | None = None
    fingerprint: str
    is_active: bool
    ingest_mode: str = "live"


class ObservedEventListResponse(BaseModel):
    items: list[ObservedEventResponse]
    total: int
    limit: int
    offset: int


class ObservedEventQueryParams(BaseModel):
    source: DataSource | None = None
    event_type: str | None = None
    category: Category | None = None
    severity: Severity | None = None
    active: bool = True
    bounding_box: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    include_raw: bool = False
