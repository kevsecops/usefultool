"""Data retention cleanup for inactive alerts and observed events."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.observed_event import ObservedEvent
from app.normalization.datetime_utils import utc_now

logger = get_logger(__name__)


def cleanup_inactive_alerts(
    db: Session,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> int:
    """Delete inactive alerts older than the retention window."""
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.alerts_retention_days
    if days <= 0:
        return 0

    now = now or utc_now()
    cutoff = now - timedelta(days=days)
    result = db.execute(
        delete(Alert).where(
            Alert.is_active.is_(False),
            Alert.last_seen_at < cutoff,
        )
    )
    deleted = result.rowcount or 0
    if deleted:
        logger.info("Retention: deleted %d inactive alerts older than %d days", deleted, days)
    return deleted


def cleanup_inactive_observed_events(
    db: Session,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> int:
    """Delete inactive observed events older than the retention window."""
    settings = get_settings()
    days = (
        retention_days
        if retention_days is not None
        else settings.observed_events_retention_days
    )
    if days <= 0:
        return 0

    now = now or utc_now()
    cutoff = now - timedelta(days=days)
    result = db.execute(
        delete(ObservedEvent).where(
            ObservedEvent.is_active.is_(False),
            ObservedEvent.last_seen_at < cutoff,
        )
    )
    deleted = result.rowcount or 0
    if deleted:
        logger.info(
            "Retention: deleted %d inactive observed events older than %d days",
            deleted,
            days,
        )
    return deleted


def run_retention_cleanup(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Run all configured retention cleanup tasks."""
    settings = get_settings()
    if not settings.retention_cleanup_enabled:
        return {"alerts_deleted": 0, "observed_events_deleted": 0}

    alerts_deleted = cleanup_inactive_alerts(db, now=now)
    observed_deleted = cleanup_inactive_observed_events(db, now=now)
    return {
        "alerts_deleted": alerts_deleted,
        "observed_events_deleted": observed_deleted,
    }
