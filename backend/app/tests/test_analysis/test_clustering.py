"""Tests for cluster detection."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.analysis.clustering import detect_hotspots
from app.models.alert import Alert


def _make_alert(**kwargs) -> Alert:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "source": "noaa",
        "source_alert_id": "test-1",
        "title": "Test Alert",
        "category": "weather",
        "severity": "severe",
        "status": "actual",
        "country_code": "US",
        "region": "Texas",
        "issued_at": now,
        "ingested_at": now,
        "last_seen_at": now,
        "raw_payload": {},
        "fingerprint": "fp1",
        "is_active": True,
    }
    defaults.update(kwargs)
    return Alert(**defaults)


def test_country_region_cluster_three_severe() -> None:
    alerts = [
        _make_alert(source_alert_id=f"t-{i}", fingerprint=f"fp{i}")
        for i in range(3)
    ]
    hotspots = detect_hotspots(alerts)
    assert len(hotspots) >= 1
    assert hotspots[0].region == "Texas, US"
    assert hotspots[0].count == 3
    assert hotspots[0].severe_or_extreme_count == 3


def test_no_cluster_below_threshold() -> None:
    alerts = [
        _make_alert(source_alert_id=f"t-{i}", fingerprint=f"fp{i}", severity="moderate")
        for i in range(2)
    ]
    hotspots = detect_hotspots(alerts)
    assert len(hotspots) == 0


def test_spatial_cluster_nearby_severe() -> None:
    base_lat, base_lon = 32.75, -97.33
    alerts = [
        _make_alert(
            source_alert_id=f"s-{i}",
            fingerprint=f"sfp{i}",
            latitude=base_lat + i * 0.01,
            longitude=base_lon + i * 0.01,
            region=None,
            country_code=None,
            severity="severe",
        )
        for i in range(3)
    ]
    hotspots = detect_hotspots(alerts)
    assert len(hotspots) >= 1
    assert hotspots[0].count >= 3


def test_country_category_cluster() -> None:
    alerts = [
        _make_alert(
            source_alert_id=f"c-{i}",
            fingerprint=f"cfp{i}",
            category="flood",
            severity="extreme",
            region=f"Region-{i}",
        )
        for i in range(3)
    ]
    hotspots = detect_hotspots(alerts)
    assert len(hotspots) >= 1
    assert hotspots[0].severe_or_extreme_count >= 3
