"""FIRMS grid clustering tests."""

from datetime import UTC, datetime

from app.analysis.firms_clustering import (
    FirmsPoint,
    cluster_firms_points,
    cluster_severity,
)
from app.schemas.common import Severity


def _point(lat: float, lon: float, hour: int = 12) -> FirmsPoint:
    return FirmsPoint(
        point_id=f"p-{lat}-{lon}",
        latitude=lat,
        longitude=lon,
        acquired_at=datetime(2026, 7, 13, hour, 0, tzinfo=UTC),
        brightness=320.0,
        frp=50.0,
        confidence="nominal",
        satellite="N",
    )


def test_cluster_groups_nearby_points() -> None:
    points = [
        _point(38.42, -1.05, 12),
        _point(38.44, -1.02, 13),
        _point(38.46, -1.08, 14),
        _point(38.02, 23.52, 11),
        _point(38.04, 23.55, 12),
        _point(38.06, 23.58, 13),
    ]
    clusters = cluster_firms_points(points, grid_deg=0.5, time_hours=24.0, min_cluster_points=3)
    assert len(clusters) == 2
    assert all(len(c.points) >= 3 for c in clusters)


def test_min_cluster_threshold_filters_noise() -> None:
    points = [
        _point(38.42, -1.05),
        _point(38.44, -1.02),
        _point(41.50, 2.10),
        _point(41.52, 2.12),
    ]
    clusters = cluster_firms_points(points, grid_deg=0.5, time_hours=24.0, min_cluster_points=3)
    assert clusters == []


def test_cluster_metadata_fields() -> None:
    points = [_point(38.42 + i * 0.01, -1.05 + i * 0.01, 10 + i) for i in range(4)]
    clusters = cluster_firms_points(points, min_cluster_points=3)
    cluster = clusters[0]
    assert cluster.cluster_id.startswith("firms-cluster-")
    assert cluster.maximum_brightness is not None
    assert cluster.maximum_frp is not None
    assert len(cluster.source_record_ids) == 4
    assert cluster.bounding_geometry["type"] == "Polygon"


def test_cluster_severity_heuristic() -> None:
    assert cluster_severity(20, 500, 400) == Severity.EXTREME
    assert cluster_severity(10, 100, 330) == Severity.SEVERE
    assert cluster_severity(5, 30, 300) == Severity.MODERATE
    assert cluster_severity(2, 5, 280) == Severity.MINOR
