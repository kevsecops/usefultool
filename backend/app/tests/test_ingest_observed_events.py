"""Ingest tests for observed events."""

import pytest
from sqlalchemy import func, select

from app.models.observed_event import ObservedEvent
from app.services.ingest_service import run_ingest


@pytest.mark.asyncio
async def test_usgs_ingest_populates_observed_events(db_session) -> None:
    run = await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    assert run.status == "success"
    assert run.alerts_fetched == 0
    assert run.alerts_created == 0

    count = db_session.scalar(select(func.count()).select_from(ObservedEvent))
    assert count == 3


@pytest.mark.asyncio
async def test_usgs_ingest_idempotent(db_session) -> None:
    await run_ingest(db_session, sources=["usgs"])
    db_session.commit()
    run2 = await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    assert run2.alerts_created == 0
    count = db_session.scalar(select(func.count()).select_from(ObservedEvent))
    assert count == 3


@pytest.mark.asyncio
async def test_usgs_ingest_deactivates_stale_events(db_session) -> None:
    from app.normalization.datetime_utils import utc_now
    from app.normalization.fingerprint import generate_observed_event_fingerprint

    now = utc_now()
    orphan = ObservedEvent(
        source="usgs",
        source_event_id="orphan-usgs-event",
        title="Orphan USGS event",
        category="earthquake",
        severity="minor",
        status="automatic",
        confidence="low",
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"test": True},
        fingerprint=generate_observed_event_fingerprint(
            source="usgs",
            source_event_id="orphan-usgs-event",
            title="Orphan USGS event",
            issued_at=now,
            severity="minor",
            category="earthquake",
        ),
        is_active=True,
    )
    db_session.add(orphan)
    db_session.commit()

    run = await run_ingest(db_session, sources=["usgs"])
    db_session.commit()
    db_session.refresh(orphan)

    assert run.alerts_deactivated >= 1
    assert orphan.is_active is False


@pytest.mark.asyncio
async def test_alert_ingest_unaffected_by_usgs(db_session) -> None:
    """Full ingest must still populate alerts from existing sources."""
    from app.models.alert import Alert

    run = await run_ingest(db_session)
    db_session.commit()

    assert run.alerts_fetched > 0
    alert_count = db_session.scalar(select(func.count()).select_from(Alert))
    usgs_count = db_session.scalar(
        select(func.count()).select_from(ObservedEvent).where(ObservedEvent.source == "usgs")
    )
    assert alert_count > 0
    assert usgs_count == 3
