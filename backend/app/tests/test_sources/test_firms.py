"""FIRMS adapter tests."""

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.http_client import HttpClient
from app.sources.firms import (
    FirmsSourceAdapter,
    build_firms_point_id,
    parse_firms_csv,
    parse_firms_fixture_points,
)
from app.sources.fixture_loader import load_fixture


SAMPLE_CSV = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight
38.42000,-1.05000,320.10,0.40,0.40,2026-07-13,1200,N,VIIRS,nominal,2.0NRT,285.50,45.20,D
38.44000,-1.02000,335.50,0.40,0.40,2026-07-13,1215,N,VIIRS,high,2.0NRT,290.10,62.80,D
38.46000,-1.08000,310.00,0.40,0.40,2026-07-13,1230,N,VIIRS,nominal,2.0NRT,280.00,38.10,D
38.02000,23.52000,305.50,0.40,0.40,2026-07-13,1100,N,VIIRS,nominal,2.0NRT,275.00,28.00,D
38.04000,23.55000,318.20,0.40,0.40,2026-07-13,1115,N,VIIRS,nominal,2.0NRT,278.00,41.50,D
38.06000,23.58000,325.00,0.40,0.40,2026-07-13,1130,N,VIIRS,high,2.0NRT,282.00,55.00,D
"""


def test_parse_firms_csv() -> None:
    points = parse_firms_csv(SAMPLE_CSV)
    assert len(points) == 6
    assert points[0].latitude == pytest.approx(38.42)
    assert points[0].frp == pytest.approx(45.2)
    assert points[0].acquired_at.tzinfo == UTC


def test_build_firms_point_id() -> None:
    pid = build_firms_point_id(38.42, -1.05, "2026-07-13", "1200", "N")
    assert "38.4200" in pid
    assert "2026-07-13" in pid


def test_parse_fixture_points() -> None:
    data = load_fixture("firms", "mediterranean_points.json", refresh_dates=False)
    points = parse_firms_fixture_points(data)
    assert len(points) == 15


def test_fixture_clusters_into_three_groups() -> None:
    adapter = FirmsSourceAdapter()
    data = load_fixture("firms", "mediterranean_points.json", refresh_dates=False)
    points = parse_firms_fixture_points(data)
    clusters = adapter._cluster_points(points)
    assert adapter.last_raw_points_fetched == 15
    assert adapter.last_clusters_persisted == 3


@pytest.mark.asyncio
async def test_fetch_alerts_returns_clusters_not_raw_points(monkeypatch) -> None:
    adapter = FirmsSourceAdapter()
    monkeypatch.setattr(adapter, "_use_fixtures", lambda: True)
    payloads = await adapter.fetch_alerts()
    assert len(payloads) == 3
    assert all("cluster_id" in p.data for p in payloads)
    assert all("point_count" in p.data for p in payloads)


def test_normalize_observed_event_active_fire_cluster() -> None:
    adapter = FirmsSourceAdapter()
    from app.sources.base import RawAlertPayload

    cluster_data = {
        "cluster_id": "firms-cluster-demo",
        "point_count": 4,
        "centroid_lat": 38.45,
        "centroid_lon": -1.04,
        "first_detected_at": "2026-07-13T10:00:00+00:00",
        "last_detected_at": "2026-07-13T12:45:00+00:00",
        "severity": "moderate",
        "confidence": "medium",
        "source_metadata": {
            "cluster_id": "firms-cluster-demo",
            "point_count": 4,
            "bounding_geometry": {
                "type": "Polygon",
                "coordinates": [[[-1.1, 38.4], [-1.0, 38.4], [-1.0, 38.5], [-1.1, 38.5], [-1.1, 38.4]]],
            },
            "centroid": {"type": "Point", "coordinates": [-1.04, 38.45]},
            "first_detected_at": "2026-07-13T10:00:00+00:00",
            "last_detected_at": "2026-07-13T12:45:00+00:00",
            "max_confidence": "high",
            "avg_confidence_score": 2.0,
            "satellite_sources": ["N"],
            "maximum_brightness": 342.0,
            "fire_radiative_power": {"maximum": 88.4, "average": 58.6},
            "source_record_ids": ["p1", "p2", "p3", "p4"],
        },
        "_ingest_mode": "fixture",
    }
    raw = RawAlertPayload(source="firms", data=cluster_data, ingest_mode="fixture")
    canonical = adapter.normalize_observed_event(adapter.parse_observed_event(raw))

    assert canonical.source == "firms"
    assert canonical.event_type == "active_fire_cluster"
    assert canonical.category == "wildfire"
    assert canonical.geometry["type"] == "Polygon"
    assert canonical.source_metadata["point_count"] == 4
    assert len(canonical.raw_payload) == 3
    assert "p1" not in str(canonical.raw_payload)


@pytest.mark.asyncio
async def test_live_fetch_parses_csv(monkeypatch) -> None:
    mock_http = MagicMock(spec=HttpClient)
    mock_http.get_text = AsyncMock(return_value=SAMPLE_CSV)

    adapter = FirmsSourceAdapter(http_client=mock_http)
    monkeypatch.setattr(adapter, "_use_fixtures", lambda: False)
    adapter.settings = type(
        "S",
        (),
        {
            "demo_mode": False,
            "firms_use_fixtures": False,
            "firms_map_key": "test-key",
            "sources_live": "firms",
            "firms_base_url": "https://firms.modaps.eosdis.nasa.gov",
            "firms_product": "VIIRS_SNPP_NRT",
            "firms_area_coords": "0,36,20,46",
            "firms_day_range": 1,
            "firms_region_label": "Southern Europe / Mediterranean",
            "firms_cluster_grid_deg": 0.5,
            "firms_cluster_time_hours": 24.0,
            "firms_min_cluster_points": 3,
            "firms_fallback_to_fixtures": False,
            "firms_user_agent": "test",
            "firms_fetch_timeout_seconds": 30.0,
            "firms_max_retries": 1,
            "firms_max_response_bytes": 50_000_000,
        },
    )()

    points = await adapter._fetch_points_live()
    assert len(points) == 6
    mock_http.get_text.assert_awaited_once()
