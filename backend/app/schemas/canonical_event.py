"""Pydantic schemas for canonical events."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Category, Confidence, Severity, SpatialScope


MemberType = Literal["alert", "observed_event"]
LinkConfidence = Literal["high", "medium", "low"]


class CanonicalEventMemberSummary(BaseModel):
    member_type: MemberType
    member_id: UUID
    link_confidence: LinkConfidence
    link_reason: str | None = None
    source: str | None = None
    title: str | None = None


class CanonicalEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str | None = None
    title: str
    status: str
    severity: Severity
    geometry: dict[str, Any] | None = None
    spatial_scope: SpatialScope
    started_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None
    confidence: Confidence
    primary_source_id: UUID | None = None
    correlation_reason: str | None = None
    correlation_version: str
    is_active: bool
    member_count: int = 0
    members: list[CanonicalEventMemberSummary] = Field(default_factory=list)


class CanonicalEventListResponse(BaseModel):
    items: list[CanonicalEventResponse]
    total: int
    limit: int
    offset: int


class CanonicalEventQueryParams(BaseModel):
    event_type: str | None = None
    severity: Severity | None = None
    status: str | None = None
    active: bool | None = True
    bounding_box: str | None = None
    limit: int = 50
    offset: int = 0


class CanonicalEventSourcesResponse(BaseModel):
    canonical_event_id: UUID
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    observed_events: list[dict[str, Any]] = Field(default_factory=list)


class CorrelateEventsResponse(BaseModel):
    canonical_events_created: int
    canonical_events_updated: int
    links_created: int
    possible_matches: int
    members_processed: int
