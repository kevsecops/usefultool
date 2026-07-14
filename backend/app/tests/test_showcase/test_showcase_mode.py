"""Tests for SHOWCASE_MODE curated demo ingest."""

import pytest

from app.core.config import get_settings
from app.services.showcase_service import load_manifest, load_showcase_data, run_showcase_ingest


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_load_manifest_has_three_scenarios():
    manifest = load_manifest()
    assert len(manifest.scenarios) == 3
    assert "usgs" in manifest.ingest_sources
    assert "noaa_swpc" in manifest.ingest_sources


def test_load_showcase_usgs_fixture():
    data = load_showcase_data("earthquake_port/usgs.geojson")
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 1


@pytest.mark.asyncio
async def test_run_showcase_ingest(db_session, monkeypatch):
    monkeypatch.setenv("SHOWCASE_MODE", "true")
    get_settings.cache_clear()

    run = await run_showcase_ingest(db_session, generate_briefing=False)
    db_session.commit()

    assert run.status in ("success", "partial")
    assert run.alerts_fetched >= 3
    assert run.source == "showcase"
