"""API endpoint tests."""

import pytest


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["demo_mode"] is True
    assert "scheduler" in data
    assert "alert_counts" in data
    assert "active_alert_count" in data


@pytest.mark.asyncio
async def test_alerts_after_ingest(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    response = client.get("/api/v1/alerts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert len(data["items"]) > 0
    assert "source" in data["items"][0]


@pytest.mark.asyncio
async def test_stats_after_ingest(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["active_count"] > 0


@pytest.mark.asyncio
async def test_admin_ingest_requires_token(client) -> None:
    response = client.post("/api/v1/admin/ingest", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_ingest_with_token(client, db_session) -> None:
    response = client.post(
        "/api/v1/admin/ingest",
        json={},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("success", "partial")
    assert data["alerts_fetched"] > 0


@pytest.mark.asyncio
async def test_alerts_bounding_box_filter(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    # Texas fixture polygons are around lon -97, lat 32-33
    response = client.get("/api/v1/alerts", params={"bounding_box": "-98,32,-96,34", "country": "US"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["country_code"] == "US"


@pytest.mark.asyncio
async def test_alerts_bounding_box_invalid(client) -> None:
    response = client.get("/api/v1/alerts", params={"bounding_box": "invalid"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_alerts_bounding_box_empty_region(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    response = client.get("/api/v1/alerts", params={"bounding_box": "0,0,1,1"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_sources(client) -> None:
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    data = response.json()
    assert len(data["sources"]) == 7
    source_ids = {s["id"] for s in data["sources"]}
    assert source_ids == {"nina", "gdacs", "noaa", "usgs", "eonet", "noaa_swpc", "firms"}
