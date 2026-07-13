"""Space weather API tests."""

import pytest


@pytest.mark.asyncio
async def test_space_weather_endpoint(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["noaa_swpc"])
    db_session.commit()

    response = client.get("/api/v1/space-weather")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 4
    for item in data["items"]:
        assert item["source"] == "noaa_swpc"
        assert item["category"] == "environmental"


@pytest.mark.asyncio
async def test_observed_events_filter_by_eonet(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["eonet"])
    db_session.commit()

    response = client.get("/api/v1/observed-events", params={"source": "eonet"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    categories = {item["category"] for item in data["items"]}
    assert "wildfire" in categories
    assert "volcano" in categories
