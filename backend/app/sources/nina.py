"""NINA source adapter — live HTTP in Phase 7, fixtures in DEMO_MODE."""

from typing import Any
from urllib.parse import quote, urlparse

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.category import normalize_cap_category, normalize_nina_event_code
from app.normalization.datetime_utils import parse_datetime, utc_now
from app.normalization.geometry import compute_centroid
from app.normalization.html_sanitizer import sanitize_html
from app.normalization.severity import normalize_cap_severity
from app.schemas.alert import CanonicalAlert
from app.schemas.common import AlertSource, AlertStatus, Category, Certainty, Urgency
from app.sources.base import ParsedAlert, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import load_fixture, load_geojson, list_fixtures

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

_MAP_FEEDS = ("mowas/mapData.json", "dwd/mapData.json")


def _nina_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    return frozenset({host}) if host else frozenset()


def extract_geometry_from_geojson(data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract first feature geometry from NINA GeoJSON FeatureCollection."""
    features = data.get("features", [])
    if not features:
        return None
    first = features[0]
    if isinstance(first, dict):
        return first.get("geometry")
    return None


class NinaSourceAdapter:
    source_id = AlertSource.NINA

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch = None
        self._last_ingest_mode: str | None = None
        self._last_fetch_count: int = 0
        self._http = http_client or HttpClient(
            user_agent=self.settings.nina_user_agent,
            timeout_seconds=self.settings.nina_fetch_timeout_seconds,
            max_retries=self.settings.nina_max_retries,
            max_response_bytes=self.settings.nina_max_response_bytes,
            allowed_hosts=_nina_allowed_hosts(self.settings.nina_base_url),
        )

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.nina_use_fixtures:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "nina" not in live_sources

    def _fixture_feeds(self) -> tuple[str, ...]:
        return ("mapdata_mowas.json", "mapdata_dwd.json")

    async def _fetch_from_fixtures(self) -> list[RawAlertPayload]:
        payloads: list[RawAlertPayload] = []
        for feed in self._fixture_feeds():
            try:
                items = load_fixture("nina", feed)
            except FileNotFoundError:
                logger.warning("NINA fixture missing: %s", feed)
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                alert_id = item.get("id", "")
                detail = self._load_detail_fixture(alert_id)
                geometry = self._load_geometry_fixture(alert_id)
                payloads.append(
                    RawAlertPayload(
                        source=self.source_id,
                        data=item,
                        detail=detail,
                        geometry=geometry,
                        ingest_mode="fixture",
                    )
                )
        self._last_fetch = utc_now()
        self._last_ingest_mode = "fixture"
        self._last_fetch_count = len(payloads)
        return payloads

    def _load_detail_fixture(self, alert_id: str) -> dict[str, Any] | None:
        safe_id = alert_id.replace(".", "_").replace("/", "_")
        try:
            return load_fixture("nina", f"warning_detail_{safe_id}.json")
        except FileNotFoundError:
            try:
                return load_fixture("nina", "warning_detail_flood.json")
            except FileNotFoundError:
                return None

    def _load_geometry_fixture(self, alert_id: str) -> dict[str, Any] | None:
        safe_id = alert_id.replace(".", "_").replace("/", "_")
        for name in (f"warning_geo_{safe_id}.geojson", "warning_geo_flood.geojson"):
            try:
                geo = load_geojson("nina", name)
                return extract_geometry_from_geojson(geo)
            except FileNotFoundError:
                continue
        return None

    async def _fetch_live(self) -> list[RawAlertPayload]:
        base = self.settings.nina_base_url.rstrip("/")
        compact_items: list[dict[str, Any]] = []

        for feed in _MAP_FEEDS:
            try:
                items = await self._http.get_json_list(f"{base}/{feed}")
                compact_items.extend(item for item in items if isinstance(item, dict))
            except HttpClientError as exc:
                logger.warning("NINA mapData fetch failed for %s: %s", feed, exc)

        payloads: list[RawAlertPayload] = []
        for item in compact_items:
            alert_id = item.get("id", "")
            if not alert_id:
                continue
            detail = await self._fetch_warning_detail(base, alert_id)
            geometry = await self._fetch_warning_geometry(base, alert_id)
            payloads.append(
                RawAlertPayload(
                    source=self.source_id,
                    data=item,
                    detail=detail,
                    geometry=geometry,
                    ingest_mode="live",
                )
            )

        self._last_fetch = utc_now()
        self._last_ingest_mode = "live"
        self._last_fetch_count = len(payloads)
        logger.info("NINA live fetch returned %d alerts", len(payloads))
        return payloads

    async def _fetch_warning_detail(self, base: str, alert_id: str) -> dict[str, Any] | None:
        encoded_id = quote(alert_id, safe="")
        try:
            return await self._http.get_json(f"{base}/warnings/{encoded_id}.json")
        except HttpClientError as exc:
            logger.warning("NINA detail fetch failed for %s: %s", alert_id, exc)
            return None

    async def _fetch_warning_geometry(self, base: str, alert_id: str) -> dict[str, Any] | None:
        encoded_id = quote(alert_id, safe="")
        try:
            geo = await self._http.get_json(f"{base}/warnings/{encoded_id}.geojson")
            return extract_geometry_from_geojson(geo)
        except HttpClientError as exc:
            logger.warning("NINA geometry fetch failed for %s: %s", alert_id, exc)
            return None

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            return await self._fetch_from_fixtures()

        try:
            payloads = await self._fetch_live()
            if (
                not payloads
                and self.settings.nina_fallback_to_fixtures
                and list_fixtures("nina", "mapdata_*.json")
            ):
                logger.warning("NINA live fetch returned no alerts, falling back to fixtures")
                return await self._fetch_from_fixtures()
            return payloads
        except Exception as exc:
            if self.settings.nina_fallback_to_fixtures and list_fixtures("nina", "mapdata_*.json"):
                logger.warning("NINA live fetch failed (%s), falling back to fixtures", exc)
                return await self._fetch_from_fixtures()
            raise

    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert:
        detail = raw.detail or {}
        info_list = detail.get("info", [])
        info = info_list[0] if info_list else {}
        ingest_mode = raw.ingest_mode or ("fixture" if self._use_fixtures() else "live")
        return ParsedAlert(
            source=self.source_id,
            source_alert_id=raw.data.get("id", detail.get("identifier", "")),
            fields={
                "compact": raw.data,
                "detail": detail,
                "info": info,
                "geometry": raw.geometry,
                "ingest_mode": ingest_mode,
            },
            raw_payload={
                "compact": raw.data,
                "detail": detail,
                "geometry": raw.geometry,
                "_ingest_mode": ingest_mode,
            },
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
                category = normalize_cap_category(cats[0])

        severity = normalize_cap_severity(info.get("severity") or compact.get("severity"))
        urgency_raw = (info.get("urgency") or compact.get("urgency") or "").lower()
        certainty_raw = (info.get("certainty") or "").lower()
        status_raw = (detail.get("status") or "actual").lower()

        issued_at = parse_datetime(detail.get("sent")) or parse_datetime(compact.get("startDate"))
        if not issued_at:
            issued_at = utc_now()

        lat, lon = compute_centroid(geometry)

        ingest_mode = parsed.fields.get("ingest_mode", "live")
        source_url = None
        if ingest_mode == "live":
            source_url = (
                f"{self.settings.nina_base_url.rstrip('/')}/warnings/{parsed.source_alert_id}.json"
            )

        return CanonicalAlert(
            source=AlertSource.NINA,
            source_alert_id=parsed.source_alert_id,
            source_url=source_url,
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
        if self._use_fixtures():
            fixtures = list_fixtures("nina", "mapdata_*.json")
            if fixtures:
                return SourceHealth(
                    source=self.source_id,
                    is_healthy=True,
                    checked_at=now,
                    latency_ms=1,
                    last_success_at=self._last_fetch or now,
                    ingest_mode="fixture",
                    alerts_fetched=self._last_fetch_count or None,
                )
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                error_message="No NINA fixtures found",
                ingest_mode="fixture",
            )

        import time

        start = time.monotonic()
        try:
            url = f"{self.settings.nina_base_url.rstrip('/')}/mowas/mapData.json"
            items = await self._http.get_json_list(url)
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=True,
                checked_at=now,
                latency_ms=latency_ms,
                last_success_at=self._last_fetch or now,
                ingest_mode="live",
                alerts_fetched=self._last_fetch_count or len(items),
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
