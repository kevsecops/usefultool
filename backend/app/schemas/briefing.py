"""Briefing API schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AffectedRegion(BaseModel):
    region: str
    alert_count: int
    max_severity: str
    alert_ids: list[str] = Field(default_factory=list)


class SourceCount(BaseModel):
    source: str
    label: str
    count: int


class CountryCount(BaseModel):
    code: str
    count: int


class MajorEvent(BaseModel):
    title: str
    severity: str
    source: str
    category: str | None = None
    region: str | None = None
    alert_id: str


class CrossBorderPattern(BaseModel):
    type: str
    description: str
    alert_ids: list[str] = Field(default_factory=list)
    confidence: str = "low"


class TrendAnomalyItem(BaseModel):
    dimension: str
    key: str
    current_count: int
    rolling_avg: float
    ratio: float


class PotentialImplications(BaseModel):
    economy: list[str] = Field(default_factory=list)
    logistics: list[str] = Field(default_factory=list)
    infrastructure: list[str] = Field(default_factory=list)
    technology: list[str] = Field(default_factory=list)
    finance: list[str] = Field(default_factory=list)


class BriefingContent(BaseModel):
    generated_at: str
    type: str = "rule_based"
    active_count: int = 0
    overall_risk_score: int = 0
    summary: str = ""
    overall_confidence: str = "low"
    by_source: list[SourceCount] = Field(default_factory=list)
    top_countries: list[CountryCount] = Field(default_factory=list)
    affected_regions: list[AffectedRegion] = Field(default_factory=list)
    major_events: list[MajorEvent] = Field(default_factory=list)
    cross_border_patterns: list[CrossBorderPattern] = Field(default_factory=list)
    trend_anomalies: list[TrendAnomalyItem] = Field(default_factory=list)
    potential_implications: PotentialImplications = Field(default_factory=PotentialImplications)
    limitations: list[str] = Field(default_factory=list)
    source_alert_ids: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)


class BriefingResponse(BaseModel):
    id: UUID
    generated_at: datetime
    type: str
    overall_risk_score: int
    overall_confidence: str
    content: BriefingContent
    source_alert_ids: list[UUID] = Field(default_factory=list)
    llm_model: str | None = None


class BriefingListResponse(BaseModel):
    items: list[BriefingResponse]
    total: int
    limit: int
    offset: int


class GenerateBriefingRequest(BaseModel):
    type: str = "auto"


class GenerateBriefingResponse(BaseModel):
    briefing_id: str
    type: str
    overall_risk_score: int
    generated_at: datetime
