"""Stats API schemas."""

from datetime import datetime

from pydantic import BaseModel


class CountryCount(BaseModel):
    code: str
    count: int


class HotspotRegion(BaseModel):
    region: str
    count: int


class StatsResponse(BaseModel):
    active_count: int
    global_risk_score: int = 0
    score_breakdown: dict[str, float | int] = {}
    by_country: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    top_countries: list[CountryCount] = []
    hotspot_regions: list[HotspotRegion] = []
    last_ingest: datetime | None = None
