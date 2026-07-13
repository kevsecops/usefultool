"""NOAA/NWS source adapter (fixture mode in Phase 2)."""

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.normalization.category import normalize_event_name
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.geometry import compute_centroid
from app.normalization.html_sanitizer import sanitize_html
from app.normalization.severity import normalize_cap_severity
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


class NoaaSourceAdapter:
    source_id = AlertSource.NOAA

    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_fetch = None

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        payloads: list[RawAlertPayload] = []
        for path in list_fixtures("noaa", "alerts_active_*.json"):
            data = load_fixture("noaa", path.name)
            features = data.get("features", [])
            for feature in features:
                payloads.append(RawAlertPayload(source=self.source_id, data=feature))
        self._last_fetch = utc_now()
        return payloads

    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert:
        props = raw.data.get("properties", {})
        source_alert_id = props.get("id", raw.data.get("id", ""))
        return ParsedAlert(
            source=self.source_id,
            source_alert_id=source_alert_id,
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

        area_desc = props.get("areaDesc", "")
        region = area_desc.split(",")[-1].strip() if area_desc else None

        return CanonicalAlert(
            source=AlertSource.NOAA,
            source_alert_id=parsed.source_alert_id,
            source_url=feature_id if isinstance(feature_id, str) and feature_id.startswith("http") else None,
            title=props.get("headline") or event_name or "NOAA Alert",
            description=sanitize_html(props.get("description")),
            instruction=sanitize_html(props.get("instruction")),
            country_code="US",
            country_name="United States",
            region=region,
            location_name=area_desc,
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
