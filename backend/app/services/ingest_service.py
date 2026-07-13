"""Ingest orchestration service."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.ingest_run import IngestRun
from app.normalization.datetime_utils import utc_now
from app.normalization.fingerprint import generate_fingerprint
from app.normalization.geometry import geojson_to_wkt_element
from app.schemas.alert import CanonicalAlert
from app.schemas.common import IngestRunStatus
from app.sources.registry import get_adapters

logger = get_logger(__name__)


def _canonical_to_model(canonical: CanonicalAlert, now: datetime) -> Alert:
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
        is_active=True,
    )


def _update_alert(existing: Alert, canonical: CanonicalAlert, now: datetime) -> bool:
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
        "is_active": True,
    }
    for key, value in fields_to_update.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    return changed


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
    seen_keys: set[tuple[str, str]] = set()
    fetched = created = updated = 0
    errors: list[dict] = []

    for adapter in adapters:
        source_fetched = source_created = source_updated = 0
        try:
            raw_alerts = await adapter.fetch_alerts()
            for raw in raw_alerts:
                parsed = adapter.parse_alert(raw)
                canonical = adapter.normalize_alert(parsed)
                fetched += 1
                source_fetched += 1
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
                        source_updated += 1
                else:
                    db.add(_canonical_to_model(canonical, now))
                    created += 1
                    source_created += 1
            logger.info(
                "Ingest source=%s fetched=%d created=%d updated=%d",
                adapter.source_id,
                source_fetched,
                source_created,
                source_updated,
            )
        except Exception as exc:
            logger.exception("Ingest failed for source %s", adapter.source_id)
            errors.append({"source": adapter.source_id, "error": str(exc)})

    deactivated = _deactivate_stale_alerts(db, adapters, seen_keys, now)

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
    source_ids = {a.source_id for a in adapters}
    active_alerts = db.scalars(
        select(Alert).where(Alert.is_active.is_(True), Alert.source.in_(source_ids))
    ).all()

    for alert in active_alerts:
        key = (alert.source, alert.source_alert_id)
        expired = alert.expires_at is not None and alert.expires_at < now
        not_seen = key not in seen_keys
        if not_seen or expired:
            alert.is_active = False
            deactivated += 1
    return deactivated
