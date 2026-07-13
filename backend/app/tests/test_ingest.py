"""Ingest service tests."""

from datetime import timedelta

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
async def test_ingest_detects_updates(db_session, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    await run_ingest(db_session, sources=["nina"])
    db_session.commit()

    alert = db_session.scalar(select(Alert).where(Alert.source == "nina").limit(1))
    assert alert is not None
    original_title = alert.title
    alert.title = "Changed title for update test"
    db_session.commit()

    run = await run_ingest(db_session, sources=["nina"])
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


@pytest.mark.asyncio
async def test_ingest_isolates_source_failures(db_session, monkeypatch) -> None:
    from app.sources.nina import NinaSourceAdapter

    async def failing_fetch(self):
        raise RuntimeError("NINA unavailable")

    monkeypatch.setattr(NinaSourceAdapter, "fetch_alerts", failing_fetch)

    run = await run_ingest(db_session)
    db_session.commit()

    assert run.status == "partial"
    assert any(err["source"] == "nina" for err in run.errors)
    assert run.alerts_fetched > 0


@pytest.mark.asyncio
async def test_ingest_auto_generates_briefing(db_session, monkeypatch) -> None:
    """Default ingest should create a briefing snapshot aligned with live alerts."""
    from app.models.briefing import Briefing
    from app.services.briefing_service import get_latest_briefing
    from sqlalchemy import func, select

    monkeypatch.setenv("AUTO_GENERATE_BRIEFING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    run = await run_ingest(db_session)
    db_session.commit()

    assert run.status in ("success", "partial")
    count = db_session.scalar(select(func.count()).select_from(Briefing))
    assert count == 1

    briefing = get_latest_briefing(db_session)
    assert briefing is not None
    assert briefing.overall_risk_score == briefing.content["overall_risk_score"]
    assert briefing.content["active_count"] > 0
    assert len(briefing.content["by_source"]) > 0


@pytest.mark.asyncio
async def test_ingest_skips_briefing_when_disabled(db_session, monkeypatch) -> None:
    from app.models.briefing import Briefing
    from sqlalchemy import func, select

    monkeypatch.setenv("AUTO_GENERATE_BRIEFING", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    await run_ingest(db_session)
    db_session.commit()

    count = db_session.scalar(select(func.count()).select_from(Briefing))
    assert count == 0


@pytest.mark.asyncio
async def test_ingest_dedup_by_source_and_id(db_session) -> None:
    await run_ingest(db_session)
    db_session.commit()

    count_before = db_session.scalar(select(func.count()).select_from(Alert))
    run2 = await run_ingest(db_session)
    db_session.commit()
    count_after = db_session.scalar(select(func.count()).select_from(Alert))

    assert run2.alerts_created == 0
    assert count_before == count_after

    sources = db_session.scalars(select(Alert.source).distinct()).all()
    assert "nina" in sources
    assert "gdacs" in sources
    assert "noaa" in sources


@pytest.mark.asyncio
async def test_ingest_deactivates_expired_alerts(db_session) -> None:
    """Alerts past expires_at must be marked inactive during ingest."""
    now = utc_now()
    expired = Alert(
        source="nina",
        source_alert_id="expired-january-flood",
        title="Hochwasserwarnung Saarland",
        category="flood",
        severity="moderate",
        status="actual",
        country_code="DE",
        issued_at=now,
        expires_at=now - timedelta(hours=6),
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"test": True},
        fingerprint=generate_fingerprint(
            source="nina",
            source_alert_id="expired-january-flood",
            title="Hochwasserwarnung Saarland",
            issued_at=now,
            severity="moderate",
            category="flood",
        ),
        is_active=True,
    )
    db_session.add(expired)
    db_session.commit()

    run = await run_ingest(db_session)
    db_session.commit()
    db_session.refresh(expired)

    assert run.alerts_deactivated >= 1
    assert expired.is_active is False


@pytest.mark.asyncio
async def test_fixture_dates_refreshed_on_ingest(db_session) -> None:
    """January NINA fixture must get future expires_at when loaded via fixture_loader."""
    now = utc_now()
    await run_ingest(db_session, sources=["nina"])
    db_session.commit()

    alert = db_session.scalar(
        select(Alert).where(Alert.source_alert_id.like("mow.DEMO-%")).limit(1)
    )
    assert alert is not None
    assert alert.expires_at is not None
    assert alert.expires_at > now
    assert alert.is_active is True


@pytest.mark.asyncio
async def test_live_nina_ingest_deactivates_stale_fixture_alerts(db_session, monkeypatch) -> None:
    """Fixture-origin NINA alerts must be deactivated when not in live feed."""
    from app.core.config import get_settings
    from app.sources.nina import NinaSourceAdapter

    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    now = utc_now()
    stale_fixture = Alert(
        source="nina",
        source_alert_id="mow.DEMO-SL-FLOOD-20260713-000",
        title="Hochwasserwarnung Saarland",
        category="flood",
        severity="moderate",
        status="actual",
        country_code="DE",
        issued_at=now,
        expires_at=now + timedelta(hours=24),
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"_ingest_mode": "fixture", "test": True},
        fingerprint=generate_fingerprint(
            source="nina",
            source_alert_id="mow.DEMO-SL-FLOOD-20260713-000",
            title="Hochwasserwarnung Saarland",
            issued_at=now,
            severity="moderate",
            category="flood",
        ),
        is_active=True,
    )
    db_session.add(stale_fixture)
    db_session.commit()

    async def empty_live_fetch(self):
        self._last_ingest_mode = "live"
        self._last_fetch_count = 0
        return []

    monkeypatch.setattr(NinaSourceAdapter, "fetch_alerts", empty_live_fetch)

    run = await run_ingest(db_session, sources=["nina"])
    db_session.commit()
    db_session.refresh(stale_fixture)

    assert run.alerts_deactivated >= 1
    assert stale_fixture.is_active is False

