"""USGS adapter tests."""

from datetime import UTC, datetime

import pytest

from app.sources.fixture_loader import load_fixture, refresh_usgs_fixture
from app.sources.usgs import (
    UsgsSourceAdapter,
    extract_usgs_features,
    normalize_usgs_severity,
    parse_usgs_timestamp,
)


def test_parse_usgs_timestamp() -> None:
    ts = parse_usgs_timestamp(1783932807913)
    assert ts is not None
    assert ts.tzinfo == UTC


def test_normalize_usgs_severity_uses_pager_not_magnitude() -> None:
    # Low magnitude but red PAGER alert -> extreme
    assert (
        normalize_usgs_severity({"mag": 2.0, "alert": "red", "sig": 10, "tsunami": 0})
        == "extreme"
    )
    # High magnitude but no alert -> significance-based
    assert (
        normalize_usgs_severity({"mag": 7.5, "alert": None, "sig": 650, "tsunami": 0})
        == "extreme"
    )


def test_normalize_usgs_severity_tsunami_bump() -> None:
    assert (
        normalize_usgs_severity({"mag": 5.0, "alert": "green", "sig": 50, "tsunami": 1})
        == "moderate"
    )


def test_extract_usgs_features_from_fixture() -> None:
    data = load_fixture("usgs", "all_day_demo.geojson")
    features = extract_usgs_features(data)
    assert len(features) == 3
    assert all(f.get("type") == "Feature" for f in features)


def test_usgs_normalize_observed_event_from_fixture() -> None:
    adapter = UsgsSourceAdapter()
    data = refresh_usgs_fixture(load_fixture("usgs", "all_day_demo.geojson"))
    feature = extract_usgs_features(data)[0]
    from app.sources.base import RawAlertPayload

    raw = RawAlertPayload(source="usgs", data=feature, ingest_mode="fixture")
    parsed = adapter.parse_observed_event(raw)
    canonical = adapter.normalize_observed_event(parsed)

    assert canonical.source == "usgs"
    assert canonical.source_event_id == "us7000szzy"
    assert canonical.category == "earthquake"
    assert canonical.severity == "minor"
    assert canonical.source_metadata is not None
    assert canonical.source_metadata.get("magnitude") == 6.4
    assert canonical.source_metadata.get("alert") == "green"


@pytest.mark.asyncio
async def test_usgs_fetch_fixtures_in_demo_mode(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()

    adapter = UsgsSourceAdapter()
    payloads = await adapter.fetch_alerts()
    assert len(payloads) == 3
    assert payloads[0].ingest_mode == "fixture"


@pytest.mark.asyncio
async def test_usgs_live_fetch_mocked(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.core.http_client import HttpClient

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("USGS_USE_FIXTURES", "false")
    monkeypatch.setenv("SOURCES_LIVE", "usgs")
    get_settings.cache_clear()

    fixture_data = refresh_usgs_fixture(load_fixture("usgs", "all_day_demo.geojson"))

    class MockTransport:
        async def handle_async_request(self, request):
            import httpx

            return httpx.Response(200, json=fixture_data)

    http = HttpClient(
        user_agent="test",
        allowed_hosts=frozenset({"earthquake.usgs.gov"}),
        transport=MockTransport(),
    )
    adapter = UsgsSourceAdapter(http_client=http)
    payloads = await adapter.fetch_alerts()
    assert len(payloads) == 3
