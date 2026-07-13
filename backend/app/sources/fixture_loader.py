"""Fixture loader for DEMO_MODE."""

import json
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.normalization.datetime_utils import utc_now

logger = get_logger(__name__)

_ISSUED_FIELD_NAMES = frozenset(
    {
        "sent",
        "effective",
        "onset",
        "startdate",
        "fromdate",
        "datemodified",
    }
)
_EXPIRES_FIELD_NAMES = frozenset({"expires", "todate", "enddate"})
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$"
)


def _format_dt(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _refresh_datetimes_recursive(
    node: Any,
    *,
    issued_at: datetime,
    expires_at: datetime,
) -> Any:
    if isinstance(node, dict):
        refreshed: dict[str, Any] = {}
        for key, value in node.items():
            key_lower = key.lower()
            if key_lower in _ISSUED_FIELD_NAMES and isinstance(value, str) and _ISO_DATETIME_RE.match(value):
                refreshed[key] = _format_dt(issued_at)
            elif key_lower in _EXPIRES_FIELD_NAMES and isinstance(value, str) and _ISO_DATETIME_RE.match(value):
                refreshed[key] = _format_dt(expires_at)
            else:
                refreshed[key] = _refresh_datetimes_recursive(
                    value,
                    issued_at=issued_at,
                    expires_at=expires_at,
                )
        return refreshed
    if isinstance(node, list):
        return [
            _refresh_datetimes_recursive(item, issued_at=issued_at, expires_at=expires_at)
            for item in node
        ]
    return node


def refresh_fixture_datetimes(
    data: Any,
    *,
    now: datetime | None = None,
    issued_hours_ago: int = 2,
    expires_hours_ahead: int = 24,
) -> Any:
    """Rewrite known datetime fields so demo fixtures stay current relative to now."""
    now = now or utc_now()
    issued_at = now - timedelta(hours=issued_hours_ago)
    expires_at = now + timedelta(hours=expires_hours_ahead)
    return _refresh_datetimes_recursive(
        deepcopy(data),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def refresh_usgs_fixture(
    data: dict[str, Any],
    *,
    now: datetime | None = None,
    hours_ago: int = 2,
) -> dict[str, Any]:
    """Shift USGS millisecond epoch timestamps so fixtures stay recent."""
    now = now or utc_now()
    event_time_ms = int((now - timedelta(hours=hours_ago)).timestamp() * 1000)
    updated_ms = int(now.timestamp() * 1000)

    refreshed = deepcopy(data)
    metadata = refreshed.get("metadata")
    if isinstance(metadata, dict):
        metadata["generated"] = updated_ms

    features = refreshed.get("features")
    if isinstance(features, list):
        for idx, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties")
            if not isinstance(props, dict):
                continue
            offset_ms = idx * 60_000
            props["time"] = event_time_ms - offset_ms
            props["updated"] = updated_ms - offset_ms

    return refreshed


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_fixture(source: str, filename: str, *, refresh_dates: bool = True) -> Any:
    settings = get_settings()
    path = settings.fixtures_dir / source / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    data = _load_json(path)
    if refresh_dates and source != "usgs":
        data = refresh_fixture_datetimes(data)
    return data


def list_fixtures(source: str, pattern: str = "*.json") -> list[Path]:
    settings = get_settings()
    source_dir = settings.fixtures_dir / source
    if not source_dir.exists():
        return []
    return sorted(source_dir.glob(pattern))


def load_geojson(source: str, filename: str, *, refresh_dates: bool = True) -> dict[str, Any]:
    settings = get_settings()
    path = settings.fixtures_dir / source / filename
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON fixture not found: {path}")
    data = _load_json(path)
    if refresh_dates and source != "usgs":
        data = refresh_fixture_datetimes(data)
    return data
