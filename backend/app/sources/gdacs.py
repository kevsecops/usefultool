"""GDACS source adapter — live HTTP in Phase 7, fixtures in DEMO_MODE."""

from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.category import normalize_gdacs_event_type
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.geometry import compute_centroid
from app.normalization.html_sanitizer import sanitize_html
from app.normalization.severity import normalize_gdacs_alert_level
from app.schemas.alert import CanonicalAlert
from app.schemas.common import AlertSource, AlertStatus, Urgency
from app.sources.base import ParsedAlert, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import load_fixture, list_fixtures

logger = get_logger(__name__)

_ISO3_TO_ISO2: dict[str, str] = {
    "PNG": "PG",
    "USA": "US",
    "DEU": "DE",
    "IDN": "ID",
    "PHL": "PH",
    "JPN": "JP",
    "HND": "HN",
}


def _gdacs_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    return frozenset({host}) if host else frozenset()


def extract_gdacs_features(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract GeoJSON features from GDACS FeatureCollection."""
    features = data.get("features")
    if not isinstance(features, list):
        return []
    return [
        feature
        for feature in features
        if isinstance(feature, dict) and feature.get("type") == "Feature"
    ]


def is_current_event(props: dict[str, Any]) -> bool:
    """GDACS returns iscurrent as string 'true'/'false'."""
    return str(props.get("iscurrent", "true")).lower() == "true"


class GdacsSourceAdapter:
    source_id = AlertSource.GDACS

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch = None
        self._http = http_client or HttpClient(
            user_agent=self.settings.noaa_user_agent,
            timeout_seconds=self.settings.gdacs_fetch_timeout_seconds,
            max_retries=self.settings.gdacs_max_retries,
            max_response_bytes=self.settings.gdacs_max_response_bytes,
            allowed_hosts=_gdacs_allowed_hosts(self.settings.gdacs_base_url),
        )

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.gdacs_use_fixtures:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "gdacs" not in live_sources

    async def _fetch_from_fixtures(self) -> list[RawAlertPayload]:
        data = load_fixture("gdacs", "events4app.json")
        features = extract_gdacs_features(data)
        payloads = [
            RawAlertPayload(source=self.source_id, data=feature)
            for feature in features
            if is_current_event(feature.get("properties", {}))
        ]
        self._last_fetch = utc_now()
        return payloads

    async def _fetch_live(self) -> list[RawAlertPayload]:
        base = self.settings.gdacs_base_url.rstrip("/")
        url = f"{base}/gdacsapi/api/events/geteventlist/events4app"
        data = await self._http.get_json(url)
        features = extract_gdacs_features(data)
        current_features = [
            feature
            for feature in features
            if is_current_event(feature.get("properties", {}))
        ]
        payloads = [RawAlertPayload(source=self.source_id, data=feature) for feature in current_features]
        self._last_fetch = utc_now()
        logger.info("GDACS live fetch returned %d alerts", len(payloads))
        return payloads

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            return await self._fetch_from_fixtures()

        try:
            payloads = await self._fetch_live()
            if (
                not payloads
                and self.settings.gdacs_fallback_to_fixtures
                and list_fixtures("gdacs", "events4app.json")
            ):
                logger.warning("GDACS live fetch returned no alerts, falling back to fixtures")
                return await self._fetch_from_fixtures()
            return payloads
        except Exception as exc:
            if self.settings.gdacs_fallback_to_fixtures and list_fixtures("gdacs", "events4app.json"):
                logger.warning("GDACS live fetch failed (%s), falling back to fixtures", exc)
                return await self._fetch_from_fixtures()
            raise

    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert:
        props = raw.data.get("properties", {})
        event_type = props.get("eventtype", "")
        event_id = props.get("eventid", "")
        episode_id = props.get("episodeid", "")
        source_alert_id = f"{event_type}-{event_id}-{episode_id}"
        return ParsedAlert(
            source=self.source_id,
            source_alert_id=source_alert_id,
            fields={
                "properties": props,
                "geometry": raw.data.get("geometry"),
            },
            raw_payload=raw.data,
        )

    def normalize_alert(self, parsed: ParsedAlert) -> CanonicalAlert:
        props: dict[str, Any] = parsed.fields.get("properties", {})
        geometry = parsed.fields.get("geometry")
        event_type = props.get("eventtype", "")
        alert_score = props.get("alertscore")
        severity = normalize_gdacs_alert_level(props.get("alertlevel"), alert_score)
        category = normalize_gdacs_event_type(event_type)
        iso3 = props.get("iso3", "")
        country_code = _ISO3_TO_ISO2.get(iso3, iso3[:2] if iso3 else None)

        issued_at = parse_datetime(props.get("fromdate")) or utc_now()
        is_current = is_current_event(props)

        lat, lon = compute_centroid(geometry)
        if geometry and geometry.get("type") == "Point":
            coords = geometry.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        url_info = props.get("url", {})
        source_url = url_info.get("details") or url_info.get("report")

        return CanonicalAlert(
            source=AlertSource.GDACS,
            source_alert_id=parsed.source_alert_id,
            source_url=source_url,
            title=props.get("name", "GDACS Event"),
            description=sanitize_html(props.get("description") or props.get("htmldescription")),
            instruction=None,
            country_code=country_code,
            country_name=props.get("country"),
            region=None,
            location_name=props.get("country"),
            latitude=lat,
            longitude=lon,
            geometry=geometry,
            category=category,
            event_type=event_type,
            severity=severity,
            urgency=Urgency.UNKNOWN,
            certainty=None,
            status=AlertStatus.ACTUAL if is_current else AlertStatus.UNKNOWN,
            language="en",
            issued_at=issued_at,
            effective_at=None,
            starts_at=issued_at,
            expires_at=parse_datetime(props.get("todate")),
            updated_at_source=parse_datetime(props.get("datemodified")),
            raw_payload=parsed.raw_payload,
        )

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        if self._use_fixtures():
            fixtures = list_fixtures("gdacs", "events4app.json")
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
                error_message="No GDACS fixtures found",
            )

        import time

        start = time.monotonic()
        try:
            base = self.settings.gdacs_base_url.rstrip("/")
            url = f"{base}/gdacsapi/api/events/geteventlist/events4app"
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
