"""GDACS live adapter tests with mocked HTTP."""

from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.sources.fixture_loader import load_fixture
from app.sources.gdacs import (
    GdacsSourceAdapter,
    extract_gdacs_features,
    is_current_event,
)

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "gdacs"


@pytest.fixture
def events_fixture() -> dict:
    return load_fixture("gdacs", "events4app.json")


def test_extract_gdacs_features(events_fixture: dict) -> None:
    features = extract_gdacs_features(events_fixture)
    assert len(features) == 3


def test_is_current_event() -> None:
    assert is_current_event({"iscurrent": "true"}) is True
    assert is_current_event({"iscurrent": "false"}) is False
    assert is_current_event({}) is True


@pytest.mark.asyncio
async def test_gdacs_live_fetch_parses_features(events_fixture: dict, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GDACS_USE_FIXTURES", "false")
    monkeypatch.setenv("GDACS_FALLBACK_TO_FIXTURES", "false")
    monkeypatch.setenv("SOURCES_LIVE", "gdacs")
    get_settings.cache_clear()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=events_fixture)

    client = HttpClient(
        user_agent="TestAgent/1.0 (test@example.com)",
        allowed_hosts=frozenset({"www.gdacs.org"}),
        transport=httpx.MockTransport(handler),
    )
    adapter = GdacsSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 3

    canonical = adapter.normalize_alert(adapter.parse_alert(raw_alerts[0]))
    assert canonical.source == "gdacs"
    assert canonical.category == "earthquake"
    assert canonical.severity == "severe"
    assert canonical.country_code == "PG"
    assert canonical.latitude is not None
    assert canonical.longitude is not None


@pytest.mark.asyncio
async def test_gdacs_filters_non_current_events(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GDACS_USE_FIXTURES", "false")
    monkeypatch.setenv("GDACS_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    stale_fixture = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {
                    "eventtype": "EQ",
                    "eventid": 1,
                    "episodeid": 1,
                    "name": "Stale event",
                    "alertlevel": "Green",
                    "iscurrent": "false",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 1]},
                "properties": {
                    "eventtype": "EQ",
                    "eventid": 2,
                    "episodeid": 2,
                    "name": "Current event",
                    "alertlevel": "Orange",
                    "iscurrent": "true",
                },
            },
        ],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=stale_fixture)

    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"www.gdacs.org"}),
        transport=httpx.MockTransport(handler),
    )
    adapter = GdacsSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 1
    assert raw_alerts[0].data["properties"]["name"] == "Current event"


@pytest.mark.asyncio
async def test_gdacs_demo_mode_uses_fixtures(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES_DIR.parent))
    get_settings.cache_clear()

    adapter = GdacsSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 3


@pytest.mark.asyncio
async def test_gdacs_fallback_to_fixtures_on_live_failure(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GDACS_USE_FIXTURES", "false")
    monkeypatch.setenv("GDACS_FALLBACK_TO_FIXTURES", "true")
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES_DIR.parent))
    get_settings.cache_clear()

    def fail_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    client = HttpClient(
        user_agent="Test/1.0",
        max_retries=0,
        allowed_hosts=frozenset({"www.gdacs.org"}),
        transport=httpx.MockTransport(fail_handler),
    )
    adapter = GdacsSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 3


@pytest.mark.asyncio
async def test_gdacs_health_check_live(events_fixture: dict, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GDACS_USE_FIXTURES", "false")
    get_settings.cache_clear()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=events_fixture)

    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"www.gdacs.org"}),
        transport=httpx.MockTransport(handler),
    )
    adapter = GdacsSourceAdapter(http_client=client)
    health = await adapter.health_check()
    assert health.is_healthy is True


@pytest.mark.asyncio
async def test_gdacs_event_type_category_mapping(events_fixture: dict, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GDACS_USE_FIXTURES", "false")
    monkeypatch.setenv("GDACS_FALLBACK_TO_FIXTURES", "false")
    get_settings.cache_clear()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=events_fixture)

    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"www.gdacs.org"}),
        transport=httpx.MockTransport(handler),
    )
    adapter = GdacsSourceAdapter(http_client=client)
    raw_alerts = await adapter.fetch_alerts()
    categories = {
        adapter.normalize_alert(adapter.parse_alert(raw)).category for raw in raw_alerts
    }
    assert "earthquake" in categories
    assert "weather" in categories
    assert "volcano" in categories


@pytest.mark.asyncio
async def test_http_client_rejects_non_allowlisted_gdacs_host() -> None:
    client = HttpClient(
        user_agent="Test/1.0",
        allowed_hosts=frozenset({"www.gdacs.org"}),
    )
    with pytest.raises(HttpClientError, match="not allowlisted"):
        await client.get_json("https://evil.example.com/gdacsapi/api/events/geteventlist/events4app")
