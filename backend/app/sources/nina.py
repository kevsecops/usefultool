"""NINA source adapter (MoWaS + DWD, fixture mode in Phase 2)."""

from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.normalization.category import normalize_nina_event_code
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.fingerprint import generate_fingerprint
from app.normalization.geometry import compute_centroid
from app.normalization.html_sanitizer import sanitize_html
from app.normalization.severity import normalize_cap_severity
from app.schemas.alert import CanonicalAlert
from app.schemas.common import AlertSource, AlertStatus, Category, Certainty, Urgency
from app.sources.base import ParsedAlert, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import load_fixture, load_geojson

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


class NinaSourceAdapter:
    source_id = AlertSource.NINA

    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_fetch: datetime | None = None

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        payloads: list[RawAlertPayload] = []
        for feed in ("mapdata_mowas.json", "mapdata_dwd.json"):
            try:
                items = load_fixture("nina", feed)
            except FileNotFoundError:
                logger.warning("NINA fixture missing: %s", feed)
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                alert_id = item.get("id", "")
                detail = self._load_detail(alert_id)
                geometry = self._load_geometry(alert_id)
                payloads.append(
                    RawAlertPayload(
                        source=self.source_id,
                        data=item,
                        detail=detail,
                        geometry=geometry,
                    )
                )
        self._last_fetch = utc_now()
        return payloads

    def _load_detail(self, alert_id: str) -> dict[str, Any] | None:
        safe_id = alert_id.replace(".", "_").replace("/", "_")
        try:
            return load_fixture("nina", f"warning_detail_{safe_id}.json")
        except FileNotFoundError:
            try:
                return load_fixture("nina", "warning_detail_flood.json")
            except FileNotFoundError:
                return None

    def _load_geometry(self, alert_id: str) -> dict[str, Any] | None:
        safe_id = alert_id.replace(".", "_").replace("/", "_")
        try:
            geo = load_geojson("nina", f"warning_geo_{safe_id}.geojson")
            features = geo.get("features", [])
            if features:
                return features[0].get("geometry")
            return None
        except FileNotFoundError:
            try:
                geo = load_geojson("nina", "warning_geo_flood.geojson")
                features = geo.get("features", [])
                if features:
                    return features[0].get("geometry")
            except FileNotFoundError:
                return None
        return None

    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert:
        detail = raw.detail or {}
        info_list = detail.get("info", [])
        info = info_list[0] if info_list else {}
        return ParsedAlert(
            source=self.source_id,
            source_alert_id=raw.data.get("id", detail.get("identifier", "")),
            fields={
                "compact": raw.data,
                "detail": detail,
                "info": info,
                "geometry": raw.geometry,
            },
            raw_payload={"compact": raw.data, "detail": detail, "geometry": raw.geometry},
        )

    def normalize_alert(self, parsed: ParsedAlert) -> CanonicalAlert:
        compact = parsed.fields.get("compact", {})
        detail = parsed.fields.get("detail", {})
        info = parsed.fields.get("info", {})
        geometry = parsed.fields.get("geometry")

        title_obj = compact.get("i18nTitle") or info.get("headline") or {}
        title = title_obj.get("de") or title_obj.get("en") or compact.get("id", "NINA Alert")

        event_code = (compact.get("transKeys") or {}).get("event", "")
        category = normalize_nina_event_code(event_code)
        if category == Category.OTHER and info.get("category"):
            cats = info.get("category", [])
            if isinstance(cats, list) and cats:
                from app.normalization.category import normalize_cap_category

                category = normalize_cap_category(cats[0])

        severity = normalize_cap_severity(info.get("severity") or compact.get("severity"))
        urgency_raw = (info.get("urgency") or compact.get("urgency") or "").lower()
        certainty_raw = (info.get("certainty") or "").lower()
        status_raw = (detail.get("status") or "actual").lower()

        issued_at = parse_datetime(detail.get("sent")) or parse_datetime(compact.get("startDate"))
        if not issued_at:
            issued_at = utc_now()

        lat, lon = compute_centroid(geometry)

        return CanonicalAlert(
            source=AlertSource.NINA,
            source_alert_id=parsed.source_alert_id,
            source_url=f"{self.settings.nina_base_url}/warnings/{parsed.source_alert_id}.json",
            title=title,
            description=sanitize_html(info.get("description")),
            instruction=sanitize_html(info.get("instruction")),
            country_code="DE",
            country_name="Germany",
            region=None,
            location_name=(info.get("area", [{}])[0].get("areaDesc") if info.get("area") else None),
            latitude=lat,
            longitude=lon,
            geometry=geometry,
            category=category,
            event_type=event_code or info.get("event"),
            severity=severity,
            urgency=_URGENCY_MAP.get(urgency_raw, Urgency.UNKNOWN),
            certainty=_CERTAINTY_MAP.get(certainty_raw, Certainty.UNKNOWN),
            status=_STATUS_MAP.get(status_raw, AlertStatus.UNKNOWN),
            language="de",
            issued_at=issued_at,
            effective_at=parse_datetime(info.get("effective")),
            starts_at=parse_datetime(info.get("onset")),
            expires_at=parse_datetime(info.get("expires")),
            updated_at_source=parse_datetime(detail.get("sent")),
            raw_payload=parsed.raw_payload,
        )

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        try:
            load_fixture("nina", "mapdata_mowas.json")
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
