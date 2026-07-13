"""Ingest service tests."""

import pytest
from sqlalchemy import func, select

from app.models.alert import Alert
from app.normalization.datetime_utils import utc_now
from app.normalization.fingerprint import generate_fingerprint
from app.services.ingest_service import run_ingest


@pytest.mark.asyncio
async def test_ingest_populates_alerts(db_session) -> None:
    run = await run_ingest(db_session)
    db_session.commit()
    assert run.status in ("success", "partial")
    assert run.alerts_fetched > 0
    assert run.alerts_created > 0

    count = db_session.scalar(select(func.count()).select_from(Alert))
    assert count == run.alerts_created


@pytest.mark.asyncio
async def test_ingest_is_idempotent(db_session) -> None:
    await run_ingest(db_session)
    db_session.commit()
    run2 = await run_ingest(db_session)
    db_session.commit()
    assert run2.alerts_created == 0
    assert run2.alerts_updated >= 0


@pytest.mark.asyncio
async def test_ingest_detects_updates(db_session) -> None:
    await run_ingest(db_session)
    db_session.commit()

    alert = db_session.scalar(select(Alert).where(Alert.source == "nina").limit(1))
    assert alert is not None
    original_title = alert.title
    alert.title = "Changed title for update test"
    db_session.commit()

    run = await run_ingest(db_session)
    db_session.commit()
    db_session.refresh(alert)
    assert run.alerts_updated >= 1
    assert alert.title != "Changed title for update test"
    assert alert.title == original_title


@pytest.mark.asyncio
async def test_ingest_deactivates_removed_alerts(db_session) -> None:
    await run_ingest(db_session, sources=["noaa"])
    db_session.commit()

    now = utc_now()
    orphan = Alert(
        source="noaa",
        source_alert_id="orphan-alert-not-in-feed",
        title="Orphan NOAA alert",
        category="other",
        severity="minor",
        status="actual",
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"test": True},
        fingerprint=generate_fingerprint(
            source="noaa",
            source_alert_id="orphan-alert-not-in-feed",
            title="Orphan NOAA alert",
            issued_at=now,
            severity="minor",
            category="other",
        ),
        is_active=True,
    )
    db_session.add(orphan)
    db_session.commit()

    run = await run_ingest(db_session, sources=["noaa"])
    db_session.commit()
    db_session.refresh(orphan)
    assert run.alerts_deactivated >= 1
    assert orphan.is_active is False

