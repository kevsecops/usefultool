"""NASA EONET natural events source adapter — live API or fixtures."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.geometry import compute_centroid
from app.schemas.common import (
    Category,
    Confidence,
    DataSource,
    ObservedEventStatus,
    Severity,
    SpatialScope,
)
from app.schemas.observed_event import CanonicalObservedEvent
from app.sources.base import ParsedObservedEvent, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import list_fixtures, load_fixture

logger = get_logger(__name__)

_EONET_ALLOWED_HOSTS = frozenset({"eonet.gsfc.nasa.gov"})

_EONET_CATEGORY_MAP: dict[str, Category] = {
    "wildfires": Category.WILDFIRE,
    "severeStorms": Category.WEATHER,
    "volcanoes": Category.VOLCANO,
    "floods": Category.FLOOD,
    "earthquakes": Category.EARTHQUAKE,
    "landslides": Category.ENVIRONMENTAL,
    "drought": Category.ENVIRONMENTAL,
    "dustHaze": Category.ENVIRONMENTAL,
    "seaLakeIce": Category.ENVIRONMENTAL,
    "snow": Category.WEATHER,
    "tempExtremes": Category.WEATHER,
    "waterColor": Category.ENVIRONMENTAL,
    "manmade": Category.OTHER,
}

_SUPPORTED_GEOMETRY_TYPES = frozenset({"Point", "LineString", "Polygon", "MultiPolygon"})


def _eonet_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    if host and host in _EONET_ALLOWED_HOSTS:
        return frozenset({host})
    return _EONET_ALLOWED_HOSTS


def extract_eonet_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    events = data.get("events")
    if isinstance(events, list):
        return [e for e in events if isinstance(e, dict) and e.get("id")]
    return []


def map_eonet_category(categories: list[dict[str, Any]] | None) -> Category:
    if not categories:
        return Category.OTHER
    for cat in categories:
        cat_id = cat.get("id") if isinstance(cat, dict) else None
        if cat_id and cat_id in _EONET_CATEGORY_MAP:
            return _EONET_CATEGORY_MAP[cat_id]
    return Category.OTHER


def select_latest_geometry(geometry_snapshots: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Pick the most recent geometry snapshot — one event per EONET id, not per snapshot."""
    if not geometry_snapshots:
        return None
    valid = [g for g in geometry_snapshots if isinstance(g, dict) and g.get("type") in _SUPPORTED_GEOMETRY_TYPES]
    if not valid:
        return None
    valid.sort(key=lambda g: g.get("date") or "", reverse=True)
    return valid[0]


def geometry_from_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    geom_type = snapshot.get("type")
    coords = snapshot.get("coordinates")
    if not geom_type or coords is None:
        return None
    return {"type": geom_type, "coordinates": coords}


def normalize_eonet_severity(
    category: Category,
    magnitude_value: float | None,
    magnitude_unit: str | None,
) -> Severity:
    if magnitude_value is None:
        return Severity.UNKNOWN
    unit = (magnitude_unit or "").lower()
    if unit == "kts" or category == Category.WEATHER:
        if magnitude_value >= 100:
            return Severity.EXTREME
        if magnitude_value >= 75:
            return Severity.SEVERE
        if magnitude_value >= 50:
            return Severity.MODERATE
        if magnitude_value >= 34:
            return Severity.MINOR
        return Severity.UNKNOWN
    if unit == "acres" or category == Category.WILDFIRE:
        if magnitude_value >= 100_000:
            return Severity.EXTREME
        if magnitude_value >= 10_000:
            return Severity.SEVERE
        if magnitude_value >= 1_000:
            return Severity.MODERATE
        if magnitude_value >= 100:
            return Severity.MINOR
        return Severity.UNKNOWN
    if category == Category.VOLCANO:
        return Severity.MODERATE
    if category == Category.FLOOD:
        return Severity.MODERATE
    return Severity.UNKNOWN


def infer_spatial_scope(category: Category, geometry: dict[str, Any] | None) -> SpatialScope:
    if category == Category.WEATHER and geometry and geometry.get("type") == "LineString":
        return SpatialScope.REGIONAL
    if geometry and geometry.get("type") in ("Polygon", "MultiPolygon"):
        return SpatialScope.REGIONAL
    return SpatialScope.LOCAL


