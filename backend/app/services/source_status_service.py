"""Persist source health metadata."""

from sqlalchemy.orm import Session

from app.models.source_status import SourceStatus
from app.normalization.datetime_utils import utc_now
from app.sources.base import SourceHealth


def upsert_source_status(db: Session, health: SourceHealth, *, record_type: str) -> None:
    now = utc_now()
    existing = db.get(SourceStatus, health.source)
    if existing:
        existing.record_type = record_type
        existing.is_healthy = health.is_healthy
        existing.checked_at = health.checked_at
        existing.latency_ms = health.latency_ms
        existing.last_success_at = health.last_success_at
        existing.error_message = health.error_message
        existing.ingest_mode = health.ingest_mode
        existing.records_fetched = health.records_fetched
        existing.updated_at = now
        return

    db.add(
        SourceStatus(
            source=health.source,
            record_type=record_type,
            is_healthy=health.is_healthy,
            checked_at=health.checked_at,
            latency_ms=health.latency_ms,
            last_success_at=health.last_success_at,
            error_message=health.error_message,
            ingest_mode=health.ingest_mode,
            records_fetched=health.records_fetched,
            updated_at=now,
        )
    )
