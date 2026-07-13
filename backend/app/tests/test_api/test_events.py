"""Canonical events API tests."""

from datetime import UTC, datetime
from uuid import uuid4

from app.models.alert import Alert
from app.models.observed_event import ObservedEvent
from app.services.correlation_service import run_correlation


def _now() -> datetime:
    return datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _seed_correlated_pair(db_session) -> None:
    now = _now()
    alert = Alert(
        id=uuid4(),
        source="gdacs",
        source_alert_id="eq-999-1",
        title="M6.0 Earthquake Pacific",
        category="earthquake",
        event_type="earthquake",
        severity="severe",
        status="actual",
        latitude=10.0,
        longitude=140.0,
        geometry_json={"type": "Point", "coordinates": [140.0, 10.0]},
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"properties": {"eventid": "999"}},
        fingerprint="api-gdacs-fp",
        is_active=True,
    )
    observed = ObservedEvent(
        id=uuid4(),
        source="usgs",
        source_event_id="us7000xyz",
        title="M6.0 Earthquake Pacific",
        category="earthquake",
        event_type="earthquake",
        severity="severe",
        status="automatic",
        confidence="high",
        latitude=10.02,
        longitude=140.01,
        geometry_json={"type": "Point", "coordinates": [140.01, 10.02]},
        spatial_scope="local",
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"id": "us7000xyz"},
        fingerprint="api-usgs-fp",
        is_active=True,
    )
    db_session.add_all([alert, observed])
    db_session.flush()
    run_correlation(db_session)
    db_session.flush()


def test_list_canonical_events(client, db_session) -> None:
    _seed_correlated_pair(db_session)
    db_session.commit()

    response = client.get("/api/v1/events")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["member_count"] == 2


def test_canonical_event_detail(client, db_session) -> None:
    _seed_correlated_pair(db_session)
    db_session.commit()

    listing = client.get("/api/v1/events").json()
    event_id = listing["items"][0]["id"]

    response = client.get(f"/api/v1/events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == event_id
    assert len(data["members"]) == 2


def test_canonical_event_sources(client, db_session) -> None:
    _seed_correlated_pair(db_session)
    db_session.commit()

    event_id = client.get("/api/v1/events").json()["items"][0]["id"]
    response = client.get(f"/api/v1/events/{event_id}/sources")
    assert response.status_code == 200
    data = response.json()
    assert len(data["alerts"]) == 1
    assert len(data["observed_events"]) == 1
    assert data["alerts"][0]["source"] == "gdacs"
    assert data["observed_events"][0]["source"] == "usgs"


def test_admin_correlate_events(client, db_session) -> None:
    _now_val = _now()
    alert = Alert(
        source="gdacs",
        source_alert_id="eq-admin-1",
        title="M4.5 Earthquake",
        category="earthquake",
        event_type="earthquake",
        severity="moderate",
        status="actual",
        latitude=1.0,
        longitude=2.0,
        geometry_json={"type": "Point", "coordinates": [2.0, 1.0]},
        issued_at=_now_val,
        ingested_at=_now_val,
        last_seen_at=_now_val,
        raw_payload={},
        fingerprint="admin-gdacs-fp",
        is_active=True,
    )
    observed = ObservedEvent(
        source="usgs",
        source_event_id="us-admin-1",
        title="M4.5 Earthquake",
        category="earthquake",
        event_type="earthquake",
        severity="moderate",
        status="automatic",
        confidence="medium",
        latitude=1.01,
        longitude=2.01,
        geometry_json={"type": "Point", "coordinates": [2.01, 1.01]},
        spatial_scope="local",
        issued_at=_now_val,
        ingested_at=_now_val,
        last_seen_at=_now_val,
        raw_payload={},
        fingerprint="admin-usgs-fp",
        is_active=True,
    )
    db_session.add_all([alert, observed])
    db_session.commit()

    response = client.post(
        "/api/v1/admin/correlate-events",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_events_created"] == 1
    assert data["links_created"] == 2


def test_health_includes_canonical_event_count(client, db_session) -> None:
    _seed_correlated_pair(db_session)
    db_session.commit()

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_event_count"] == 1
