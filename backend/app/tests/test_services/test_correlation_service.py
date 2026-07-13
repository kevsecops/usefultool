"""Tests for cross-source event correlation."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.observed_event import ObservedEvent
from app.normalization.fingerprint import generate_fingerprint, generate_observed_event_fingerprint
from app.services.correlation_service import run_correlation, score_pair
from app.services.correlation_service import _member_from_alert, _member_from_observed_event


def _now() -> datetime:
    return datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _make_alert(**kwargs) -> Alert:
    now = _now()
    defaults = {
        "id": uuid4(),
        "source": "gdacs",
        "source_alert_id": "eq-123456-1",
        "title": "M5.2 Earthquake in Coastal Region",
        "description": "Strong earthquake reported",
        "category": "earthquake",
        "event_type": "earthquake",
        "severity": "moderate",
        "status": "actual",
        "latitude": 35.1,
        "longitude": 25.2,
        "geometry_json": {"type": "Point", "coordinates": [25.2, 35.1]},
        "issued_at": now,
        "ingested_at": now,
        "last_seen_at": now,
        "raw_payload": {"properties": {"eventid": "123456"}},
        "fingerprint": "gdacs-eq-fp",
        "is_active": True,
    }
    defaults.update(kwargs)
    return Alert(**defaults)


def _make_observed_event(**kwargs) -> ObservedEvent:
    now = _now()
    defaults = {
        "id": uuid4(),
        "source": "usgs",
        "source_event_id": "us7000abc",
        "title": "M5.2 Earthquake Coastal Region",
        "description": "USGS detected earthquake",
        "category": "earthquake",
        "event_type": "earthquake",
        "severity": "moderate",
        "status": "automatic",
        "confidence": "high",
        "latitude": 35.12,
        "longitude": 25.18,
        "geometry_json": {"type": "Point", "coordinates": [25.18, 35.12]},
        "spatial_scope": "local",
        "issued_at": now,
        "ingested_at": now,
        "last_seen_at": now,
        "raw_payload": {"id": "us7000abc"},
        "fingerprint": "usgs-eq-fp",
        "is_active": True,
    }
    defaults.update(kwargs)
    return ObservedEvent(**defaults)


def test_score_pair_high_confidence_earthquake() -> None:
    alert = _member_from_alert(_make_alert())
    observed = _member_from_observed_event(_make_observed_event())
    match = score_pair(alert, observed)
    assert match.level == "high"
    assert "geo_proximity" in match.reasons


def test_score_pair_rejects_same_source() -> None:
    left = _member_from_alert(_make_alert(source="gdacs", source_alert_id="a1"))
    right = _member_from_alert(_make_alert(source="gdacs", source_alert_id="a2"))
    match = score_pair(left, right)
    assert match.level == "none"


def test_correlation_creates_canonical_event(db_session) -> None:
    alert = _make_alert()
    observed = _make_observed_event()
    db_session.add_all([alert, observed])
    db_session.flush()

    alert_count_before = db_session.scalar(select(func.count()).select_from(Alert))
    observed_count_before = db_session.scalar(select(func.count()).select_from(ObservedEvent))

    result = run_correlation(db_session)
    db_session.flush()

    assert result.canonical_events_created == 1
    assert result.links_created == 2
    assert db_session.scalar(select(func.count()).select_from(CanonicalEvent)) == 1

    links = db_session.scalars(select(CanonicalEventLink)).all()
    assert len(links) == 2
    assert all(link.link_confidence == "high" for link in links)

    assert db_session.scalar(select(func.count()).select_from(Alert)) == alert_count_before
    assert (
        db_session.scalar(select(func.count()).select_from(ObservedEvent)) == observed_count_before
    )


def test_medium_confidence_possible_match(db_session) -> None:
    now = _now()
    alert = _make_alert(
        source="noaa",
        source_alert_id="flood-warning-1",
        title="Flash Flood Warning",
        category="flood",
        event_type="flood",
        latitude=30.0,
        longitude=-90.0,
        geometry_json={"type": "Point", "coordinates": [-90.0, 30.0]},
        fingerprint=generate_fingerprint(
            source="noaa",
            source_alert_id="flood-warning-1",
            title="Flash Flood Warning",
            issued_at=now,
            severity="moderate",
            category="flood",
        ),
    )
    observed = _make_observed_event(
        source="eonet",
        source_event_id="eonet-storm-1",
        title="Severe Storm System",
        category="weather",
        event_type="severe storm",
        latitude=30.05,
        longitude=-90.05,
        geometry_json={"type": "Point", "coordinates": [-90.05, 30.05]},
        fingerprint=generate_observed_event_fingerprint(
            source="eonet",
            source_event_id="eonet-storm-1",
            title="Severe Storm System",
            issued_at=now,
            severity="moderate",
            category="weather",
        ),
    )
    db_session.add_all([alert, observed])
    db_session.flush()

    match = score_pair(_member_from_alert(alert), _member_from_observed_event(observed))
    assert match.level == "medium"

    result = run_correlation(db_session)
    db_session.flush()

    assert result.possible_matches == 1
    links = db_session.scalars(select(CanonicalEventLink)).all()
    low_links = [link for link in links if link.link_confidence == "low"]
    assert len(low_links) == 1
    assert "possible_match" in (low_links[0].link_reason or "")


def test_source_records_preserved_after_correlation(db_session) -> None:
    alert = _make_alert()
    observed = _make_observed_event()
    db_session.add_all([alert, observed])
    db_session.commit()

    alert_id = alert.id
    observed_id = observed.id
    alert_title = alert.title
    observed_title = observed.title

    run_correlation(db_session)
    db_session.commit()

    persisted_alert = db_session.get(Alert, alert_id)
    persisted_observed = db_session.get(ObservedEvent, observed_id)
    assert persisted_alert is not None
    assert persisted_observed is not None
    assert persisted_alert.title == alert_title
    assert persisted_observed.title == observed_title
