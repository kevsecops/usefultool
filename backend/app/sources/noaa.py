"""NOAA/NWS source adapter — live HTTP in Phase 3, fixtures in DEMO_MODE."""

from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.category import normalize_event_name
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.geometry import compute_centroid
from app.normalization.html_sanitizer import sanitize_html
from app.normalization.severity import normalize_cap_severity
from app.normalization.strings import clamp_str
from app.schemas.alert import CanonicalAlert
from app.schemas.common import AlertSource, AlertStatus, Certainty, Urgency
from app.sources.base import ParsedAlert, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import load_fixture, list_fixtures

logger = get_logger(__name__)

_URGENCY_MAP = {
    "immediate": Urgency.IMMEDIATE,
    "expected": Urgency.EXPECTED,
    "future": Urgency.FUTURE,
    "past": Urgency.PAST,
}

_CERTAINTY_MAP = {
    "observed": Certainty.OBSERVED,
    "likely": Certainty.LIKELY,
    "possible": Certainty.POSSIBLE,
    "unlikely": Certainty.UNLIKELY,
}

_STATUS_MAP = {
    "actual": AlertStatus.ACTUAL,
    "exercise": AlertStatus.EXERCISE,
    "test": AlertStatus.TEST,
    "draft": AlertStatus.DRAFT,
}


def _noaa_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    return frozenset({host}) if host else frozenset()


