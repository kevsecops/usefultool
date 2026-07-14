"""SHOWCASE_MODE — curated demo scenarios without external API keys."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.canonical_event import CanonicalEvent
from app.models.ingest_run import IngestRun
from app.normalization.datetime_utils import utc_now
from app.schemas.common import IngestRunStatus
from app.services.ingest_service import (
    _ingest_alerts,
    _ingest_observed_events,
    deactivate_expired_alerts,
)
from app.sources.base import RawAlertPayload
from app.sources.eonet import EonetSourceAdapter
from app.sources.gdacs import GdacsSourceAdapter, extract_gdacs_features, is_current_event
from app.sources.noaa_swpc import (
    NoaaSwpcSourceAdapter,
    extract_alert_events,
    extract_scale_events,
)
from app.sources.usgs import UsgsSourceAdapter, extract_usgs_features
from app.sources.fixture_loader import refresh_fixture_datetimes, refresh_usgs_fixture

logger = get_logger(__name__)

_SHOWCASE_INGEST_MODE = "showcase"


def _tag_showcase(data: dict[str, Any]) -> dict[str, Any]:
    tagged = dict(data)
    tagged["_ingest_mode"] = _SHOWCASE_INGEST_MODE
    return tagged

_SOURCE_LOADERS: dict[str, tuple[str, type]] = {
    "usgs": ("earthquake_port/usgs.geojson", UsgsSourceAdapter),
    "gdacs": ("tropical_storm/gdacs.json", GdacsSourceAdapter),
    "eonet": ("tropical_storm/eonet.json", EonetSourceAdapter),
    "noaa_swpc": ("geomagnetic_storm/swpc.json", NoaaSwpcSourceAdapter),
}


@dataclass
class ShowcaseManifest:
    version: str
    scenarios: list[dict[str, Any]]
    ingest_sources: list[str]
    exposure_fixtures: list[str]


def showcase_dir() -> Path:
    return get_settings().fixtures_dir / "showcase"


def load_manifest() -> ShowcaseManifest:
    path = showcase_dir() / "manifest.json"
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return ShowcaseManifest(
        version=data.get("version", "1.0"),
        scenarios=data.get("scenarios", []),
        ingest_sources=data.get("ingest_sources", list(_SOURCE_LOADERS.keys())),
        exposure_fixtures=data.get("exposure_fixtures", []),
    )


def load_showcase_data(relative_path: str, *, refresh_dates: bool = True) -> Any:
    path = showcase_dir() / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Showcase fixture not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not refresh_dates:
        return data
    if relative_path.endswith(".geojson"):
        return refresh_usgs_fixture(data)
    return refresh_fixture_datetimes(data)


def _usgs_payloads(data: dict[str, Any]) -> list[RawAlertPayload]:
    return [
        RawAlertPayload(
            source="usgs",
            data=_tag_showcase(feature),
            ingest_mode=_SHOWCASE_INGEST_MODE,
        )
        for feature in extract_usgs_features(data)
    ]


def _gdacs_payloads(data: dict[str, Any]) -> list[RawAlertPayload]:
    return [
        RawAlertPayload(
            source="gdacs",
            data=_tag_showcase(feature),
            ingest_mode=_SHOWCASE_INGEST_MODE,
        )
        for feature in extract_gdacs_features(data)
        if is_current_event(feature.get("properties", {}))
    ]


def _eonet_payloads(data: dict[str, Any]) -> list[RawAlertPayload]:
    events = data.get("events", [])
    if not isinstance(events, list):
        return []
    return [
        RawAlertPayload(
            source="eonet",
            data=_tag_showcase(event),
            ingest_mode=_SHOWCASE_INGEST_MODE,
        )
        for event in events
        if isinstance(event, dict)
    ]


def _swpc_payloads(data: dict[str, Any]) -> list[RawAlertPayload]:
    events: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if "alerts" in data:
            events.extend(extract_alert_events(data["alerts"]))
        if "scales" in data:
            events.extend(extract_scale_events(data["scales"]))
    return [
        RawAlertPayload(
            source="noaa_swpc",
            data=_tag_showcase(event),
            ingest_mode=_SHOWCASE_INGEST_MODE,
        )
        for event in events
    ]


def _payloads_for_source(source_id: str) -> list[RawAlertPayload]:
    if source_id not in _SOURCE_LOADERS:
        return []
    relative_path, _ = _SOURCE_LOADERS[source_id]
    data = load_showcase_data(relative_path)

    if source_id == "usgs":
        return _usgs_payloads(data)
    if source_id == "gdacs":
        return _gdacs_payloads(data)
    if source_id == "eonet":
        return _eonet_payloads(data)
    if source_id == "noaa_swpc":
        return _swpc_payloads(data)
    return []


async def _ingest_showcase_source(
    db: Session,
    source_id: str,
    now,
) -> tuple[int, int, int, set[tuple[str, str]]]:
    payloads = _payloads_for_source(source_id)
    if not payloads:
        return 0, 0, 0, set()

    _, adapter_cls = _SOURCE_LOADERS[source_id]
    adapter = adapter_cls()

    if adapter.record_type == "observed_event":
        fetched = created = updated = 0
        seen_keys: set[tuple[str, str]] = set()
        for raw in payloads:
            parsed = adapter.parse_observed_event(raw)
            canonical = adapter.normalize_observed_event(parsed)
            fetched += 1
            key = (canonical.source, canonical.source_event_id)
            seen_keys.add(key)
            from app.services.ingest_service import (  # noqa: PLC0415
                _observed_event_to_model,
                _update_observed_event,
            )
            from app.models.observed_event import ObservedEvent

            existing = db.scalar(
                select(ObservedEvent).where(
                    ObservedEvent.source == canonical.source,
                    ObservedEvent.source_event_id == canonical.source_event_id,
                )
            )
            if existing:
                if _update_observed_event(existing, canonical, now):
                    updated += 1
            else:
                db.add(_observed_event_to_model(canonical, now))
                created += 1
        return fetched, created, updated, seen_keys

    fetched = created = updated = 0
    seen_keys: set[tuple[str, str]] = set()
    for raw in payloads:
        parsed = adapter.parse_alert(raw)
        canonical = adapter.normalize_alert(parsed)
        fetched += 1
        key = (canonical.source, canonical.source_alert_id)
        seen_keys.add(key)
        from app.services.ingest_service import _canonical_to_model, _update_alert  # noqa: PLC0415
        from app.models.alert import Alert

        existing = db.scalar(
            select(Alert).where(
                Alert.source == canonical.source,
                Alert.source_alert_id == canonical.source_alert_id,
            )
        )
        if existing:
            if _update_alert(existing, canonical, now):
                updated += 1
        else:
            db.add(_canonical_to_model(canonical, now))
            created += 1
    return fetched, created, updated, seen_keys


def import_showcase_exposure(db: Session) -> int:
    """Import exposure assets from fixtures/showcase/exposure/."""
    from app.services.exposure_service import import_exposure_fixtures_from_dir

    exposure_dir = showcase_dir() / "exposure"
    result = import_exposure_fixtures_from_dir(
        db, exposure_dir, source_label="showcase_fixture"
    )
    return result.assets_created + result.assets_updated


def showcase_data_present(db: Session) -> bool:
    count = db.scalar(
        select(func.count()).select_from(CanonicalEvent).where(CanonicalEvent.is_active.is_(True))
    )
    return (count or 0) > 0


async def run_showcase_ingest(
    db: Session,
    *,
    generate_briefing: bool | None = None,
) -> IngestRun:
    """Load all curated showcase scenarios — no external API keys required."""
    settings = get_settings()
    should_generate = (
        generate_briefing
        if generate_briefing is not None
        else settings.auto_generate_briefing
    )
    manifest = load_manifest()
    now = utc_now()
    expired_count = deactivate_expired_alerts(db, now)

    run = IngestRun(
        started_at=now,
        source="showcase",
        status=IngestRunStatus.RUNNING,
        errors=[],
    )
    db.add(run)
    db.flush()

    fetched = created = updated = 0
    errors: list[dict] = []

    try:
        import_showcase_exposure(db)
    except Exception as exc:
        logger.warning("Showcase exposure import failed: %s", exc)
        errors.append({"source": "showcase_exposure", "error": str(exc)})

    for source_id in manifest.ingest_sources:
        try:
            source_fetched, source_created, source_updated, _ = await _ingest_showcase_source(
                db, source_id, now
            )
            fetched += source_fetched
            created += source_created
            updated += source_updated
            logger.info(
                "Showcase ingest source=%s fetched=%d created=%d updated=%d",
                source_id,
                source_fetched,
                source_created,
                source_updated,
            )
        except Exception as exc:
            logger.exception("Showcase ingest failed for source %s", source_id)
            errors.append({"source": source_id, "error": str(exc)})

    run.finished_at = utc_now()
    run.alerts_fetched = fetched
    run.alerts_created = created
    run.alerts_updated = updated
    run.alerts_deactivated = expired_count
    run.errors = errors
    if errors and fetched == 0:
        run.status = IngestRunStatus.FAILED
    elif errors:
        run.status = IngestRunStatus.PARTIAL
    else:
        run.status = IngestRunStatus.SUCCESS

    db.flush()
    db.refresh(run)

    from app.services.correlation_service import run_correlation
    from app.services.exposure_service import run_calculate_exposure
    from app.services.implication_service import run_generate_implications

    if run.status in (IngestRunStatus.SUCCESS, IngestRunStatus.PARTIAL):
        run_correlation(db)
        run_calculate_exposure(db, active_only=True)
        run_generate_implications(db, active_only=True)

    if should_generate and run.status in (IngestRunStatus.SUCCESS, IngestRunStatus.PARTIAL):
        from app.services.briefing_service import generate_briefing

        generate_briefing(db, briefing_type="auto")

    return run


async def ensure_showcase_data(db: Session) -> None:
    """Run showcase ingest on startup when SHOWCASE_MODE=true and DB is empty."""
    if showcase_data_present(db):
        logger.info("Showcase data already present — skipping startup ingest")
        return
    logger.info("SHOWCASE_MODE: loading curated demo scenarios")
    await run_showcase_ingest(db, generate_briefing=True)
