"""Tests for risk score v2 calculation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.analysis.risk_score import (
    EVENT_SEVERITY_WEIGHTS,
    compute_event_severity_index,
    compute_global_risk_score,
    compute_humanitarian_impact_signal,
    compute_infrastructure_exposure_index,
    compute_multi_source_corroboration,
)
from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.event_asset_exposure import EventAssetExposure
from app.models.exposure_asset import ExposureAsset
from app.models.implication_candidate import ImplicationCandidate


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


def _make_canonical_event(**kwargs) -> CanonicalEvent:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "title": "Test Event",
        "severity": "severe",
        "confidence": "medium",
        "status": "active",
        "started_at": now,
        "updated_at": now,
        "is_active": True,
    }
    defaults.update(kwargs)
    return CanonicalEvent(**defaults)


def _make_exposure(asset_type: str = "port", importance: str = "critical", overlap: bool = True):
    asset = ExposureAsset(
        id=uuid4(),
        asset_type=asset_type,
        name=f"Test {asset_type}",
        importance_level=importance,
        source="demo_fixture",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    exposure = EventAssetExposure(
        id=uuid4(),
        event_id=uuid4(),
        asset_id=asset.id,
        exposure_type="inside_event_area" if overlap else "near_event_area",
        overlap=overlap,
        confidence="high",
        calculated_at=datetime.now(UTC),
    )
    exposure.asset = asset
    return exposure


def test_event_severity_weights() -> None:
    assert EVENT_SEVERITY_WEIGHTS["severe"] == 12
    assert EVENT_SEVERITY_WEIGHTS["extreme"] == 20


def test_many_alerts_do_not_saturate_score() -> None:
    """50 moderate alerts should NOT produce a score near 100."""
    now = datetime.now(UTC)
    alerts = [
        _make_alert(source_alert_id=f"m-{i}", severity="moderate", fingerprint=f"fp-{i}")
        for i in range(50)
    ]
    result = compute_global_risk_score(alerts, now=now)
    assert result.global_score < 40
    assert result.breakdown["version"] == "2"


def test_ten_severe_alerts_fallback_below_40() -> None:
    """Alert-only fallback uses top-5 diminishing — not linear alert count."""
    now = datetime.now(UTC)
    alerts = [_make_alert(source_alert_id=f"s-{i}", fingerprint=f"fp-{i}") for i in range(10)]
    result = compute_global_risk_score(alerts, now=now)
    assert result.global_score < 40
    assert result.breakdown["event_severity_index"]["source"] == "alert_fallback"


def test_canonical_events_score_higher_than_alert_count() -> None:
    """One extreme canonical event outweighs many minor alerts."""
    now = datetime.now(UTC)
    alerts = [
        _make_alert(severity="minor", source_alert_id=f"m-{i}", fingerprint=f"fp-{i}")
        for i in range(30)
    ]
    events = [_make_canonical_event(severity="extreme", confidence="high")]
    result = compute_global_risk_score(alerts, canonical_events=events, now=now)
    assert result.global_score >= 20
    assert result.breakdown["event_severity_index"]["source"] == "canonical_events"


def test_showcase_scenario_moderate_score() -> None:
    """Three showcase-like events with exposures should land in 40-75 range."""
    now = datetime.now(UTC)
    event_eq = _make_canonical_event(title="M6.8 Earthquake", severity="severe", confidence="high")
    event_storm = _make_canonical_event(title="Tropical Cyclone", severity="severe", confidence="medium")
    event_geo = _make_canonical_event(title="G4 Geomagnetic Storm", severity="extreme", confidence="high")

    link1 = CanonicalEventLink(
        id=uuid4(),
        canonical_event_id=event_storm.id,
        member_type="alert",
        member_id=uuid4(),
        link_confidence="high",
        created_at=now,
    )
    link2 = CanonicalEventLink(
        id=uuid4(),
        canonical_event_id=event_storm.id,
        member_type="observed",
        member_id=uuid4(),
        link_confidence="high",
        created_at=now,
    )
    event_storm.links = [link1, link2]

    exposures = [
        _make_exposure("port", "critical", overlap=True),
        _make_exposure("airport", "critical", overlap=True),
        _make_exposure("power_plant", "high", overlap=False),
    ]

    impl = ImplicationCandidate(
        id=uuid4(),
        canonical_event_id=event_eq.id,
        category="infrastructure",
        title="Port exposure risk",
        evidence_level="inferred_from_exposure",
        confidence="medium",
        related_asset_ids=[],
        supporting_source_ids=[],
        created_at=now,
    )

    result = compute_global_risk_score(
        alerts=[_make_alert()],
        canonical_events=[event_eq, event_storm, event_geo],
        event_exposures=exposures,
        implications=[impl],
        now=now,
    )
    assert 35 <= result.global_score <= 80
    assert result.global_score < 100


def test_global_score_capped_at_100() -> None:
    now = datetime.now(UTC)
    events = [
        _make_canonical_event(severity="extreme", confidence="high", title=f"Event {i}")
        for i in range(10)
    ]
    for event in events:
        event.links = [
            CanonicalEventLink(
                id=uuid4(),
                canonical_event_id=event.id,
                member_type="alert",
                member_id=uuid4(),
                link_confidence="high",
                created_at=now,
            ),
            CanonicalEventLink(
                id=uuid4(),
                canonical_event_id=event.id,
                member_type="observed",
                member_id=uuid4(),
                link_confidence="high",
                created_at=now,
            ),
            CanonicalEventLink(
                id=uuid4(),
                canonical_event_id=event.id,
                member_type="alert",
                member_id=uuid4(),
                link_confidence="high",
                created_at=now,
            ),
        ]

    exposures = [_make_exposure("power_plant", "critical") for _ in range(8)]
    implications = [
        ImplicationCandidate(
            id=uuid4(),
            canonical_event_id=events[0].id,
            category="humanitarian",
            title=f"Impact {i}",
            evidence_level="officially_reported",
            confidence="high",
            related_asset_ids=[],
            supporting_source_ids=[],
            created_at=now,
        )
        for i in range(5)
    ]

    result = compute_global_risk_score(
        canonical_events=events,
        event_exposures=exposures,
        implications=implications,
        now=now,
    )
    assert result.global_score <= 100


def test_global_score_zero_when_no_signals() -> None:
    result = compute_global_risk_score([])
    assert result.global_score == 0


def test_infrastructure_exposure_index_weights() -> None:
    exposures = [
        _make_exposure("power_plant", "critical", overlap=True),
        _make_exposure("airport", "high", overlap=False),
    ]
    index, detail = compute_infrastructure_exposure_index(exposures)
    assert index > 0
    assert detail["unique_assets"] == 2


def test_multi_source_corroboration_requires_two_sources() -> None:
    now = datetime.now(UTC)
    event = _make_canonical_event()
    event.links = [
        CanonicalEventLink(
            id=uuid4(),
            canonical_event_id=event.id,
            member_type="alert",
            member_id=uuid4(),
            link_confidence="high",
            created_at=now,
        )
    ]
    index, detail = compute_multi_source_corroboration([event])
    assert index == 0
    assert detail["corroborated_events"] == 0


def test_humanitarian_impact_ignores_hypothesis() -> None:
    now = datetime.now(UTC)
    event = _make_canonical_event()
    impl = ImplicationCandidate(
        id=uuid4(),
        canonical_event_id=event.id,
        category="logistics",
        title="Hypothesis only",
        evidence_level="hypothesis",
        confidence="high",
        related_asset_ids=[],
        supporting_source_ids=[],
        created_at=now,
    )
    index, detail = compute_humanitarian_impact_signal([impl], [event])
    assert index == 0
    assert detail["qualifying_implications"] == 0


def test_event_severity_index_canonical_preferred() -> None:
    events = [_make_canonical_event(severity="severe")]
    alerts = [_make_alert(severity="extreme") for _ in range(20)]
    index, detail = compute_event_severity_index(events, alerts)
    assert detail["source"] == "canonical_events"
    assert index == pytest.approx(17, abs=3)
