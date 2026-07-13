"""NINA live adapter tests with mocked HTTP."""

from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.sources.fixture_loader import load_fixture, load_geojson
from app.sources.nina import NinaSourceAdapter, extract_geometry_from_geojson

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "nina"


def _make_transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture
def mowas_fixture() -> list:
    return load_fixture("nina", "mapdata_mowas.json")


@pytest.fixture
def detail_fixture() -> dict:
    return load_fixture("nina", "warning_detail_flood.json")


@pytest.fixture
def geo_fixture() -> dict:
    return load_geojson("nina", "warning_geo_flood.geojson")


def test_extract_geometry_from_geojson(geo_fixture: dict) -> None:
    geometry = extract_geometry_from_geojson(geo_fixture)
    assert geometry is not None
    assert geometry["type"] == "Polygon"


@pytest.mark.asyncio
async def test_nina_live_fetch_parses_alerts(
    mowas_fixture: list,
    detail_fixture: dict,
    geo_fixture: dict,
    monkeypatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    monkeypatch.setenv("SOURCES_LIVE", "nina")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/mowas/mapData.json"):
            return httpx.Response(200, json=mowas_fixture)
        if path.endswith("/dwd/mapData.json"):
            return httpx.Response(200, json=[])
        if path.endswith(".json") and "/warnings/" in path:
            return httpx.Response(200, json=detail_fixture)
        if path.endswith(".geojson"):
            return httpx.Response(200, json=geo_fixture)
        return httpx.Response(404, json={"error": "not found"})

    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"warnung.bund.de"}),
        transport=_make_transport(handler),
    )
    adapter = NinaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 3

    canonical = adapter.normalize_alert(adapter.parse_alert(raw_alerts[0]))
    assert canonical.source == "nina"
    assert canonical.country_code == "DE"
    assert canonical.category == "flood"
    assert canonical.severity == "moderate"
    assert canonical.urgency == "immediate"
    assert canonical.certainty == "likely"
    assert canonical.latitude is not None
    assert canonical.longitude is not None
    assert "<br/>" not in (canonical.description or "")


@pytest.mark.asyncio
async def test_nina_demo_mode_uses_fixtures(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES_DIR.parent))
    get_settings.cache_clear()

    adapter = NinaSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) >= 3


@pytest.mark.asyncio
async def test_nina_fallback_to_fixtures_on_live_failure(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES_DIR.parent))
    get_settings.cache_clear()

    def fail_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        max_retries=0,
        allowed_hosts=frozenset({"warnung.bund.de"}),
        transport=_make_transport(fail_handler),
    )
    adapter = NinaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) >= 3


@pytest.mark.asyncio
async def test_nina_health_check_live(mowas_fixture: list, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/mowas/mapData.json"):
            return httpx.Response(200, json=mowas_fixture)
        return httpx.Response(404)

    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"warnung.bund.de"}),
        transport=_make_transport(handler),
    )
    adapter = NinaSourceAdapter(http_client=client)
    health = await adapter.health_check()
    assert health.is_healthy is True


@pytest.mark.asyncio
async def test_nina_severity_mapping(monkeypatch, mowas_fixture: list) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/mowas/mapData.json"):
            return httpx.Response(200, json=mowas_fixture)
        if request.url.path.endswith("/dwd/mapData.json"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"warnung.bund.de"}),
        transport=_make_transport(handler),
    )
    adapter = NinaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    severities = {
        adapter.normalize_alert(adapter.parse_alert(raw)).severity for raw in raw_alerts
    }
    assert "moderate" in severities
    assert "minor" in severities
    assert "severe" in severities


@pytest.mark.asyncio
async def test_nina_empty_live_returns_no_alerts_without_fallback(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    monkeypatch.setenv("NINA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/mowas/mapData.json"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/dwd/mapData.json"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"warnung.bund.de"}),
        transport=_make_transport(handler),
    )
    adapter = NinaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert raw_alerts == []
    assert adapter._last_ingest_mode == "live"


@pytest.mark.asyncio
async def test_nina_fixture_alerts_have_no_source_url(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES_DIR.parent))
    get_settings.cache_clear()

    adapter = NinaSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    flood = next(r for r in raw_alerts if "DEMO-SL-FLOOD" in r.data.get("id", ""))
    canonical = adapter.normalize_alert(adapter.parse_alert(flood))
    assert canonical.source_url is None
    assert canonical.raw_payload.get("_ingest_mode") == "fixture"


@pytest.mark.asyncio
async def test_nina_health_check_reports_ingest_mode(monkeypatch, mowas_fixture: list) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NINA_USE_FIXTURES", "false")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/mowas/mapData.json"):
            return httpx.Response(200, json=mowas_fixture)
        return httpx.Response(404)

    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"warnung.bund.de"}),
        transport=_make_transport(handler),
    )
    adapter = NinaSourceAdapter(http_client=client)
    await adapter.fetch_alerts()
    health = await adapter.health_check()
    assert health.ingest_mode == "live"
    assert health.alerts_fetched == 3


@pytest.mark.asyncio
async def test_http_client_rejects_non_allowlisted_nina_host() -> None:
    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"warnung.bund.de"}),
    )
    with pytest.raises(HttpClientError, match="not allowlisted"):
        await client.get_json_list("https://evil.example.com/mowas/mapData.json")
