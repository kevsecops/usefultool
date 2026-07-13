"""EONET adapter tests."""

import pytest

from app.schemas.common import Category
from app.sources.eonet import (
    EonetSourceAdapter,
    extract_eonet_events,
    geometry_from_snapshot,
    map_eonet_category,
    normalize_eonet_severity,
    select_latest_geometry,
)
from app.sources.fixture_loader import load_fixture


def test_extract_eonet_events_from_fixture() -> None:
    data = load_fixture("eonet", "events_open.json", refresh_dates=False)
    events = extract_eonet_events(data)
    assert len(events) == 3


def test_select_latest_geometry_picks_most_recent() -> None:
    snapshots = [
        {"date": "2026-07-10T12:00:00Z", "type": "Point", "coordinates": [-65.0, 22.0]},
        {"date": "2026-07-12T06:00:00Z", "type": "LineString", "coordinates": [[-60, 28], [-57, 30]]},
    ]
    latest = select_latest_geometry(snapshots)
    assert latest is not None
    assert latest["type"] == "LineString"
    geo = geometry_from_snapshot(latest)
    assert geo is not None
    assert geo["type"] == "LineString"


def test_select_latest_geometry_single_event_not_duplicated() -> None:
    """Multiple snapshots for one EONET id collapse to latest geometry only."""
    data = load_fixture("eonet", "events_open.json", refresh_dates=False)
    storm = next(e for e in extract_eonet_events(data) if e["id"] == "EONET_DEMO_STORM")
    latest = select_latest_geometry(storm["geometry"])
    assert latest["type"] == "LineString"
    assert len(storm["geometry"]) == 3


def test_map_eonet_categories() -> None:
    assert map_eonet_category([{"id": "wildfires"}]) == "wildfire"
    assert map_eonet_category([{"id": "severeStorms"}]) == "weather"
    assert map_eonet_category([{"id": "volcanoes"}]) == "volcano"


def test_normalize_eonet_severity_storm_kts() -> None:
    assert normalize_eonet_severity(Category.WEATHER, 65.0, "kts") == "moderate"
    assert normalize_eonet_severity(Category.WEATHER, 100.0, "kts") == "extreme"


def test_eonet_normalize_point_wildfire() -> None:
    adapter = EonetSourceAdapter()
    data = load_fixture("eonet", "events_open.json", refresh_dates=False)
    wildfire = next(e for e in extract_eonet_events(data) if e["id"] == "EONET_DEMO_WILDFIRE")
    from app.sources.base import RawAlertPayload

    raw = RawAlertPayload(source="eonet", data=wildfire, ingest_mode="fixture")
    parsed = adapter.parse_observed_event(raw)
    canonical = adapter.normalize_observed_event(parsed)

    assert canonical.source == "eonet"
    assert canonical.source_event_id == "EONET_DEMO_WILDFIRE"
    assert canonical.category == "wildfire"
    assert canonical.geometry["type"] == "Point"
    assert canonical.spatial_scope == "local"


def test_eonet_normalize_linestring_storm() -> None:
    adapter = EonetSourceAdapter()
    data = load_fixture("eonet", "events_open.json", refresh_dates=False)
    storm = next(e for e in extract_eonet_events(data) if e["id"] == "EONET_DEMO_STORM")
    from app.sources.base import RawAlertPayload

    raw = RawAlertPayload(source="eonet", data=storm, ingest_mode="fixture")
    canonical = adapter.normalize_observed_event(adapter.parse_observed_event(raw))

    assert canonical.geometry["type"] == "LineString"
    assert canonical.spatial_scope == "regional"
    assert canonical.severity == "moderate"


def test_eonet_normalize_volcano() -> None:
    adapter = EonetSourceAdapter()
    data = load_fixture("eonet", "events_open.json", refresh_dates=False)
    volcano = next(e for e in extract_eonet_events(data) if e["id"] == "EONET_DEMO_VOLCANO")
    from app.sources.base import RawAlertPayload

    raw = RawAlertPayload(source="eonet", data=volcano, ingest_mode="fixture")
    canonical = adapter.normalize_observed_event(adapter.parse_observed_event(raw))

    assert canonical.category == "volcano"
    assert canonical.latitude is not None


@pytest.mark.asyncio
async def test_eonet_fetch_fixtures_in_demo_mode(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()

    adapter = EonetSourceAdapter()
    payloads = await adapter.fetch_alerts()
    assert len(payloads) == 3
    assert payloads[0].ingest_mode == "fixture"


@pytest.mark.asyncio
async def test_eonet_live_fetch_mocked(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.core.http_client import HttpClient

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("EONET_USE_FIXTURES", "false")
    monkeypatch.setenv("SOURCES_LIVE", "eonet")
    get_settings.cache_clear()

    fixture_data = load_fixture("eonet", "events_open.json", refresh_dates=False)

    class MockTransport:
        async def handle_async_request(self, request):
            import httpx

            return httpx.Response(200, json=fixture_data)

    http = HttpClient(
        user_agent="test",
        allowed_hosts=frozenset({"eonet.gsfc.nasa.gov"}),
        transport=MockTransport(),
    )
    adapter = EonetSourceAdapter(http_client=http)
    payloads = await adapter.fetch_alerts()
    assert len(payloads) == 3


@pytest.mark.asyncio
async def test_eonet_ingest_deactivates_closed_events(db_session) -> None:
    """Events not in open feed are deactivated on ingest."""
    from app.models.observed_event import ObservedEvent
    from app.normalization.datetime_utils import utc_now
    from app.normalization.fingerprint import generate_observed_event_fingerprint
    from app.services.ingest_service import run_ingest

    now = utc_now()
    orphan = ObservedEvent(
        source="eonet",
        source_event_id="EONET_CLOSED_ORPHAN",
        title="Closed EONET event",
        category="wildfire",
        severity="minor",
        status="unknown",
        confidence="medium",
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"id": "EONET_CLOSED_ORPHAN"},
        fingerprint=generate_observed_event_fingerprint(
            source="eonet",
            source_event_id="EONET_CLOSED_ORPHAN",
            title="Closed EONET event",
            issued_at=now,
            severity="minor",
            category="wildfire",
        ),
        is_active=True,
    )
    db_session.add(orphan)
    db_session.commit()

    run = await run_ingest(db_session, sources=["eonet"])
    db_session.commit()
    db_session.refresh(orphan)

    assert run.status == "success"
    assert orphan.is_active is False
