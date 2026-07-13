"""GDACS source adapter (fixture mode in Phase 2)."""

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.normalization.category import normalize_gdacs_event_type
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.geometry import compute_centroid
from app.normalization.html_sanitizer import sanitize_html
from app.normalization.severity import normalize_gdacs_alert_level
from app.schemas.alert import CanonicalAlert
from app.schemas.common import AlertSource, AlertStatus, Category, Urgency
from app.sources.base import ParsedAlert, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import load_fixture

logger = get_logger(__name__)

_ISO3_TO_ISO2: dict[str, str] = {
    "PNG": "PG",
    "USA": "US",
    "DEU": "DE",
    "IDN": "ID",
    "PHL": "PH",
    "JPN": "JP",
}


class GdacsSourceAdapter:
    source_id = AlertSource.GDACS

    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_fetch = None

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        data = load_fixture("gdacs", "events4app.json")
        features = data.get("features", [])
        payloads = [
            RawAlertPayload(source=self.source_id, data=feature)
            for feature in features
        ]
        self._last_fetch = utc_now()
        return payloads

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
        is_current = str(props.get("iscurrent", "true")).lower() == "true"

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
        try:
            load_fixture("gdacs", "events4app.json")
            return SourceHealth(
                source=self.source_id,
                is_healthy=True,
                checked_at=now,
                latency_ms=1,
                last_success_at=self._last_fetch or now,
            )
        except FileNotFoundError as exc:
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                error_message=str(exc),
            )
