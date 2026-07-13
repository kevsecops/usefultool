"""NOAA Space Weather Prediction Center adapter — separate from NWS weather alerts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.datetime_utils import parse_datetime, utc_now
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

_SWPC_ALLOWED_HOSTS = frozenset({"services.swpc.noaa.gov", "swpc.noaa.gov"})

_NOAA_SCALE_RE = re.compile(
    r"NOAA\s+Scale:\s*([GSR])(\d)\s*-\s*(\w+)",
    re.IGNORECASE,
)
_SERIAL_RE = re.compile(r"Serial\s+Number:\s*(\d+)", re.IGNORECASE)
_MESSAGE_CODE_RE = re.compile(r"Space\s+Weather\s+Message\s+Code:\s*(\w+)", re.IGNORECASE)
_POLEWARD_RE = re.compile(r"poleward of (\d+)\s*degrees", re.IGNORECASE)

_G_SEVERITY: dict[int, Severity] = {
    1: Severity.MINOR,
    2: Severity.MODERATE,
    3: Severity.SEVERE,
    4: Severity.SEVERE,
    5: Severity.EXTREME,
}
_S_SEVERITY: dict[int, Severity] = {
    1: Severity.MINOR,
    2: Severity.MODERATE,
    3: Severity.SEVERE,
    4: Severity.SEVERE,
    5: Severity.EXTREME,
}
_R_SEVERITY: dict[int, Severity] = {
    1: Severity.MINOR,
    2: Severity.MODERATE,
    3: Severity.SEVERE,
    4: Severity.SEVERE,
    5: Severity.EXTREME,
}

_SCALE_SEVERITY = {"G": _G_SEVERITY, "S": _S_SEVERITY, "R": _R_SEVERITY}

_SCALE_LABELS = {
    "G": "Geomagnetic Storm",
    "S": "Solar Radiation Storm",
    "R": "Radio Blackout",
}

_G_POTENTIAL_SYSTEMS = {
    1: ["power_grid", "satellite_operations", "gnss"],
    2: ["power_grid", "satellite_operations", "gnss", "hf_radio"],
    3: ["power_grid", "satellite_operations", "gnss", "hf_radio"],
    4: ["power_grid", "satellite_operations", "gnss", "hf_radio", "aviation"],
    5: ["power_grid", "satellite_operations", "gnss", "hf_radio", "aviation"],
}
_S_POTENTIAL_SYSTEMS = {
    1: ["satellite_operations", "aviation"],
    2: ["satellite_operations", "aviation", "gnss"],
    3: ["satellite_operations", "aviation", "gnss", "hf_radio"],
    4: ["satellite_operations", "aviation", "gnss", "hf_radio"],
    5: ["satellite_operations", "aviation", "gnss", "hf_radio", "power_grid"],
}
_R_POTENTIAL_SYSTEMS = {
    1: ["hf_radio", "gnss"],
    2: ["hf_radio", "gnss", "satellite_operations"],
    3: ["hf_radio", "gnss", "satellite_operations", "aviation"],
    4: ["hf_radio", "gnss", "satellite_operations", "aviation", "power_grid"],
    5: ["hf_radio", "gnss", "satellite_operations", "aviation", "power_grid"],
}
_SCALE_SYSTEMS = {"G": _G_POTENTIAL_SYSTEMS, "S": _S_POTENTIAL_SYSTEMS, "R": _R_POTENTIAL_SYSTEMS}


def _swpc_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    if host and host in _SWPC_ALLOWED_HOSTS:
        return frozenset({host})
    return _SWPC_ALLOWED_HOSTS


def parse_swpc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace(" ", "T")
    if normalized.endswith("Z"):
        return parse_datetime(normalized)
    if "T" in normalized and "+" not in normalized and normalized.count("-") <= 2:
        return parse_datetime(normalized + "Z")
    return parse_datetime(normalized)


def scale_to_severity(scale_type: str, level: int | str | None) -> Severity:
    if level is None:
        return Severity.UNKNOWN
    try:
        lvl = int(level)
    except (TypeError, ValueError):
        return Severity.UNKNOWN
    if lvl <= 0:
        return Severity.UNKNOWN
    return _SCALE_SEVERITY.get(scale_type.upper(), {}).get(lvl, Severity.UNKNOWN)


def parse_noaa_scale_from_message(message: str) -> tuple[str | None, int | None, str | None]:
    match = _NOAA_SCALE_RE.search(message)
    if not match:
        return None, None, None
    return match.group(1).upper(), int(match.group(2)), match.group(3).lower()


def infer_spatial_scope_from_message(message: str, scale_type: str | None) -> tuple[SpatialScope, float | None, float | None, list[str]]:
    """Infer scope and latitude band from SWPC alert text."""
    affected_regions: list[str] = []
    lat_min = lat_max = None
    lower = message.lower()

    if "poleward of" in lower:
        pole_match = _POLEWARD_RE.search(message)
        if pole_match:
            lat_min = float(pole_match.group(1))
            lat_max = 90.0
            affected_regions.append("high_latitude")
            return SpatialScope.GLOBAL, lat_min, lat_max, affected_regions

    if "dayside" in lower or "sunlit" in lower:
        affected_regions.append("dayside_hemisphere")
        return SpatialScope.GLOBAL, None, None, affected_regions

    if scale_type == "R":
        affected_regions.append("sunlit_hemisphere")
        return SpatialScope.GLOBAL, None, None, affected_regions

    if scale_type == "S":
        affected_regions.append("magnetosphere")
        return SpatialScope.ORBITAL, None, None, affected_regions

    if scale_type == "G":
        affected_regions.append("auroral_zone")
        return SpatialScope.GLOBAL, 50.0, 90.0, affected_regions

    return SpatialScope.GLOBAL, None, None, affected_regions


def potential_systems_for_scale(scale_type: str, level: int) -> list[str]:
    return _SCALE_SYSTEMS.get(scale_type.upper(), {}).get(level, ["satellite_operations"])


def build_scale_documentation(scale_type: str, level: int, text: str | None) -> dict[str, Any]:
    return {
        "scale_type": scale_type,
        "level": level,
        "label": _SCALE_LABELS.get(scale_type, "Space Weather"),
        "description": text or "none",
        "noaa_scales_url": "https://www.swpc.noaa.gov/noaa-scales-explanation",
        "rule_based": True,
    }


def extract_scale_events(scales_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn noaa-scales.json entries into normalized event dicts."""
    events: list[dict[str, Any]] = []
    day_labels = {"-1": "observed_yesterday", "0": "current", "1": "forecast_day1", "2": "forecast_day2", "3": "forecast_day3"}

    for key, entry in scales_data.items():
        if not isinstance(entry, dict):
            continue
        day_label = day_labels.get(str(key), f"day_{key}")
        date_stamp = entry.get("DateStamp")
        time_stamp = entry.get("TimeStamp")

        for scale_type in ("G", "S", "R"):
            scale_obj = entry.get(scale_type)
            if not isinstance(scale_obj, dict):
                continue
            level = scale_obj.get("Scale")
            text = scale_obj.get("Text")
            if level is None or str(level) == "0":
                continue
            try:
                level_int = int(level)
            except (TypeError, ValueError):
                continue
            if level_int <= 0:
                continue

            events.append(
                {
                    "source_event_id": f"swpc-scale-{scale_type}-{key}",
                    "scale_type": scale_type,
                    "scale_level": level_int,
                    "scale_text": text,
                    "day_label": day_label,
                    "date_stamp": date_stamp,
                    "time_stamp": time_stamp,
                    "prob": scale_obj.get("Prob") or scale_obj.get("MinorProb"),
                    "event_kind": "scale",
                }
            )
    return events


