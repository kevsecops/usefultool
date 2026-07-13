"""NOAA live adapter tests with mocked HTTP."""

import json
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.sources.noaa import NoaaSourceAdapter, extract_noaa_features, resolve_source_url
from app.sources.fixture_loader import load_fixture

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "noaa"


def _make_transport(responses: list[tuple[int, dict | str, dict | None]]):
    """Build MockTransport from (status, body, headers) tuples."""

    call_idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_idx["i"]
        call_idx["i"] += 1
        status, body, headers = responses[min(idx, len(responses) - 1)]
        if isinstance(body, dict):
            return httpx.Response(status, json=body, headers=headers or {})
        return httpx.Response(status, text=body, headers=headers or {})

    return httpx.MockTransport(handler)


@pytest.fixture
def tx_fixture() -> dict:
    get_settings.cache_clear()
    return load_fixture("noaa", "alerts_active_tx.json")


@pytest.fixture
def graph_fixture() -> dict:
    features = load_fixture("noaa", "alerts_active_tx.json")["features"]
    return {
        "@context": {"@vocab": "https://api.weather.gov/ontology#"},
        "type": "FeatureCollection",
        "@graph": features,
    }


def test_extract_features_from_features_key(tx_fixture: dict) -> None:
    features = extract_noaa_features(tx_fixture)
    assert len(features) == 2
    assert "properties" in features[0]


def test_extract_features_from_graph_key(graph_fixture: dict) -> None:
    features = extract_noaa_features(graph_fixture)
    assert len(features) == 2


def test_resolve_source_url_from_feature_id() -> None:
    url = resolve_source_url(
        {"id": "https://api.weather.gov/alerts/urn:oid:abc"},
        {},
    )
    assert url == "https://api.weather.gov/alerts/urn:oid:abc"


def test_resolve_source_url_from_urn() -> None:
    url = resolve_source_url({}, {"id": "urn:oid:abc"})
    assert url == "https://api.weather.gov/alerts/urn:oid:abc"


@pytest.mark.asyncio
async def test_noaa_live_fetch_parses_features(tx_fixture: dict, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NOAA_USE_FIXTURES", "false")
    monkeypatch.setenv("NOAA_FALLBACK_TO_FIXTURES", "false")
    monkeypatch.setenv("SOURCES_LIVE", "noaa")
    get_settings.cache_clear()

    transport = _make_transport([(200, tx_fixture, None)])
    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"api.weather.gov"}),
        transport=transport,
    )
    adapter = NoaaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 2

    canonical = adapter.normalize_alert(adapter.parse_alert(raw_alerts[0]))
    assert canonical.source == "noaa"
    assert canonical.country_code == "US"
    assert canonical.category == "flood"
    assert canonical.severity == "minor"
    assert canonical.urgency == "expected"
    assert canonical.certainty == "likely"
    assert canonical.source_url is not None
    assert canonical.latitude is not None
    assert canonical.longitude is not None


@pytest.mark.asyncio
async def test_noaa_live_fetch_handles_graph(graph_fixture: dict, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NOAA_USE_FIXTURES", "false")
    monkeypatch.setenv("NOAA_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    transport = _make_transport([(200, graph_fixture, None)])
    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"api.weather.gov"}),
        transport=transport,
    )
    adapter = NoaaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 2


@pytest.mark.asyncio
async def test_noaa_demo_mode_uses_fixtures(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(Path(__file__).resolve().parents[4] / "fixtures"))
    get_settings.cache_clear()

    adapter = NoaaSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) >= 2


@pytest.mark.asyncio
async def test_noaa_fallback_to_fixtures_on_live_failure(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NOAA_USE_FIXTURES", "false")
    monkeypatch.setenv("NOAA_FALLBACK_TO_FIXTURES", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(Path(__file__).resolve().parents[4] / "fixtures"))
    get_settings.cache_clear()

    def fail_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    transport = httpx.MockTransport(fail_handler)
    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        max_retries=0,
        allowed_hosts=frozenset({"api.weather.gov"}),
        transport=transport,
    )
    adapter = NoaaSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) >= 2


@pytest.mark.asyncio
async def test_noaa_health_check_live(monkeypatch, tx_fixture: dict) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NOAA_USE_FIXTURES", "false")
    get_settings.cache_clear()

    transport = _make_transport([(200, tx_fixture, None)])
    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"api.weather.gov"}),
        transport=transport,
    )
    adapter = NoaaSourceAdapter(http_client=client)
    health = await adapter.health_check()
    assert health.is_healthy is True


@pytest.mark.asyncio
async def test_http_client_rejects_non_allowlisted_host() -> None:
    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"api.weather.gov"}),
    )
    with pytest.raises(HttpClientError, match="not allowlisted"):
        await client.get_json("https://evil.example.com/alerts")


@pytest.mark.asyncio
async def test_http_client_retries_on_timeout() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json={"features": []})

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        user_agent="Test/1.0",
        max_retries=2,
        allowed_hosts=frozenset({"api.weather.gov"}),
        transport=transport,
    )
    data = await client.get_json("https://api.weather.gov/alerts/active")
    assert data == {"features": []}
    assert attempts["count"] == 2
