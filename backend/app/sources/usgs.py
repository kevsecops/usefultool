"""USGS earthquake source adapter — live GeoJSON feed or fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.datetime_utils import utc_now
from app.normalization.fingerprint import generate_observed_event_fingerprint
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
from app.sources.fixture_loader import list_fixtures, load_fixture, refresh_usgs_fixture

logger = get_logger(__name__)

_USGS_ALLOWED_HOSTS = frozenset({"earthquake.usgs.gov"})

_STATUS_MAP = {
    "automatic": ObservedEventStatus.AUTOMATIC,
    "reviewed": ObservedEventStatus.REVIEWED,
    "deleted": ObservedEventStatus.DELETED,
}

_PAGER_SEVERITY = {
    "green": Severity.MINOR,
    "yellow": Severity.MODERATE,
    "orange": Severity.SEVERE,
    "red": Severity.EXTREME,
}

_SEVERITY_ORDER = [
    Severity.UNKNOWN,
    Severity.MINOR,
    Severity.MODERATE,
    Severity.SEVERE,
    Severity.EXTREME,
]


def _usgs_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    if host and host in _USGS_ALLOWED_HOSTS:
        return frozenset({host})
    return _USGS_ALLOWED_HOSTS


def parse_usgs_timestamp(value: int | float | None) -> datetime | None:
    """Parse USGS millisecond epoch timestamps."""
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def extract_usgs_features(data: dict[str, Any]) -> list[dict[str, Any]]:
    features = data.get("features")
    if isinstance(features, list):
        return [f for f in features if isinstance(f, dict) and f.get("type") == "Feature"]
    return []


def normalize_usgs_severity(props: dict[str, Any]) -> Severity:
    """Severity from PAGER alert level, significance, and tsunami — not magnitude alone."""
    alert = (props.get("alert") or "").lower()
    sig = props.get("sig") or 0
    tsunami = bool(props.get("tsunami"))

    if alert in _PAGER_SEVERITY:
        base = _PAGER_SEVERITY[alert]
    elif sig >= 600:
        base = Severity.EXTREME
    elif sig >= 400:
        base = Severity.SEVERE
    elif sig >= 200:
        base = Severity.MODERATE
    elif sig >= 40:
        base = Severity.MINOR
    else:
        base = Severity.UNKNOWN

    if tsunami and base != Severity.EXTREME:
        idx = _SEVERITY_ORDER.index(base)
        base = _SEVERITY_ORDER[min(idx + 1, len(_SEVERITY_ORDER) - 1)]

    return base


def normalize_usgs_confidence(props: dict[str, Any]) -> Confidence:
    status = (props.get("status") or "").lower()
    mag = props.get("mag")
    if status == "reviewed":
        return Confidence.HIGH
    if isinstance(mag, (int, float)) and mag >= 4.0:
        return Confidence.MEDIUM
    return Confidence.LOW


def build_usgs_description(props: dict[str, Any]) -> str:
    parts: list[str] = []
    mag = props.get("mag")
    if mag is not None:
        parts.append(f"Magnitude {mag}")
    depth = None
    if props.get("geometry") and isinstance(props["geometry"], dict):
        coords = props["geometry"].get("coordinates")
        if isinstance(coords, list) and len(coords) >= 3:
            depth = coords[2]
    if depth is not None:
        parts.append(f"depth {depth:.1f} km")
    if props.get("alert"):
        parts.append(f"PAGER alert: {props['alert']}")
    if props.get("sig") is not None:
        parts.append(f"significance {props['sig']}")
    if props.get("tsunami"):
        parts.append("tsunami flag set")
    if props.get("felt"):
        parts.append(f"felt reports: {props['felt']}")
    place = props.get("place")
    if place:
        parts.append(f"location: {place}")
    return ". ".join(parts) if parts else props.get("title", "USGS earthquake")


def flatten_point_geometry(geojson: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip Z dimension from Point geometries for 2D PostGIS columns."""
    if not geojson or geojson.get("type") != "Point":
        return geojson
    coords = geojson.get("coordinates")
    if isinstance(coords, list) and len(coords) >= 2:
        return {"type": "Point", "coordinates": [coords[0], coords[1]]}
    return geojson