def build_eonet_description(
    event: dict[str, Any],
    latest_geom: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    if event.get("description"):
        parts.append(str(event["description"]))
    if latest_geom:
        mag_val = latest_geom.get("magnitudeValue")
        mag_unit = latest_geom.get("magnitudeUnit")
        if mag_val is not None and mag_unit:
            parts.append(f"Magnitude: {mag_val} {mag_unit}")
        geom_date = latest_geom.get("date")
        if geom_date:
            parts.append(f"Latest geometry: {geom_date}")
    cats = event.get("categories") or []
    if cats:
        titles = [c.get("title") for c in cats if isinstance(c, dict) and c.get("title")]
        if titles:
            parts.append(f"Categories: {', '.join(titles)}")
    return ". ".join(parts) if parts else event.get("title", "EONET natural event")


class EonetSourceAdapter:
    source_id = DataSource.EONET
    record_type = "observed_event"

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch: datetime | None = None
        self._last_ingest_mode: str | None = None
        self._http = http_client or HttpClient(
            user_agent=self.settings.eonet_user_agent,
            timeout_seconds=self.settings.eonet_fetch_timeout_seconds,
            max_retries=self.settings.eonet_max_retries,
            max_response_bytes=self.settings.eonet_max_response_bytes,
            allowed_hosts=_eonet_allowed_hosts(self.settings.eonet_base_url),
        )

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.eonet_use_fixtures:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "eonet" not in live_sources

    async def _fetch_from_fixtures(self) -> list[RawAlertPayload]:
        payloads: list[RawAlertPayload] = []
        for path in list_fixtures("eonet", "*.json"):
            data = load_fixture("eonet", path.name)
            for event in extract_eonet_events(data):
                payloads.append(
                    RawAlertPayload(
                        source=self.source_id,
                        data=event,
                        ingest_mode="fixture",
                    )
                )
        self._last_fetch = utc_now()
        self._last_ingest_mode = "fixture"
        return payloads

    async def _fetch_live(self) -> list[RawAlertPayload]:
        url = f"{self.settings.eonet_base_url.rstrip('/')}/events"
        data = await self._http.get_json(url, params={"status": "open"})
        events = extract_eonet_events(data)
        payloads = [
            RawAlertPayload(source=self.source_id, data=event, ingest_mode="live")
            for event in events
        ]
        self._last_fetch = utc_now()
        self._last_ingest_mode = "live"
        logger.info("EONET live fetch returned %d events", len(payloads))
        return payloads

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            return await self._fetch_from_fixtures()
        try:
            return await self._fetch_live()
        except Exception as exc:
            if self.settings.eonet_fallback_to_fixtures and list_fixtures("eonet", "*.json"):
                logger.warning("EONET live fetch failed (%s), falling back to fixtures", exc)
                return await self._fetch_from_fixtures()
            raise

    def parse_observed_event(self, raw: RawAlertPayload) -> ParsedObservedEvent:
        source_event_id = str(raw.data.get("id", ""))
        return ParsedObservedEvent(
            source=self.source_id,
            source_event_id=source_event_id,
            fields={"event": raw.data},
            raw_payload=raw.data,
        )

    def normalize_observed_event(self, parsed: ParsedObservedEvent) -> CanonicalObservedEvent:
        event: dict[str, Any] = parsed.fields.get("event", {})
        categories = event.get("categories") or []
        category = map_eonet_category(categories)
        latest_geom = select_latest_geometry(event.get("geometry"))
        geometry = geometry_from_snapshot(latest_geom)
        lat, lon = compute_centroid(geometry)

        geom_date = latest_geom.get("date") if latest_geom else None
        issued_at = parse_datetime(geom_date) or utc_now()
        closed = event.get("closed")
        ends_at = parse_datetime(closed) if closed else None

        cat_id = categories[0].get("id") if categories and isinstance(categories[0], dict) else None
        mag_val = latest_geom.get("magnitudeValue") if latest_geom else None
        mag_unit = latest_geom.get("magnitudeUnit") if latest_geom else None

        sources = event.get("sources") or []
        source_url = None
        if sources and isinstance(sources[0], dict):
            source_url = sources[0].get("url") or event.get("link")

        source_metadata: dict[str, Any] = {
            "eonet_id": event.get("id"),
            "eonet_categories": [c.get("id") for c in categories if isinstance(c, dict)],
            "eonet_sources": sources,
            "geometry_snapshot_count": len(event.get("geometry") or []),
            "latest_geometry_date": geom_date,
            "magnitude_value": mag_val,
            "magnitude_unit": mag_unit,
            "closed": closed,
        }

        return CanonicalObservedEvent(
            source=DataSource.EONET,
            source_event_id=parsed.source_event_id,
            source_url=source_url or event.get("link"),
            title=event.get("title") or "EONET event",
            description=build_eonet_description(event, latest_geom),
            event_type=cat_id,
            category=category,
            severity=normalize_eonet_severity(category, mag_val, mag_unit),
            status=ObservedEventStatus.REVIEWED if not closed else ObservedEventStatus.UNKNOWN,
            confidence=Confidence.HIGH,
            location_name=event.get("description"),
            latitude=lat,
            longitude=lon,
            geometry=geometry,
            spatial_scope=infer_spatial_scope(category, geometry),
            issued_at=issued_at,
            starts_at=issued_at,
            ends_at=ends_at,
            updated_at_source=issued_at,
            raw_payload=parsed.raw_payload,
            source_metadata=source_metadata,
        )

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        if self._use_fixtures():
            fixtures = list_fixtures("eonet", "*.json")
            if fixtures:
                return SourceHealth(
                    source=self.source_id,
                    is_healthy=True,
                    checked_at=now,
                    latency_ms=1,
                    last_success_at=self._last_fetch or now,
                    ingest_mode="fixture",
                )
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                error_message="No EONET fixtures found",
                ingest_mode="fixture",
            )

        import time

        start = time.monotonic()
        try:
            url = f"{self.settings.eonet_base_url.rstrip('/')}/events"
            await self._http.get_json(url, params={"status": "open", "limit": 1})
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=True,
                checked_at=now,
                latency_ms=latency_ms,
                last_success_at=self._last_fetch or now,
                ingest_mode="live",
            )
        except (HttpClientError, Exception) as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                latency_ms=latency_ms,
                error_message=str(exc),
                ingest_mode="live",
            )
