"""Tests for trend spike detection."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.analysis.trends import detect_trend_anomalies
from app.models.alert import Alert


def _make_alert(**kwargs) -> Alert:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "source": "noaa",
        "source_alert_id": "test-1",
        "title": "Test Alert",
        "category": "weather",
        "severity": "moderate",
        "status": "actual",
        "country_code": "US",
        "issued_at": now,
        "ingested_at": now,
        "last_seen_at": now,
        "raw_payload": {},
        "fingerprint": "fp1",
        "is_active": True,
    }
    defaults.update(kwargs)
    return Alert(**defaults)


def test_spike_when_many_recent_alerts() -> None:
    """Active count exceeding recent ingest baseline triggers spike."""
    now = datetime.now(UTC)
    old = now - timedelta(days=10)
    alerts = [
        _make_alert(source_alert_id=f"old-{i}", fingerprint=f"ofp{i}", ingested_at=old)
        for i in range(5)
    ] + [
        _make_alert(source_alert_id=f"new-{i}", fingerprint=f"nfp{i}", ingested_at=now)
        for i in range(5)
    ]
    anomalies = detect_trend_anomalies(alerts, now=now)
    global_spikes = [a for a in anomalies if a.dimension == "global"]
    assert len(global_spikes) >= 1
    assert global_spikes[0].is_spike


def test_no_spike_stable_counts() -> None:
    now = datetime.now(UTC)
    # Alerts spread across the 7-day window → current ≈ rolling average
    alerts = []
    for i in range(7):
        day = now - timedelta(days=i)
        alerts.append(
            _make_alert(
                source_alert_id=f"a-{i}",
                fingerprint=f"afp{i}",
                ingested_at=day,
            )
        )
    anomalies = detect_trend_anomalies(alerts, now=now)
    assert len(anomalies) == 0