class UsgsSourceAdapter:
    source_id = DataSource.USGS
    record_type = "observed_event"

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch: datetime | None = None
        self._last_ingest_mode: str | None = None
        self._http = http_client or HttpClient(
            user_agent=self.settings.usgs_user_agent,
            timeout_seconds=self.settings.usgs_fetch_timeout_seconds,
            max_retries=self.settings.usgs_max_retries,
            max_response_bytes=self.settings.usgs_max_response_bytes,
            allowed_hosts=_usgs_allowed_hosts(self.settings.usgs_base_url),
        )

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.usgs_use_fixtures:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "usgs" not in live_sources

    async def _fetch_from_fixtures(self) -> list[RawAlertPayload]:
        payloads: list[RawAlertPayload] = []
        for path in list_fixtures("usgs", "*.geojson"):
            data = refresh_usgs_fixture(load_fixture("usgs", path.name))
            for feature in extract_usgs_features(data):
                payloads.append(
                    RawAlertPayload(
                        source=self.source_id,
                        data=feature,
                        ingest_mode="fixture",
                    )
                )
        self._last_fetch = utc_now()
        self._last_ingest_mode = "fixture"
        return payloads

    async def _fetch_live(self) -> list[RawAlertPayload]:
        url = f"{self.settings.usgs_base_url.rstrip('/')}/summary/all_day.geojson"
        data = await self._http.get_json(url)
        features = extract_usgs_features(data)
        payloads = [
            RawAlertPayload(source=self.source_id, data=feature, ingest_mode="live")
            for feature in features
        ]
        self._last_fetch = utc_now()
        self._last_ingest_mode = "live"
        logger.info("USGS live fetch returned %d events", len(payloads))
        return payloads

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            return await self._fetch_from_fixtures()
        try:
            return await self._fetch_live()
        except Exception as exc:
            if self.settings.usgs_fallback_to_fixtures and list_fixtures("usgs", "*.geojson"):
                logger.warning("USGS live fetch failed (%s), falling back to fixtures", exc)
                return await self._fetch_from_fixtures()
            raise

    def parse_observed_event(self, raw: RawAlertPayload) -> ParsedObservedEvent:
        props = raw.data.get("properties", {})
        source_event_id = str(raw.data.get("id") or props.get("code", ""))
        return ParsedObservedEvent(
            source=self.source_id,
            source_event_id=source_event_id,
            fields={
                "properties": props,
                "geometry": raw.data.get("geometry"),
            },
            raw_payload=raw.data,
        )

    def normalize_observed_event(self, parsed: ParsedObservedEvent) -> CanonicalObservedEvent:
        props: dict[str, Any] = parsed.fields.get("properties", {})
        raw_geometry = parsed.fields.get("geometry")
        geometry = flatten_point_geometry(raw_geometry)

        issued_at = parse_usgs_timestamp(props.get("time")) or utc_now()
        updated_at_source = parse_usgs_timestamp(props.get("updated"))
        lat, lon = compute_centroid(geometry)

        severity = normalize_usgs_severity(props)
        confidence = normalize_usgs_confidence(props)
        status_raw = (props.get("status") or "unknown").lower()

        mag = props.get("mag")
        title = props.get("title") or (
            f"M {mag} earthquake" if mag is not None else "USGS earthquake"
        )

        depth_km = None
        if isinstance(raw_geometry, dict):
            coords = raw_geometry.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 3:
                depth_km = coords[2]

        source_metadata = {
            "magnitude": mag,
            "mag_type": props.get("magType"),
            "depth_km": depth_km,
            "alert": props.get("alert"),
            "significance": props.get("sig"),
            "tsunami": props.get("tsunami"),
            "felt": props.get("felt"),
            "cdi": props.get("cdi"),
            "mmi": props.get("mmi"),
            "net": props.get("net"),
            "status": props.get("status"),
            "detail_url": props.get("detail"),
        }

        return CanonicalObservedEvent(
            source=DataSource.USGS,
            source_event_id=parsed.source_event_id,
            source_url=props.get("url"),
            title=title,
            description=build_usgs_description({**props, "geometry": raw_geometry}),
            event_type=props.get("type") or "earthquake",
            category=Category.EARTHQUAKE,
            severity=severity,
            status=_STATUS_MAP.get(status_raw, ObservedEventStatus.UNKNOWN),
            confidence=confidence,
            location_name=props.get("place"),
            latitude=lat,
            longitude=lon,
            geometry=geometry,
            spatial_scope=SpatialScope.LOCAL,
            issued_at=issued_at,
            starts_at=issued_at,
            updated_at_source=updated_at_source,
            raw_payload=parsed.raw_payload,
            source_metadata=source_metadata,
        )

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        if self._use_fixtures():
            fixtures = list_fixtures("usgs", "*.geojson")
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
                error_message="No USGS fixtures found",
                ingest_mode="fixture",
            )

        import time

        start = time.monotonic()
        try:
            url = f"{self.settings.usgs_base_url.rstrip('/')}/summary/all_day.geojson"
            await self._http.get_json(url)
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
