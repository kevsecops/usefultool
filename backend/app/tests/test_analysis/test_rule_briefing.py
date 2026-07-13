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


def test_briefing_multi_source_breakdown() -> None:
    """Briefing must reflect all live sources with per-source counts and countries."""
    alerts = [
        _make_alert(
            source="nina",
            source_alert_id="nina-1",
            fingerprint="fp-nina",
            title="Hochwasserwarnung Saarland",
            country_code="DE",
            region="Saarland",
            category="flood",
        ),
        _make_alert(
            source="gdacs",
            source_alert_id="gdacs-1",
            fingerprint="fp-gdacs",
            title="Earthquake in Papua New Guinea",
            country_code="PG",
            region="Papua New Guinea",
            category="earthquake",
            severity="moderate",
        ),
        _make_alert(
            source="noaa",
            source_alert_id="noaa-1",
            fingerprint="fp-noaa",
            title="Flood Advisory in Travis County",
            country_code="US",
            region="Texas",
            category="flood",
        ),
        _make_alert(
            source="noaa",
            source_alert_id="noaa-2",
            fingerprint="fp-noaa-2",
            title="Severe Thunderstorm Warning",
            country_code="US",
            region="Oklahoma",
            category="weather",
            severity="extreme",
        ),
    ]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=4)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=[])

    assert len(briefing["by_source"]) == 3
    by_source = {item["source"]: item for item in briefing["by_source"]}
    assert by_source["nina"]["count"] == 1
    assert by_source["gdacs"]["count"] == 1
    assert by_source["noaa"]["count"] == 2
    assert by_source["nina"]["label"] == "NINA/BBK"
    assert "NINA/BBK" in briefing["summary"]
    assert "GDACS" in briefing["summary"]
    assert "NOAA/NWS" in briefing["summary"]
    assert any(item["code"] == "US" and item["count"] == 2 for item in briefing["top_countries"])
    assert any(item["code"] == "DE" for item in briefing["top_countries"])
    assert len(briefing["source_alert_ids"]) == 4
    sources_in_events = {event["source"] for event in briefing["major_events"]}
    assert sources_in_events <= {"nina", "gdacs", "noaa"}
    assert any("NINA/BBK" in lim for lim in briefing["limitations"])


def test_briefing_snapshot_fields_consistent() -> None:
    """active_count, overall_risk_score, and summary must agree at generation time."""
    alerts = [
        _make_alert(source="nina", source_alert_id="n1", fingerprint="fp-n1", country_code="DE"),
        _make_alert(source="noaa", source_alert_id="n2", fingerprint="fp-n2", country_code="US"),
    ]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=2)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=[])

    assert briefing["active_count"] == 2
    assert briefing["overall_risk_score"] == risk.global_score
    assert "2 aktive Warnungen" in briefing["summary"]
    assert f"Global Risk Score: {risk.global_score}/100" in briefing["summary"]
    assert len(briefing["source_alert_ids"]) == briefing["active_count"]


def test_briefing_implications_wildfire_uses_schema_domains() -> None:
    """Wildfire alerts must not emit non-schema implication keys (e.g. environmental)."""
    alerts = [
        _make_alert(
            category="wildfire",
            title="Wildfire Warning in Sonoma County",
            source_alert_id="wf-1",
            fingerprint="fp-wf",
        ),
        _make_alert(
            category="flood",
            title="Flood Advisory in Napa County",
            source_alert_id="fl-1",
            fingerprint="fp-fl",
        ),
    ]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=2)
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=[])

    implications = briefing["potential_implications"]
    assert set(implications.keys()) == {
        "economy",
        "logistics",
        "infrastructure",
        "technology",
        "finance",
    }
    assert len(implications["logistics"]) > 0
    assert any("Luftqualität" in s for s in implications["infrastructure"])


