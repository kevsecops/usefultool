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
async def test_briefing_stale_after_ingest_without_regeneration(db_session, monkeypatch) -> None:
    """Ingest after briefing generation marks briefing as stale."""
    from app.services.briefing_service import generate_briefing, get_latest_briefing, is_briefing_stale
    from app.services.ingest_service import run_ingest
    from app.services.stats_service import get_stats

    monkeypatch.setenv("AUTO_GENERATE_BRIEFING", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    await run_ingest(db_session)
    generate_briefing(db_session, briefing_type="rule_based")
    db_session.commit()

    briefing = get_latest_briefing(db_session)
    assert briefing is not None
    assert not is_briefing_stale(briefing, get_stats(db_session).last_ingest)

    await run_ingest(db_session, generate_briefing=False)
    db_session.commit()

    stats = get_stats(db_session)
    assert is_briefing_stale(briefing, stats.last_ingest)


@pytest.mark.asyncio
async def test_briefing_snapshot_consistent_with_stats_at_generation(client, db_session, monkeypatch) -> None:
    """Briefing overall_risk_score and active_count match live stats right after generation."""
    from app.services.briefing_service import generate_briefing
    from app.services.ingest_service import run_ingest
    from app.services.stats_service import get_stats

    monkeypatch.setenv("AUTO_GENERATE_BRIEFING", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    await run_ingest(db_session)
    generate_briefing(db_session, briefing_type="rule_based")
    db_session.commit()

    stats = get_stats(db_session)
    response = client.get("/api/v1/briefings/latest")
    assert response.status_code == 200
    data = response.json()

    assert data["overall_risk_score"] == stats.global_risk_score
    assert data["content"]["active_count"] == stats.active_count
    assert data["content"]["overall_risk_score"] == stats.global_risk_score
    assert str(data["content"]["active_count"]) in data["content"]["summary"]


@pytest.mark.asyncio
async def test_generate_briefing_requires_token(client) -> None:
    response = client.post("/api/v1/admin/generate-briefing", json={})
    assert response.status_code == 401
