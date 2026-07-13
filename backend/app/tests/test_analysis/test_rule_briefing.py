"""Tests for rule-based briefing generation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.analysis.clustering import detect_hotspots
from app.analysis.risk_score import compute_global_risk_score
from app.analysis.rule_briefing import generate_rule_briefing
from app.analysis.trends import detect_trend_anomalies
from app.models.alert import Alert


def _make_alert(**kwargs) -> Alert:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "source": "noaa",
        "source_alert_id": "test-1",
        "title": "Flood Advisory in Travis County",
        "category": "flood",
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


def test_briefing_contains_only_factual_data() -> None:
    alerts = [_make_alert()]
    hotspots = detect_hotspots(alerts)
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=1)
    anomalies = detect_trend_anomalies(alerts)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=hotspots, anomalies=anomalies)

    assert briefing["type"] == "rule_based"
    assert "Flood Advisory" in briefing["summary"] or "1 aktive" in briefing["summary"]
    assert str(alerts[0].id) in briefing["source_alert_ids"]
    assert briefing["major_events"][0]["title"] == "Flood Advisory in Travis County"
    assert briefing["major_events"][0]["alert_id"] == str(alerts[0].id)


def test_briefing_no_hallucinated_alert_ids() -> None:
    alerts = [_make_alert(), _make_alert(source_alert_id="t-2", fingerprint="fp2")]
    hotspots = detect_hotspots(alerts)
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=2)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=hotspots)

    valid_ids = {str(a.id) for a in alerts}
    for aid in briefing["source_alert_ids"]:
        assert aid in valid_ids
    for event in briefing["major_events"]:
        assert event["alert_id"] in valid_ids


def test_briefing_has_limitations() -> None:
    alerts = [_make_alert()]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=1)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=[])
    assert any("Regelbasierte" in lim for lim in briefing["limitations"])


def test_briefing_implications_conservative_language() -> None:
    alerts = [_make_alert(category="flood")]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=1)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=[])
    logistics = briefing["potential_implications"]["logistics"]
    assert len(logistics) > 0
    assert any("Mögliche" in s or "Potenzielle" in s for s in logistics)
