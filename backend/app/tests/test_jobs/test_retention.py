"""Tests for data retention cleanup."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.alert import Alert
from app.models.observed_event import ObservedEvent
from app.services.retention_service import (
    cleanup_inactive_alerts,
    cleanup_inactive_observed_events,
    run_retention_cleanup,
)


def _now() -> datetime:
    return datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _make_alert(*, active: bool, last_seen_at: datetime) -> Alert:
    return Alert(
        id=uuid4(),
        source="noaa",
        source_alert_id=f"alert-{uuid4()}",
        title="Test alert",
        category="weather",
        severity="moderate",
        status="actual",
        issued_at=last_seen_at,
        ingested_at=last_seen_at,
        last_seen_at=last_seen_at,
        raw_payload={"id": "test"},
        is_active=active,
        fingerprint=f"fp-{uuid4()}",
    )


def _make_observed_event(*, active: bool, last_seen_at: datetime) -> ObservedEvent:
    return ObservedEvent(
        id=uuid4(),
        source="usgs",
        source_event_id=f"event-{uuid4()}",
        title="Test event",
        category="earthquake",
        severity="moderate",
        status="automatic",
        issued_at=last_seen_at,
        ingested_at=last_seen_at,
        last_seen_at=last_seen_at,
        raw_payload={"id": "test"},
        is_active=active,
        fingerprint=f"fp-{uuid4()}",
    )


def test_cleanup_deletes_old_inactive_alerts(db_session, monkeypatch) -> None:
    monkeypatch.setenv("ALERTS_RETENTION_DAYS", "30")
    from app.core.config import get_settings

    get_settings.cache_clear()
    now = _now()

    old_inactive = _make_alert(active=False, last_seen_at=now - timedelta(days=45))
    recent_inactive = _make_alert(active=False, last_seen_at=now - timedelta(days=5))
    old_active = _make_alert(active=True, last_seen_at=now - timedelta(days=45))
    db_session.add_all([old_inactive, recent_inactive, old_active])
    db_session.flush()

    deleted = cleanup_inactive_alerts(db_session, now=now)
    assert deleted == 1


def test_cleanup_deletes_old_inactive_observed_events(db_session, monkeypatch) -> None:
    monkeypatch.setenv("OBSERVED_EVENTS_RETENTION_DAYS", "90")
    from app.core.config import get_settings

    get_settings.cache_clear()
    now = _now()

    old_inactive = _make_observed_event(active=False, last_seen_at=now - timedelta(days=120))
    recent_inactive = _make_observed_event(active=False, last_seen_at=now - timedelta(days=10))
    old_active = _make_observed_event(active=True, last_seen_at=now - timedelta(days=120))
    db_session.add_all([old_inactive, recent_inactive, old_active])
    db_session.flush()

    deleted = cleanup_inactive_observed_events(db_session, now=now)
    assert deleted == 1


def test_run_retention_cleanup_respects_disabled_flag(db_session, monkeypatch) -> None:
    monkeypatch.setenv("RETENTION_CLEANUP_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    now = _now()
    db_session.add(_make_alert(active=False, last_seen_at=now - timedelta(days=120)))
    db_session.flush()

    result = run_retention_cleanup(db_session, now=now)
    assert result == {"alerts_deleted": 0, "observed_events_deleted": 0}
