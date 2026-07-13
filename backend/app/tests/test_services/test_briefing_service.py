"""Tests for briefing enrichment and by_source population."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.analysis.risk_score import compute_global_risk_score
from app.analysis.rule_briefing import generate_rule_briefing
from app.models.alert import Alert
from app.models.briefing import Briefing
from app.schemas.common import BriefingType
from app.services.briefing_service import (
    _finalize_briefing_content,
    enrich_briefing_content,
    prepare_briefing_for_response,
)


def _make_alert(**kwargs) -> Alert:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "source": "noaa",
        "source_alert_id": "test-1",
        "title": "Test alert",
        "category": "weather",
        "severity": "moderate",
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


def test_finalize_briefing_content_populates_by_source() -> None:
    alerts = [
        _make_alert(source="nina", fingerprint="fp-nina", source_alert_id="n1"),
        _make_alert(source="gdacs", fingerprint="fp-gdacs", source_alert_id="g1"),
        _make_alert(source="noaa", fingerprint="fp-noaa", source_alert_id="o1"),
    ]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=3)
    content = {"source_alert_ids": [str(a.id) for a in alerts], "by_source": []}

    finalized = _finalize_briefing_content(
        content, risk=risk, active_count=len(alerts), alerts=alerts
    )

    assert len(finalized["by_source"]) == 3
    sources = {item["source"] for item in finalized["by_source"]}
    assert sources == {"nina", "gdacs", "noaa"}


def test_enrich_briefing_content_from_legacy_dict_shape() -> None:
    alerts = [
        _make_alert(source="nina", fingerprint="fp-nina", source_alert_id="n1"),
        _make_alert(source="noaa", fingerprint="fp-noaa", source_alert_id="o1"),
    ]
    content = {
        "by_source": {"nina": 1, "noaa": 1},
        "source_alert_ids": [str(a.id) for a in alerts],
    }

    enriched = enrich_briefing_content(content, alerts=alerts)

    assert len(enriched["by_source"]) == 2
    by_source = {item["source"]: item for item in enriched["by_source"]}
    assert by_source["nina"]["label"] == "NINA/BBK"
    assert by_source["noaa"]["count"] == 1


def test_enrich_briefing_content_from_major_events_fallback() -> None:
    content = {
        "by_source": [],
        "major_events": [
            {"source": "nina", "alert_id": str(uuid4())},
            {"source": "gdacs", "alert_id": str(uuid4())},
            {"source": "noaa", "alert_id": str(uuid4())},
        ],
    }

    enriched = enrich_briefing_content(content)

    assert len(enriched["by_source"]) == 3


@pytest.mark.asyncio
async def test_api_enriches_legacy_briefing_without_by_source(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    alerts = db_session.query(Alert).filter(Alert.is_active.is_(True)).all()
    assert len(alerts) > 0

    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=len(alerts))
    content = generate_rule_briefing(alerts, risk=risk, hotspots=[])
    content.pop("by_source", None)

    briefing = Briefing(
        generated_at=datetime.now(UTC),
        type=BriefingType.RULE_BASED,
        overall_risk_score=risk.global_score,
        overall_confidence=content["overall_confidence"],
        content=content,
        source_alert_ids=[a.id for a in alerts],
        llm_model=None,
    )
    db_session.add(briefing)
    db_session.commit()

    response = client.get("/api/v1/briefings/latest")
    assert response.status_code == 200
    data = response.json()
    assert len(data["content"]["by_source"]) > 0
    sources = {item["source"] for item in data["content"]["by_source"]}
    assert sources <= {"nina", "gdacs", "noaa"}


def test_prepare_briefing_for_response_uses_snapshot_alerts(db_session) -> None:
    alerts = [
        _make_alert(source="nina", fingerprint="fp-nina", source_alert_id="n1"),
        _make_alert(source="gdacs", fingerprint="fp-gdacs", source_alert_id="g1"),
    ]
    for alert in alerts:
        db_session.add(alert)
    db_session.flush()

    content = {
        "active_count": 2,
        "source_alert_ids": [str(a.id) for a in alerts],
        "major_events": [],
    }
    briefing = Briefing(
        generated_at=datetime.now(UTC),
        type=BriefingType.RULE_BASED,
        overall_risk_score=10,
        overall_confidence="low",
        content=content,
        source_alert_ids=[a.id for a in alerts],
    )
    db_session.add(briefing)
    db_session.flush()

    prepared = prepare_briefing_for_response(db_session, briefing)

    assert len(prepared.content["by_source"]) == 2
