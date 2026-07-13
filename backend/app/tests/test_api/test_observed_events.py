"""Observed events API tests."""

import pytest


@pytest.mark.asyncio
async def test_observed_events_after_ingest(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    response = client.get("/api/v1/observed-events")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["items"][0]["source"] == "usgs"
    assert data["items"][0]["category"] == "earthquake"


@pytest.mark.asyncio
async def test_observed_event_detail(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    listing = client.get("/api/v1/observed-events").json()
    event_id = listing["items"][0]["id"]

    response = client.get(f"/api/v1/observed-events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == event_id
    assert data["source_event_id"]


@pytest.mark.asyncio
async def test_observed_events_bounding_box(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    # Texas fixture event around lon -104, lat 31.5
    response = client.get(
        "/api/v1/observed-events",
        params={"bounding_box": "-105,31,-103,32"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_observed_events_filter_by_severity(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    response = client.get("/api/v1/observed-events", params={"severity": "minor"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["severity"] == "minor"


@pytest.mark.asyncio
async def test_health_includes_observed_event_counts(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["usgs"])
    db_session.commit()

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "observed_event_counts" in data
    assert data["observed_event_counts"].get("usgs", 0) == 3
