"""Source health service."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ingest_run import IngestRun
from app.schemas.sources import SourceInfo, SourcesResponse
from app.sources.registry import get_adapters

_SOURCE_NAMES = {
    "nina": "NINA/BBK Germany (MoWaS + DWD)",
    "gdacs": "GDACS International",
    "noaa": "NOAA/NWS USA",
    "usgs": "USGS Earthquakes",
}


async def get_sources(db: Session) -> SourcesResponse:
    adapters = get_adapters()
    sources: list[SourceInfo] = []
    for adapter in adapters:
        health = await adapter.health_check()
        last_fetch = db.scalar(
            select(func.max(IngestRun.finished_at)).where(
                IngestRun.source.contains(adapter.source_id)
                | (IngestRun.source == "all")
            )
        )
        sources.append(
            SourceInfo(
                id=adapter.source_id,
                name=_SOURCE_NAMES.get(adapter.source_id, adapter.source_id),
                healthy=health.is_healthy,
                last_fetch=last_fetch or health.last_success_at,
                ingest_mode=health.ingest_mode,
                alerts_fetched=health.alerts_fetched,
            )
        )
    return SourcesResponse(sources=sources)