def extract_alert_events(alerts_data: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in alerts_data:
        if not isinstance(item, dict):
            continue
        product_id = item.get("product_id", "")
        issue_dt = item.get("issue_datetime", "")
        message = item.get("message", "")
        serial_match = _SERIAL_RE.search(message)
        serial = serial_match.group(1) if serial_match else "0"
        code_match = _MESSAGE_CODE_RE.search(message)
        message_code = code_match.group(1) if code_match else product_id

        scale_type, scale_level, scale_text = parse_noaa_scale_from_message(message)
        source_event_id = f"swpc-alert-{product_id}-{serial}"

        events.append(
            {
                "source_event_id": source_event_id,
                "product_id": product_id,
                "message_code": message_code,
                "issue_datetime": issue_dt,
                "message": message,
                "scale_type": scale_type,
                "scale_level": scale_level,
                "scale_text": scale_text,
                "serial": serial,
                "event_kind": "alert",
            }
        )
    return events


class NoaaSwpcSourceAdapter:
    source_id = DataSource.NOAA_SWPC
    record_type = "observed_event"

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch: datetime | None = None
        self._last_ingest_mode: str | None = None
        self._http = http_client or HttpClient(
            user_agent=self.settings.noaa_swpc_user_agent,
            timeout_seconds=self.settings.noaa_swpc_fetch_timeout_seconds,
            max_retries=self.settings.noaa_swpc_max_retries,
            max_response_bytes=self.settings.noaa_swpc_max_response_bytes,
            allowed_hosts=_swpc_allowed_hosts(self.settings.noaa_swpc_base_url),
        )

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.noaa_swpc_use_fixtures:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "noaa_swpc" not in live_sources

    def _load_fixture_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for path in list_fixtures("noaa_swpc", "*.json"):
            data = load_fixture("noaa_swpc", path.name)
            if isinstance(data, list):
                events.extend(extract_alert_events(data))
            elif isinstance(data, dict):
                if "alerts" in data:
                    events.extend(extract_alert_events(data["alerts"]))
                if "scales" in data:
                    events.extend(extract_scale_events(data["scales"]))
                else:
                    events.extend(extract_scale_events(data))
        return events

    async def _fetch_from_fixtures(self) -> list[RawAlertPayload]:
        events = self._load_fixture_events()
        payloads = [
            RawAlertPayload(source=self.source_id, data=event, ingest_mode="fixture")
            for event in events
        ]
        self._last_fetch = utc_now()
        self._last_ingest_mode = "fixture"
        return payloads

    async def _fetch_live(self) -> list[RawAlertPayload]:
        base = self.settings.noaa_swpc_base_url.rstrip("/")
        alerts_data = await self._http.get_json_list(f"{base}/alerts.json")
        scales_data = await self._http.get_json(f"{base}/noaa-scales.json")

        alert_events = extract_alert_events(alerts_data)
        scale_events = extract_scale_events(scales_data if isinstance(scales_data, dict) else {})
        all_events = alert_events + scale_events

        payloads = [
            RawAlertPayload(source=self.source_id, data=event, ingest_mode="live")
            for event in all_events
        ]
        self._last_fetch = utc_now()
        self._last_ingest_mode = "live"
        logger.info(
            "NOAA SWPC live fetch returned %d events (%d alerts, %d scales)",
            len(payloads),
            len(alert_events),
            len(scale_events),
        )
        return payloads

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            return await self._fetch_from_fixtures()
        try:
            return await self._fetch_live()
        except Exception as exc:
            if self.settings.noaa_swpc_fallback_to_fixtures and list_fixtures("noaa_swpc", "*.json"):
                logger.warning("NOAA SWPC live fetch failed (%s), falling back to fixtures", exc)
                return await self._fetch_from_fixtures()
            raise

    def parse_observed_event(self, raw: RawAlertPayload) -> ParsedObservedEvent:
        source_event_id = str(raw.data.get("source_event_id", ""))
        return ParsedObservedEvent(
            source=self.source_id,
            source_event_id=source_event_id,
            fields={"event": raw.data},
            raw_payload=raw.data,
        )

    def _normalize_scale_event(self, event: dict[str, Any]) -> CanonicalObservedEvent:
        scale_type = event["scale_type"]
        level = event["scale_level"]
        day_label = event.get("day_label", "current")
        severity = scale_to_severity(scale_type, level)
        label = _SCALE_LABELS.get(scale_type, "Space Weather")
        title = f"{label} {scale_type}{level} ({day_label.replace('_', ' ')})"

        date_stamp = event.get("date_stamp")
        time_stamp = event.get("time_stamp")
        issued_str = f"{date_stamp}T{time_stamp}Z" if date_stamp and time_stamp else None
        issued_at = parse_swpc_datetime(issued_str) or utc_now()

        scope = SpatialScope.GLOBAL if scale_type == "G" else SpatialScope.ORBITAL if scale_type == "S" else SpatialScope.GLOBAL
        lat_min = 50.0 if scale_type == "G" and level >= 1 else None
        lat_max = 90.0 if scale_type == "G" and level >= 1 else None

        source_metadata = {
            "scale_type": scale_type,
            "scale_level": level,
            "scale_text": event.get("scale_text"),
            "day_label": day_label,
            "probability": event.get("prob"),
            "potential_systems": potential_systems_for_scale(scale_type, level),
            "scale_documentation": build_scale_documentation(scale_type, level, event.get("scale_text")),
            "affected_regions": ["global"] if scope == SpatialScope.GLOBAL else ["magnetosphere"],
            "event_kind": "scale",
        }

        return CanonicalObservedEvent(
            source=DataSource.NOAA_SWPC,
            source_event_id=event["source_event_id"],
            source_url="https://www.swpc.noaa.gov/products/noaa-scales",
            title=title,
            description=f"NOAA {label} scale {scale_type}{level}: {event.get('scale_text', 'active')}",
            event_type=f"{scale_type.lower()}_scale",
            category=Category.ENVIRONMENTAL,
            severity=severity,
            status=ObservedEventStatus.REVIEWED,
            confidence=Confidence.HIGH if day_label in ("current", "observed_yesterday") else Confidence.MEDIUM,
            geometry=None,
            spatial_scope=scope,
            affected_latitude_min=lat_min,
            affected_latitude_max=lat_max,
            issued_at=issued_at,
            starts_at=issued_at,
            raw_payload=event,
            source_metadata=source_metadata,
        )

    def _normalize_alert_event(self, event: dict[str, Any]) -> CanonicalObservedEvent:
        message = event.get("message", "")
        scale_type = event.get("scale_type")
        scale_level = event.get("scale_level")
        severity = scale_to_severity(scale_type, scale_level) if scale_type and scale_level else Severity.MODERATE

        scope, lat_min, lat_max, regions = infer_spatial_scope_from_message(message, scale_type)
        if scale_type and scale_level:
            systems = potential_systems_for_scale(scale_type, scale_level)
        else:
            systems = ["satellite_operations", "hf_radio", "gnss"]

        issued_at = parse_swpc_datetime(event.get("issue_datetime")) or utc_now()
        label = _SCALE_LABELS.get(scale_type or "", "Space Weather Alert")
        title = f"{label}"
        if scale_type and scale_level:
            title = f"{label} {scale_type}{scale_level} Alert"

        source_metadata = {
            "product_id": event.get("product_id"),
            "message_code": event.get("message_code"),
            "serial": event.get("serial"),
            "scale_type": scale_type,
            "scale_level": scale_level,
            "scale_text": event.get("scale_text"),
            "potential_systems": systems,
            "affected_regions": regions,
            "event_kind": "alert",
        }
        if scale_type and scale_level:
            source_metadata["scale_documentation"] = build_scale_documentation(
                scale_type, scale_level, event.get("scale_text")
            )

        return CanonicalObservedEvent(
            source=DataSource.NOAA_SWPC,
            source_event_id=event["source_event_id"],
            source_url="https://www.swpc.noaa.gov/products/alerts.json",
            title=title,
            description=message[:2000] if message else title,
            event_type=event.get("message_code") or event.get("product_id"),
            category=Category.ENVIRONMENTAL,
            severity=severity,
            status=ObservedEventStatus.REVIEWED if "ALERT" in message.upper() else ObservedEventStatus.UNKNOWN,
            confidence=Confidence.HIGH,
            geometry=None,
            spatial_scope=scope,
            affected_latitude_min=lat_min,
            affected_latitude_max=lat_max,
            issued_at=issued_at,
            starts_at=issued_at,
            raw_payload=event,
            source_metadata=source_metadata,
        )

    def normalize_observed_event(self, parsed: ParsedObservedEvent) -> CanonicalObservedEvent:
        event: dict[str, Any] = parsed.fields.get("event", {})
        if event.get("event_kind") == "scale":
            return self._normalize_scale_event(event)
        return self._normalize_alert_event(event)

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        if self._use_fixtures():
            fixtures = list_fixtures("noaa_swpc", "*.json")
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
                error_message="No NOAA SWPC fixtures found",
                ingest_mode="fixture",
            )

        import time

        start = time.monotonic()
        try:
            base = self.settings.noaa_swpc_base_url.rstrip("/")
            await self._http.get_json(f"{base}/noaa-scales.json")
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
