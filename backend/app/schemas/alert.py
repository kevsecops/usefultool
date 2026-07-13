"""Pydantic alert schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    AlertSource,
    AlertStatus,
    Category,
    Certainty,
    Severity,
    Urgency,
)


class CanonicalAlert(BaseModel):
    """Normalized alert before persistence."""

    model_config = ConfigDict(from_attributes=True)

    source: AlertSource
    source_alert_id: str
    source_url: str | None = None
    title: str
    description: str | None = None
    instruction: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict[str, Any] | None = None
    category: Category
    event_type: str | None = None
    severity: Severity
    urgency: Urgency | None = None
    certainty: Certainty | None = None
    status: AlertStatus = AlertStatus.ACTUAL
    language: str | None = None
    issued_at: datetime
    effective_at: datetime | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    updated_at_source: datetime | None = None
    raw_payload: dict[str, Any]


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: AlertSource
    source_alert_id: str
    source_url: str | None = None
    title: str
    description: str | None = None
    instruction: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict[str, Any] | None = None
    category: Category
    event_type: str | None = None
    severity: Severity
    urgency: Urgency | None = None
    certainty: Certainty | None = None
    status: AlertStatus
    language: str | None = None
    issued_at: datetime
    effective_at: datetime | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    updated_at_source: datetime | None = None
    ingested_at: datetime
    last_seen_at: datetime
    raw_payload: dict[str, Any] | None = None
    fingerprint: str
    is_active: bool
    ingest_mode: str = "live"


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    limit: int
    offset: int


class AlertQueryParams(BaseModel):
    source: AlertSource | None = None
    country: str | None = None
    category: Category | None = None
    severity: Severity | None = None
    active: bool = True
    issued_after: datetime | None = None
    issued_before: datetime | None = None
    bounding_box: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    include_raw: bool = False
