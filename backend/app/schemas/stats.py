"""Stats API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class CountryCount(BaseModel):
    code: str
    count: int


class HotspotRegion(BaseModel):
    region: str
    count: int
    max_severity: str | None = None
    severe_or_extreme_count: int | None = None


class TrendAnomalyItem(BaseModel):
    dimension: str
    key: str
    current_count: int
    rolling_avg: float
    ratio: float


class StatsResponse(BaseModel):
    active_count: int
    global_risk_score: int = 0
    score_breakdown: dict = Field(default_factory=dict)
    by_country: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    top_countries: list[CountryCount] = Field(default_factory=list)
    hotspot_regions: list[HotspotRegion] = Field(default_factory=list)
    trend_anomalies: list[TrendAnomalyItem] = Field(default_factory=list)
    last_ingest: datetime | None = None
