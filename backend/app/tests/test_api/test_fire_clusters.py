"""Fire clusters API tests."""

import pytest


@pytest.mark.asyncio
async def test_fire_clusters_endpoint(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session, sources=["firms"])
    db_session.commit()

    response = client.get("/api/v1/fire-clusters")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    for item in data["items"]:
        assert item["source"] == "firms"
        assert item["event_type"] == "active_fire_cluster"
        assert item["category"] == "wildfire"
        assert item["source_metadata"]["point_count"] >= 3
        assert item["geometry"]["type"] == "Polygon"


@pytest.mark.asyncio
async def test_firms_ingest_persists_clusters_only(db_session) -> None:
    from sqlalchemy import func, select

    from app.models.observed_event import ObservedEvent
    from app.services.ingest_service import run_ingest

    run = await run_ingest(db_session, sources=["firms"])
    db_session.commit()

    assert run.status == "success"
    cluster_count = db_session.scalar(
        select(func.count())
        .select_from(ObservedEvent)
        .where(ObservedEvent.source == "firms")
    )
    assert cluster_count == 3

    raw_point_ids_in_db = db_session.scalars(
        select(ObservedEvent.source_event_id).where(ObservedEvent.source == "firms")
    ).all()
    assert all(cid.startswith("firms-cluster-") for cid in raw_point_ids_in_db)
