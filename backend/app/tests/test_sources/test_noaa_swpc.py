"""NOAA SWPC adapter tests."""

import pytest

from app.sources.fixture_loader import load_fixture
from app.sources.noaa_swpc import (
    NoaaSwpcSourceAdapter,
    extract_alert_events,
    extract_scale_events,
    parse_noaa_scale_from_message,
    scale_to_severity,
)
from app.schemas.common import SpatialScope


def test_parse_noaa_scale_from_message() -> None:
    msg = "NOAA Scale: G4 - Severe\r\nPotential Impacts..."
    scale_type, level, text = parse_noaa_scale_from_message(msg)
    assert scale_type == "G"
    assert level == 4
    assert text == "severe"


def test_scale_to_severity_g4() -> None:
    assert scale_to_severity("G", 4) == "severe"
    assert scale_to_severity("G", 5) == "extreme"
    assert scale_to_severity("R", 2) == "moderate"


def test_extract_scale_events_from_fixture() -> None:
    data = load_fixture("noaa_swpc", "conditions.json", refresh_dates=False)
    events = extract_scale_events(data["scales"])
    assert len(events) >= 3
    g4 = next(e for e in events if e["source_event_id"] == "swpc-scale-G--1")
    assert g4["scale_level"] == 4


def test_extract_alert_events_from_fixture() -> None:
    data = load_fixture("noaa_swpc", "conditions.json", refresh_dates=False)
    events = extract_alert_events(data["alerts"])
    assert len(events) == 2
    g4_alert = next(e for e in events if e["product_id"] == "K09A")
    assert g4_alert["scale_type"] == "G"
    assert g4_alert["scale_level"] == 4


def test_swpc_normalize_geomagnetic_alert_global_scope() -> None:
    adapter = NoaaSwpcSourceAdapter()
    data = load_fixture("noaa_swpc", "conditions.json", refresh_dates=False)
    alert = extract_alert_events(data["alerts"])[0]
    from app.sources.base import RawAlertPayload

    raw = RawAlertPayload(source="noaa_swpc", data=alert, ingest_mode="fixture")
    canonical = adapter.normalize_observed_event(adapter.parse_observed_event(raw))

    assert canonical.source == "noaa_swpc"
    assert canonical.geometry is None
    assert canonical.spatial_scope == SpatialScope.GLOBAL
    assert canonical.affected_latitude_min == 50.0
    assert canonical.affected_latitude_max == 90.0
    assert canonical.source_metadata is not None
    assert "power_grid" in canonical.source_metadata.get("potential_systems", [])
    assert canonical.source_metadata.get("scale_documentation") is not None


def test_swpc_normalize_scale_event_orbital() -> None:
    adapter = NoaaSwpcSourceAdapter()
    data = load_fixture("noaa_swpc", "conditions.json", refresh_dates=False)
    scales = extract_scale_events(data["scales"])
    g_scale = next(e for e in scales if e["scale_type"] == "G")
    from app.sources.base import RawAlertPayload

    raw = RawAlertPayload(source="noaa_swpc", data=g_scale, ingest_mode="fixture")
    canonical = adapter.normalize_observed_event(adapter.parse_observed_event(raw))

    assert canonical.spatial_scope == SpatialScope.GLOBAL
    assert canonical.severity == "severe"
    assert "scale_documentation" in (canonical.source_metadata or {})


@pytest.mark.asyncio
async def test_swpc_fetch_fixtures_in_demo_mode(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()

    adapter = NoaaSwpcSourceAdapter()
    payloads = await adapter.fetch_alerts()
    assert len(payloads) >= 4
    assert payloads[0].ingest_mode == "fixture"


@pytest.mark.asyncio
async def test_swpc_live_fetch_mocked(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NOAA_SWPC_USE_FIXTURES", "false")
    monkeypatch.setenv("SOURCES_LIVE", "noaa_swpc")
    get_settings.cache_clear()

    fixture_data = load_fixture("noaa_swpc", "conditions.json", refresh_dates=False)
    adapter = NoaaSwpcSourceAdapter()

    async def mock_alerts(url, params=None):
        return fixture_data["alerts"]

    async def mock_scales(url, params=None):
        return fixture_data["scales"]

    adapter._http.get_json_list = mock_alerts  # type: ignore[method-assign]
    adapter._http.get_json = mock_scales  # type: ignore[method-assign]

    payloads = await adapter.fetch_alerts()
    assert len(payloads) >= 4
    assert payloads[0].ingest_mode == "live"


@pytest.mark.asyncio
async def test_swpc_ingest_populates_observed_events(db_session) -> None:
    from sqlalchemy import func, select

    from app.models.observed_event import ObservedEvent
    from app.services.ingest_service import run_ingest

    run = await run_ingest(db_session, sources=["noaa_swpc"])
    db_session.commit()

    assert run.status == "success"
    count = db_session.scalar(
        select(func.count()).select_from(ObservedEvent).where(ObservedEvent.source == "noaa_swpc")
    )
    assert count >= 4
