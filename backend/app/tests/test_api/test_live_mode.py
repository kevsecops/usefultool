"""Integration tests for live-only mode (DEMO_MODE=false)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.alert import Alert
from app.normalization.datetime_utils import utc_now
from app.normalization.fingerprint import generate_fingerprint
from app.sources.nina import NinaSourceAdapter


@pytest.mark.asyncio
async def test_live_mode_api_excludes_fixture_alerts(client, db_session, monkeypatch) -> None:
    """When DEMO_MODE=false, public API must return only live alerts."""
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    now = utc_now()

    fixture_alert = Alert(
        source="nina",
        source_alert_id="mow.DEMO-SL-FLOOD-20260713-000",
        title="Hochwasserwarnung Saarland",
        category="flood",
        severity="moderate",
        status="actual",
        country_code="DE",
        latitude=49.4,
        longitude=7.0,
        issued_at=now,
        expires_at=now + timedelta(hours=24),
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"_ingest_mode": "fixture"},
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
    live_alert = Alert(
        source="nina",
        source_alert_id="mow.LIVE-REAL-WARNING-001",
        title="Amtliche Unwetterwarnung",
        category="weather",
        severity="severe",
        status="actual",
        country_code="DE",
        latitude=52.5,
        longitude=13.4,
        issued_at=now,
        expires_at=now + timedelta(hours=12),
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"_ingest_mode": "live"},
        fingerprint=generate_fingerprint(
            source="nina",
            source_alert_id="mow.LIVE-REAL-WARNING-001",
            title="Amtliche Unwetterwarnung",
            issued_at=now,
            severity="severe",
            category="weather",
        ),
        is_active=True,
    )
    db_session.add_all([fixture_alert, live_alert])
    db_session.commit()

    response = client.get("/api/v1/alerts", params={"active": "true"})
    assert response.status_code == 200
    data = response.json()
    ids = {item["source_alert_id"] for item in data["items"]}
    assert "mow.LIVE-REAL-WARNING-001" in ids
    assert "mow.DEMO-SL-FLOOD-20260713-000" not in ids
    for item in data["items"]:
        assert item.get("ingest_mode") != "fixture"


@pytest.mark.asyncio
async def test_startup_deactivates_fixture_alerts_when_live_mode(
    client, db_session, monkeypatch
) -> None:
    """Startup cleanup must deactivate fixture rows when DEMO_MODE=false."""
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()

    now = utc_now()
    fixture_alert = Alert(
        source="nina",
        source_alert_id="mow.DEMO-STARTUP-TEST",
        title="Fixture startup test",
        category="flood",
        severity="moderate",
        status="actual",
        issued_at=now,
        expires_at=now + timedelta(hours=24),
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"_ingest_mode": "fixture"},
        fingerprint=generate_fingerprint(
            source="nina",
            source_alert_id="mow.DEMO-STARTUP-TEST",
            title="Fixture startup test",
            issued_at=now,
            severity="moderate",
            category="flood",
        ),
        is_active=True,
    )
    db_session.add(fixture_alert)
    db_session.commit()

    from app.services.alert_fixture import deactivate_fixture_alerts

    count = deactivate_fixture_alerts(db_session)
    db_session.commit()
    db_session.refresh(fixture_alert)

    assert count == 1
    assert fixture_alert.is_active is False


@pytest.mark.asyncio
async def test_health_reports_live_mode_metrics(client, db_session, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["demo_mode"] is False
    assert "scheduler" in data
    assert "alert_counts" in data
    assert "last_ingest_status" in data
    assert "active_alert_count" in data


@pytest.mark.asyncio
async def test_admin_status_requires_token(client) -> None:
    response = client.get("/api/v1/admin/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_status_with_token(client, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    response = client.get(
        "/api/v1/admin/status",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["demo_mode"] is False
    assert "metrics" in data
    assert "recent_ingest_runs" in data
    assert "scheduler" in data


@pytest.mark.asyncio
async def test_mock_live_ingest_populates_only_live_alerts(db_session, monkeypatch) -> None:
    """DEMO_MODE=false with mocked live NINA must not surface fixture alerts via API filter."""
    from app.core.config import get_settings
    from app.services.ingest_service import run_ingest

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    now = utc_now()
    stale = Alert(
        source="nina",
        source_alert_id="mow.DEMO-STALE",
        title="Stale fixture",
        category="flood",
        severity="moderate",
        status="actual",
        issued_at=now,
        expires_at=now + timedelta(hours=24),
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"_ingest_mode": "fixture"},
        fingerprint=generate_fingerprint(
            source="nina",
            source_alert_id="mow.DEMO-STALE",
            title="Stale fixture",
            issued_at=now,
            severity="moderate",
            category="flood",
        ),
        is_active=True,
    )
    db_session.add(stale)
    db_session.commit()

    async def mock_live_fetch(self):
        self._last_ingest_mode = "live"
        self._last_fetch_count = 1
        from app.sources.base import RawAlertPayload

        return [
            RawAlertPayload(
                source="nina",
                data={"id": "mow.LIVE-MOCK-001", "title": "Live mock"},
                ingest_mode="live",
            )
        ]

    def mock_parse(self, raw):
        from app.sources.base import ParsedAlert

        return ParsedAlert(
            source="nina",
            source_alert_id="mow.LIVE-MOCK-001",
            fields={"ingest_mode": "live"},
            raw_payload=raw.data,
        )

    def mock_normalize(self, parsed):
        from app.schemas.alert import CanonicalAlert
        from app.schemas.common import AlertSource, AlertStatus, Category, Severity

        return CanonicalAlert(
            source=AlertSource.NINA,
            source_alert_id="mow.LIVE-MOCK-001",
            title="Live mock warning",
            category=Category.WEATHER,
            severity=Severity.MODERATE,
            status=AlertStatus.ACTUAL,
            issued_at=now,
            expires_at=now + timedelta(hours=6),
            raw_payload={"_ingest_mode": "live"},
        )

    monkeypatch.setattr(NinaSourceAdapter, "fetch_alerts", mock_live_fetch)
    monkeypatch.setattr(NinaSourceAdapter, "parse_alert", mock_parse)
    monkeypatch.setattr(NinaSourceAdapter, "normalize_alert", mock_normalize)

    await run_ingest(db_session, sources=["nina"])
    db_session.commit()

    active_nina = db_session.scalars(
        select(Alert).where(Alert.source == "nina", Alert.is_active.is_(True))
    ).all()
    assert all("DEMO" not in alert.source_alert_id for alert in active_nina)
    assert any(alert.source_alert_id == "mow.LIVE-MOCK-001" for alert in active_nina)
