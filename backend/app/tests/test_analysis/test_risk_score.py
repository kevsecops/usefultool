"""Tests for risk score calculation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.analysis.risk_score import (
    SEVERITY_WEIGHTS,
    compute_alert_score,
    compute_global_risk_score,
    compute_trend_modifier,
)
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
        "issued_at": now - timedelta(hours=1),
        "ingested_at": now,
        "last_seen_at": now,
        "raw_payload": {},
        "fingerprint": "abc123",
        "is_active": True,
    }
    defaults.update(kwargs)
    return Alert(**defaults)


def test_severity_weights() -> None:
    assert SEVERITY_WEIGHTS["minor"] == 1
    assert SEVERITY_WEIGHTS["moderate"] == 3
    assert SEVERITY_WEIGHTS["severe"] == 6
    assert SEVERITY_WEIGHTS["extreme"] == 10


def test_alert_score_base_severe() -> None:
    now = datetime.now(UTC)
    alert = _make_alert(severity="severe")
    detail = compute_alert_score(alert, now)
    assert detail.base_weight == 6
    assert detail.alert_score == 6.0


def test_alert_score_with_urgency_immediate() -> None:
    now = datetime.now(UTC)
    alert = _make_alert(severity="severe", urgency="immediate")
    detail = compute_alert_score(alert, now)
    assert detail.urgency_mod == 1.5
    assert detail.alert_score == 9.0


def test_alert_score_with_certainty_observed() -> None:
    now = datetime.now(UTC)
    alert = _make_alert(severity="moderate", certainty="observed")
    detail = compute_alert_score(alert, now)
    assert detail.certainty_mod == 1.3
    assert detail.alert_score == pytest.approx(3.9)


def test_trend_modifier_decline() -> None:
    assert compute_trend_modifier(5, 10) == 0.9


def test_trend_modifier_spike() -> None:
    assert compute_trend_modifier(25, 10) == 1.3


def test_global_score_ten_severe_alerts() -> None:
    """10 severe alerts without modifiers → score ≈ 60 per docs."""
    now = datetime.now(UTC)
    alerts = [_make_alert(source_alert_id=f"s-{i}") for i in range(10)]
    result = compute_global_risk_score(
        alerts,
        now=now,
        cluster_bonuses=[],
        trend_modifier=1.0,
        rolling_avg_active=10,
    )
    assert result.global_score == 60
    assert result.raw_total == 60.0


def test_global_score_capped_at_100() -> None:
    now = datetime.now(UTC)
    alerts = [
        _make_alert(
            source_alert_id=f"x-{i}",
            severity="extreme",
            urgency="immediate",
            certainty="observed",
        )
        for i in range(20)
    ]
    result = compute_global_risk_score(alerts, now=now, trend_modifier=1.3)
    assert result.global_score <= 100


def test_global_score_zero_when_no_alerts() -> None:
    result = compute_global_risk_score([], trend_modifier=1.0, rolling_avg_active=0)
    assert result.global_score == 0