def test_affected_regions_lists_all_countries() -> None:
    """affected_regions must list every country with active alerts, not only hotspot clusters."""
    alerts = [
        _make_alert(
            source="nina",
            source_alert_id="de-1",
            fingerprint="fp-de-1",
            country_code="DE",
            country_name="Germany",
            region="Saarland",
            severity="moderate",
        ),
        _make_alert(
            source="nina",
            source_alert_id="de-2",
            fingerprint="fp-de-2",
            country_code="DE",
            country_name="Germany",
            region="Bayern",
            severity="moderate",
        ),
        _make_alert(
            source="nina",
            source_alert_id="de-3",
            fingerprint="fp-de-3",
            country_code="DE",
            country_name="Germany",
            region="Köln",
            severity="moderate",
        ),
        _make_alert(
            source="nina",
            source_alert_id="de-4",
            fingerprint="fp-de-4",
            country_code="DE",
            country_name="Germany",
            region="BW",
            severity="severe",
        ),
        _make_alert(
            source="gdacs",
            source_alert_id="pg-1",
            fingerprint="fp-pg",
            country_code="PG",
            country_name="Papua New Guinea",
            category="earthquake",
            severity="moderate",
        ),
        _make_alert(
            source="gdacs",
            source_alert_id="hn-1",
            fingerprint="fp-hn",
            country_code="HN",
            country_name="Honduras",
            category="weather",
            severity="severe",
        ),
        _make_alert(
            source="noaa",
            source_alert_id="us-1",
            fingerprint="fp-us-1",
            country_code="US",
            country_name="United States",
            region="Texas",
            severity="minor",
        ),
        _make_alert(
            source="noaa",
            source_alert_id="us-2",
            fingerprint="fp-us-2",
            country_code="US",
            country_name="United States",
            region="California",
            severity="severe",
        ),
        _make_alert(
            source="gdacs",
            source_alert_id="id-1",
            fingerprint="fp-id",
            country_code="ID",
            country_name="Indonesia",
            category="volcano",
            severity="minor",
        ),
    ]
    hotspots = detect_hotspots(alerts)

    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=len(alerts))
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=hotspots)

    region_codes = {item.get("country_code") for item in briefing["affected_regions"]}
    top_codes = {item["code"] for item in briefing["top_countries"]}
    assert region_codes == top_codes
    assert region_codes == {"DE", "US", "PG", "HN", "ID"}

    de_region = next(item for item in briefing["affected_regions"] if item["country_code"] == "DE")
    assert de_region["alert_count"] == 4
    us_region = next(item for item in briefing["affected_regions"] if item["country_code"] == "US")
    assert us_region["alert_count"] == 2


def test_briefing_internal_consistency_mixed_sources() -> None:
    """top_countries, by_source, and affected_regions must agree on the same snapshot."""
    alerts = [
        _make_alert(source="nina", source_alert_id="n1", fingerprint="fp-n1", country_code="DE"),
        _make_alert(source="nina", source_alert_id="n2", fingerprint="fp-n2", country_code="DE"),
        _make_alert(source="nina", source_alert_id="n3", fingerprint="fp-n3", country_code="DE"),
        _make_alert(source="nina", source_alert_id="n4", fingerprint="fp-n4", country_code="DE"),
        _make_alert(
            source="gdacs",
            source_alert_id="g1",
            fingerprint="fp-g1",
            country_code="PG",
            severity="moderate",
        ),
        _make_alert(
            source="noaa",
            source_alert_id="o1",
            fingerprint="fp-o1",
            country_code="US",
            severity="severe",
        ),
        _make_alert(
            source="noaa",
            source_alert_id="o2",
            fingerprint="fp-o2",
            country_code="US",
            severity="minor",
        ),
        _make_alert(
            source="gdacs",
            source_alert_id="g2",
            fingerprint="fp-g2",
            country_code="HN",
            severity="severe",
        ),
        _make_alert(
            source="gdacs",
            source_alert_id="g3",
            fingerprint="fp-g3",
            country_code="ID",
            severity="minor",
        ),
    ]
    hotspots = detect_hotspots(alerts)
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=len(alerts))
    briefing = generate_rule_briefing(alerts, risk=risk, hotspots=hotspots)

    assert briefing["active_count"] == len(alerts)
    assert sum(item["count"] for item in briefing["by_source"]) == briefing["active_count"]
    assert sum(item["count"] for item in briefing["top_countries"]) == briefing["active_count"]
    assert sum(item["alert_count"] for item in briefing["affected_regions"]) == briefing["active_count"]

    country_counts = {item["code"]: item["count"] for item in briefing["top_countries"]}
    region_counts = {item["country_code"]: item["alert_count"] for item in briefing["affected_regions"]}
    assert country_counts == region_counts
