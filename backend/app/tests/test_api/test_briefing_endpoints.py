"""Briefing API endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_generate_briefing_admin(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    response = client.post(
        "/api/v1/admin/generate-briefing",
        json={"type": "rule_based"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "rule_based"
    assert data["overall_risk_score"] > 0


@pytest.mark.asyncio
async def test_latest_briefing(client, db_session) -> None:
    from app.services.briefing_service import generate_briefing
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    generate_briefing(db_session, briefing_type="rule_based")
    db_session.commit()

    response = client.get("/api/v1/briefings/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "rule_based"
    assert data["overall_risk_score"] > 0
    assert "summary" in data["content"]
    assert len(data["content"]["source_alert_ids"]) > 0


@pytest.mark.asyncio
async def test_latest_briefing_not_found(client) -> None:
    response = client.get("/api/v1/briefings/latest")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_briefings(client, db_session) -> None:
    from app.services.briefing_service import generate_briefing
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    generate_briefing(db_session, briefing_type="rule_based")
    db_session.commit()

    response = client.get("/api/v1/briefings")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_stats_global_risk_score(client, db_session) -> None:
    from app.services.ingest_service import run_ingest

    await run_ingest(db_session)
    db_session.commit()

    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["active_count"] > 0
    assert data["global_risk_score"] > 0
    assert "alert_score_sum" in data["score_breakdown"]
    assert "trend_anomalies" in data


@pytest.mark.asyncio
async def test_generate_briefing_requires_token(client) -> None:
    response = client.post("/api/v1/admin/generate-briefing", json={})
    assert response.status_code == 401