def extract_noaa_features(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract GeoJSON features from NWS FeatureCollection (features or @graph)."""
    features = data.get("features")
    if isinstance(features, list):
        return [
            f
            for f in features
            if isinstance(f, dict) and (f.get("type") == "Feature" or "properties" in f)
        ]

    graph = data.get("@graph")
    if isinstance(graph, list):
        return [
            item
            for item in graph
            if isinstance(item, dict) and (item.get("type") == "Feature" or "properties" in item)
        ]

    return []


def resolve_source_url(feature: dict[str, Any], props: dict[str, Any]) -> str | None:
    """Resolve NWS alert URL from feature id or properties @id/id."""
    for candidate in (feature.get("id"), props.get("@id"), props.get("id")):
        if isinstance(candidate, str):
            if candidate.startswith("http"):
                return candidate
            if candidate.startswith("urn:"):
                return f"https://api.weather.gov/alerts/{candidate}"
    return None


def _region_from_area_desc(area_desc: str) -> str | None:
    """Derive a short region label from NOAA areaDesc (often multi-zone lists)."""
    if not area_desc:
        return None
    if "," in area_desc:
        region = area_desc.split(",")[-1].strip()
    else:
        region = area_desc.split(";")[0].strip()
    return clamp_str(region, 256)


class NoaaSourceAdapter:
    source_id = AlertSource.NOAA
    record_type = "alert"

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch = None
        self._http = http_client or HttpClient(
            user_agent=self.settings.noaa_user_agent,
            timeout_seconds=self.settings.noaa_fetch_timeout_seconds,
            max_retries=self.settings.noaa_max_retries,
            max_response_bytes=self.settings.noaa_max_response_bytes,
            allowed_hosts=_noaa_allowed_hosts(self.settings.noaa_base_url),
        )

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.noaa_use_fixtures:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "noaa" not in live_sources

    async def _fetch_from_fixtures(self) -> list[RawAlertPayload]:
        payloads: list[RawAlertPayload] = []
        for path in list_fixtures("noaa", "alerts_active_*.json"):
            data = load_fixture("noaa", path.name)
            for feature in extract_noaa_features(data):
                payloads.append(RawAlertPayload(source=self.source_id, data=feature))
        self._last_fetch = utc_now()
        return payloads

    async def _fetch_live(self) -> list[RawAlertPayload]:
        url = f"{self.settings.noaa_base_url.rstrip('/')}/alerts/active"
        pages = await self._http.get_json_paginated(url)
        features: list[dict[str, Any]] = []
        for page in pages:
            features.extend(extract_noaa_features(page))

        payloads = [RawAlertPayload(source=self.source_id, data=feature) for feature in features]
        self._last_fetch = utc_now()
        logger.info("NOAA live fetch returned %d alerts", len(payloads))
        return payloads

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            return await self._fetch_from_fixtures()

        try:
            return await self._fetch_live()
        except Exception as exc:
            if self.settings.noaa_fallback_to_fixtures and list_fixtures("noaa", "alerts_active_*.json"):
                logger.warning("NOAA live fetch failed (%s), falling back to fixtures", exc)
                return await self._fetch_from_fixtures()
            raise

    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert:
        props = raw.data.get("properties", {})
        source_alert_id = props.get("id") or raw.data.get("id", "")
        if isinstance(source_alert_id, str) and source_alert_id.startswith("http"):
            source_alert_id = source_alert_id.rsplit("/", 1)[-1]
        return ParsedAlert(
            source=self.source_id,
            source_alert_id=str(source_alert_id),
            fields={
                "properties": props,
                "geometry": raw.data.get("geometry"),
                "feature_id": raw.data.get("id"),
            },
            raw_payload=raw.data,
        )

    def normalize_alert(self, parsed: ParsedAlert) -> CanonicalAlert:
        props: dict[str, Any] = parsed.fields.get("properties", {})
        geometry = parsed.fields.get("geometry")
        feature_id = parsed.fields.get("feature_id")

        event_name = props.get("event", "")
        severity = normalize_cap_severity(props.get("severity"))
        category = normalize_event_name(event_name)

        urgency_raw = (props.get("urgency") or "").lower()
        certainty_raw = (props.get("certainty") or "").lower()
        status_raw = (props.get("status") or "actual").lower()

        issued_at = parse_datetime(props.get("sent")) or utc_now()
        lat, lon = compute_centroid(geometry)

        area_desc = props.get("areaDesc", "") or ""
        region = _region_from_area_desc(area_desc)

        source_url = resolve_source_url(
            {"id": feature_id, "properties": props},
            props,
        )

        return CanonicalAlert(
            source=AlertSource.NOAA,
            source_alert_id=parsed.source_alert_id,
            source_url=source_url,
            title=props.get("headline") or event_name or "NOAA Alert",
            description=sanitize_html(props.get("description")),
            instruction=sanitize_html(props.get("instruction")),
            country_code="US",
            country_name="United States",
            region=region,
            location_name=clamp_str(area_desc or None, 512),
            latitude=lat,
            longitude=lon,
            geometry=geometry,
            category=category,
            event_type=event_name,
            severity=severity,
            urgency=_URGENCY_MAP.get(urgency_raw, Urgency.UNKNOWN),
            certainty=_CERTAINTY_MAP.get(certainty_raw, Certainty.UNKNOWN),
            status=_STATUS_MAP.get(status_raw, AlertStatus.UNKNOWN),
            language="en-US",
            issued_at=issued_at,
            effective_at=parse_datetime(props.get("effective")),
            starts_at=parse_datetime(props.get("onset")),
            expires_at=parse_datetime(props.get("expires")),
            updated_at_source=parse_datetime(props.get("sent")),
            raw_payload=parsed.raw_payload,
        )

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        if self._use_fixtures():
            fixtures = list_fixtures("noaa", "alerts_active_*.json")
            if fixtures:
                return SourceHealth(
                    source=self.source_id,
                    is_healthy=True,
                    checked_at=now,
                    latency_ms=1,
                    last_success_at=self._last_fetch or now,
                )
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                error_message="No NOAA fixtures found",
            )

        import time

        start = time.monotonic()
        try:
            url = f"{self.settings.noaa_base_url.rstrip('/')}/alerts/active?area=DC"
            await self._http.get_json(url)
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=True,
                checked_at=now,
                latency_ms=latency_ms,
                last_success_at=self._last_fetch or now,
            )
        except (HttpClientError, Exception) as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                latency_ms=latency_ms,
                error_message=str(exc),
            )
