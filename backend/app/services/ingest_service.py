"""Ingest orchestration service."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.ingest_run import IngestRun
from app.models.observed_event import ObservedEvent
from app.normalization.datetime_utils import utc_now
from app.normalization.fingerprint import generate_fingerprint, generate_observed_event_fingerprint
from app.normalization.geometry import geojson_to_wkt_element
from app.normalization.strings import clamp_str
from app.schemas.alert import CanonicalAlert
from app.schemas.common import IngestRunStatus
from app.schemas.observed_event import CanonicalObservedEvent
from app.services.alert_active import is_expired
from app.services.alert_fixture import deactivate_fixture_alerts
from app.services.source_status_service import upsert_source_status
from app.sources.base import ObservedEventSourceAdapter
from app.sources.registry import get_adapters

logger = get_logger(__name__)

_ALERT_FIELD_LIMITS: dict[str, int] = {
    "source_url": 1024,
    "title": 1024,
    "country_name": 128,
    "region": 256,
    "location_name": 512,
    "event_type": 256,
    "language": 16,
}

_OBSERVED_EVENT_FIELD_LIMITS: dict[str, int] = {
    "source_url": 1024,
    "title": 1024,
    "event_type": 256,
    "region": 256,
    "location_name": 512,
}


def _clamp_canonical_fields(canonical, field_limits: dict[str, int]) -> None:
    """Ensure VARCHAR fields fit DB columns so one long value cannot fail the batch."""
    for field, max_len in field_limits.items():
        value = getattr(canonical, field, None)
        if isinstance(value, str):
            setattr(canonical, field, clamp_str(value, max_len))


def _should_be_active(canonical: CanonicalAlert, now: datetime) -> bool:
    if canonical.expires_at is not None and canonical.expires_at < now:
        return False
    return True


def deactivate_expired_alerts(db: Session, now: datetime | None = None) -> int:
    """Mark all expired alerts inactive (global, all sources)."""
    now = now or utc_now()
    active_alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    deactivated = 0
    for alert in active_alerts:
        if is_expired(alert, now):
            alert.is_active = False
            deactivated += 1
    return deactivated


def _canonical_to_model(canonical: CanonicalAlert, now: datetime) -> Alert:
    _clamp_canonical_fields(canonical, _ALERT_FIELD_LIMITS)
    fingerprint = generate_fingerprint(
        source=canonical.source,
        source_alert_id=canonical.source_alert_id,
        title=canonical.title,
        issued_at=canonical.issued_at,
        severity=canonical.severity,
        category=canonical.category,
    )
    return Alert(
        source=canonical.source,
        source_alert_id=canonical.source_alert_id,
        source_url=canonical.source_url,
        title=canonical.title,
        description=canonical.description,
        instruction=canonical.instruction,
        country_code=canonical.country_code,
        country_name=canonical.country_name,
        region=canonical.region,
        location_name=canonical.location_name,
        latitude=canonical.latitude,
        longitude=canonical.longitude,
        geometry=geojson_to_wkt_element(canonical.geometry),
        geometry_json=canonical.geometry,
        category=canonical.category,
        event_type=canonical.event_type,
        severity=canonical.severity,
        urgency=canonical.urgency,
        certainty=canonical.certainty,
        status=canonical.status,
        language=canonical.language,
        issued_at=canonical.issued_at,
        effective_at=canonical.effective_at,
        starts_at=canonical.starts_at,
        expires_at=canonical.expires_at,
        updated_at_source=canonical.updated_at_source,
        ingested_at=now,
        last_seen_at=now,
        raw_payload=canonical.raw_payload,
        fingerprint=fingerprint,
        is_active=_should_be_active(canonical, now),
    )


def _update_alert(existing: Alert, canonical: CanonicalAlert, now: datetime) -> bool:
    _clamp_canonical_fields(canonical, _ALERT_FIELD_LIMITS)
    new_fp = generate_fingerprint(
        source=canonical.source,
        source_alert_id=canonical.source_alert_id,
        title=canonical.title,
        issued_at=canonical.issued_at,
        severity=canonical.severity,
        category=canonical.category,
    )
    changed = False
    fields_to_update = {
        "source_url": canonical.source_url,
        "title": canonical.title,
        "description": canonical.description,
        "instruction": canonical.instruction,
        "country_code": canonical.country_code,
        "country_name": canonical.country_name,
        "region": canonical.region,
        "location_name": canonical.location_name,
        "latitude": canonical.latitude,
        "longitude": canonical.longitude,
        "geometry": geojson_to_wkt_element(canonical.geometry),
        "geometry_json": canonical.geometry,
        "category": canonical.category,
        "event_type": canonical.event_type,
        "severity": canonical.severity,
        "urgency": canonical.urgency,
        "certainty": canonical.certainty,
        "status": canonical.status,
        "language": canonical.language,
        "issued_at": canonical.issued_at,
        "effective_at": canonical.effective_at,
        "starts_at": canonical.starts_at,
        "expires_at": canonical.expires_at,
        "updated_at_source": canonical.updated_at_source,
        "raw_payload": canonical.raw_payload,
        "fingerprint": new_fp,
        "last_seen_at": now,
        "is_active": _should_be_active(canonical, now),
    }
    for key, value in fields_to_update.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    return changed


def _observed_event_to_model(canonical: CanonicalObservedEvent, now: datetime) -> ObservedEvent:
    _clamp_canonical_fields(canonical, _OBSERVED_EVENT_FIELD_LIMITS)
    fingerprint = generate_observed_event_fingerprint(
        source=canonical.source,
        source_event_id=canonical.source_event_id,
        title=canonical.title,
        issued_at=canonical.issued_at,
        severity=canonical.severity,
        category=canonical.category,
    )
    return ObservedEvent(
        source=canonical.source,
        source_event_id=canonical.source_event_id,
        source_url=canonical.source_url,
        title=canonical.title,
        description=canonical.description,
        event_type=canonical.event_type,
        category=canonical.category,
        severity=canonical.severity,
        status=canonical.status,
        confidence=canonical.confidence,
        country_code=canonical.country_code,
        region=canonical.region,
        location_name=canonical.location_name,
        latitude=canonical.latitude,
        longitude=canonical.longitude,
        geometry=geojson_to_wkt_element(canonical.geometry),
        geometry_json=canonical.geometry,
        spatial_scope=canonical.spatial_scope,
        affected_latitude_min=canonical.affected_latitude_min,
        affected_latitude_max=canonical.affected_latitude_max,
        issued_at=canonical.issued_at,
        starts_at=canonical.starts_at,
        ends_at=canonical.ends_at,
        updated_at_source=canonical.updated_at_source,
        ingested_at=now,
        last_seen_at=now,
        raw_payload=canonical.raw_payload,
        source_metadata=canonical.source_metadata,
        fingerprint=fingerprint,
        is_active=True,
    )


def _update_observed_event(
    existing: ObservedEvent, canonical: CanonicalObservedEvent, now: datetime
) -> bool:
    _clamp_canonical_fields(canonical, _OBSERVED_EVENT_FIELD_LIMITS)
    new_fp = generate_observed_event_fingerprint(
        source=canonical.source,
        source_event_id=canonical.source_event_id,
        title=canonical.title,
        issued_at=canonical.issued_at,
        severity=canonical.severity,
        category=canonical.category,
    )
    changed = False
    fields_to_update = {
        "source_url": canonical.source_url,
        "title": canonical.title,
        "description": canonical.description,
        "event_type": canonical.event_type,
        "category": canonical.category,
        "severity": canonical.severity,
        "status": canonical.status,
        "confidence": canonical.confidence,
        "country_code": canonical.country_code,
        "region": canonical.region,
        "location_name": canonical.location_name,
        "latitude": canonical.latitude,
        "longitude": canonical.longitude,
        "geometry": geojson_to_wkt_element(canonical.geometry),
        "geometry_json": canonical.geometry,
        "spatial_scope": canonical.spatial_scope,
        "affected_latitude_min": canonical.affected_latitude_min,
        "affected_latitude_max": canonical.affected_latitude_max,
        "issued_at": canonical.issued_at,
        "starts_at": canonical.starts_at,
        "ends_at": canonical.ends_at,
        "updated_at_source": canonical.updated_at_source,
        "raw_payload": canonical.raw_payload,
        "source_metadata": canonical.source_metadata,
        "fingerprint": new_fp,
        "last_seen_at": now,
        "is_active": True,
    }
    for key, value in fields_to_update.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    return changed


async def _ingest_alerts(
    db: Session,
    adapter,
    now: datetime,
) -> tuple[int, int, int, set[tuple[str, str]]]:
    fetched = created = updated = 0
    seen_keys: set[tuple[str, str]] = set()

    raw_alerts = await adapter.fetch_alerts()
    for raw in raw_alerts:
        parsed = adapter.parse_alert(raw)
        canonical = adapter.normalize_alert(parsed)
        fetched += 1
        key = (canonical.source, canonical.source_alert_id)
        seen_keys.add(key)

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


async def _ingest_observed_events(
    db: Session,
    adapter: ObservedEventSourceAdapter,
    now: datetime,
) -> tuple[int, int, int, set[tuple[str, str]]]:
    fetched = created = updated = 0
    seen_keys: set[tuple[str, str]] = set()

    raw_events = await adapter.fetch_alerts()
    for raw in raw_events:
        parsed = adapter.parse_observed_event(raw)
        canonical = adapter.normalize_observed_event(parsed)
        fetched += 1
        key = (canonical.source, canonical.source_event_id)
        seen_keys.add(key)

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


async def run_ingest(
    db: Session,
    sources: list[str] | None = None,
    *,
    generate_briefing: bool | None = None,
) -> IngestRun:
    settings = get_settings()
    should_generate_briefing = (
        generate_briefing
        if generate_briefing is not None
        else settings.auto_generate_briefing
    )
    now = utc_now()
    expired_count = deactivate_expired_alerts(db, now)
    fixture_count = 0
    if not settings.demo_mode:
        fixture_count = deactivate_fixture_alerts(db)
        if fixture_count:
            logger.info(
                "Deactivated %d fixture-origin alerts (demo_mode=false)",
                fixture_count,
            )
    source_label = "all" if not sources else ",".join(sources)
    run = IngestRun(
        started_at=now,
        source=source_label,
        status=IngestRunStatus.RUNNING,
        errors=[],
    )
    db.add(run)
    db.flush()

    adapters = get_adapters(sources)
    alert_seen_keys: set[tuple[str, str]] = set()
    event_seen_keys: set[tuple[str, str]] = set()
    fetched = created = updated = 0
    errors: list[dict] = []

    for adapter in adapters:
        source_fetched = source_created = source_updated = 0
        try:
            if getattr(adapter, "record_type", "alert") == "observed_event":
                source_fetched, source_created, source_updated, seen = await _ingest_observed_events(
                    db, adapter, now
                )
                event_seen_keys.update(seen)
            else:
                source_fetched, source_created, source_updated, seen = await _ingest_alerts(
                    db, adapter, now
                )
                alert_seen_keys.update(seen)
                fetched += source_fetched
                created += source_created
                updated += source_updated

            health = await adapter.health_check()
            health.records_fetched = source_fetched
            if hasattr(adapter, "last_raw_points_fetched"):
                health.extra_metrics = {
                    **(health.extra_metrics or {}),
                    "raw_points_fetched": adapter.last_raw_points_fetched,
                    "clusters_persisted": source_fetched,
                }
            upsert_source_status(
                db,
                health,
                record_type=getattr(adapter, "record_type", "alert"),
            )

            logger.info(
                "Ingest source=%s type=%s fetched=%d created=%d updated=%d%s",
                adapter.source_id,
                getattr(adapter, "record_type", "alert"),
                source_fetched,
                source_created,
                source_updated,
                (
                    f" raw_points={adapter.last_raw_points_fetched}"
                    if hasattr(adapter, "last_raw_points_fetched")
                    else ""
                ),
            )
        except Exception as exc:
            logger.exception("Ingest failed for source %s", adapter.source_id)
            errors.append({"source": adapter.source_id, "error": str(exc)})

    deactivated = (
        expired_count
        + fixture_count
        + _deactivate_stale_alerts(db, adapters, alert_seen_keys, now)
        + _deactivate_stale_observed_events(db, adapters, event_seen_keys, now)
    )

    run.finished_at = utc_now()
    run.alerts_fetched = fetched
    run.alerts_created = created
    run.alerts_updated = updated
    run.alerts_deactivated = deactivated
    run.errors = errors
    if errors and fetched == 0:
        run.status = IngestRunStatus.FAILED
    elif errors:
        run.status = IngestRunStatus.PARTIAL
    else:
        run.status = IngestRunStatus.SUCCESS

    db.flush()
    db.refresh(run)

    if should_generate_briefing and run.status in (IngestRunStatus.SUCCESS, IngestRunStatus.PARTIAL):
        from app.services.briefing_service import generate_briefing as gen_briefing

        gen_briefing(db, briefing_type="auto")

    return run


def _deactivate_stale_alerts(
    db: Session,
    adapters: list,
    seen_keys: set[tuple[str, str]],
    now: datetime,
) -> int:
    deactivated = 0
    source_ids = {
        a.source_id for a in adapters if getattr(a, "record_type", "alert") == "alert"
    }
    if not source_ids:
        return 0

    active_alerts = db.scalars(
        select(Alert).where(Alert.is_active.is_(True), Alert.source.in_(source_ids))
    ).all()

    for alert in active_alerts:
        key = (alert.source, alert.source_alert_id)
        expired = is_expired(alert, now)
        not_seen = key not in seen_keys
        if not_seen or expired:
            alert.is_active = False
            deactivated += 1
    return deactivated


def _deactivate_stale_observed_events(
    db: Session,
    adapters: list,
    seen_keys: set[tuple[str, str]],
    now: datetime,
) -> int:
    deactivated = 0
    source_ids = {
        a.source_id for a in adapters if getattr(a, "record_type", "alert") == "observed_event"
    }
    if not source_ids:
        return 0

    active_events = db.scalars(
        select(ObservedEvent).where(
            ObservedEvent.is_active.is_(True), ObservedEvent.source.in_(source_ids)
        )
    ).all()

    for event in active_events:
        key = (event.source, event.source_event_id)
        expired = event.ends_at is not None and event.ends_at < now
        not_seen = key not in seen_keys
        if not_seen or expired:
            event.is_active = False
            deactivated += 1
    return deactivated
