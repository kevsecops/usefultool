"""Grid + time-window clustering for NASA FIRMS thermal anomaly points."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from app.schemas.common import Confidence, Severity

_CONFIDENCE_SCORE = {
    "low": 1,
    "l": 1,
    "nominal": 2,
    "n": 2,
    "high": 3,
    "h": 3,
}

_SEVERITY_ORDER = [
    Severity.UNKNOWN,
    Severity.MINOR,
    Severity.MODERATE,
    Severity.SEVERE,
    Severity.EXTREME,
]


@dataclass(frozen=True)
class FirmsPoint:
    """Single FIRMS thermal anomaly detection."""

    point_id: str
    latitude: float
    longitude: float
    acquired_at: datetime
    brightness: float | None = None
    frp: float | None = None
    confidence: str | None = None
    satellite: str | None = None
    instrument: str | None = None
    scan: float | None = None
    track: float | None = None
    daynight: str | None = None


@dataclass
class FireCluster:
    """Aggregated active-fire cluster derived from FIRMS points."""

    cluster_id: str
    points: list[FirmsPoint]
    centroid_lat: float
    centroid_lon: float
    bounding_geometry: dict[str, Any]
    first_detected_at: datetime
    last_detected_at: datetime
    max_confidence: str | None
    avg_confidence_score: float
    satellite_sources: list[str]
    maximum_brightness: float | None
    maximum_frp: float | None
    avg_frp: float | None
    source_record_ids: list[str]
    severity: Severity
    confidence: Confidence


def _grid_index(value: float, grid_deg: float) -> int:
    return int(value // grid_deg)


def _time_bucket(acquired_at: datetime, time_hours: float) -> int:
    epoch_hours = acquired_at.timestamp() / 3600
    bucket_size = max(time_hours, 0.1)
    return int(epoch_hours // bucket_size)


def _confidence_score(label: str | None) -> float:
    if not label:
        return 0.0
    return float(_CONFIDENCE_SCORE.get(label.strip().lower(), 0))


def _score_to_confidence_label(score: float) -> str | None:
    if score >= 2.5:
        return "high"
    if score >= 1.5:
        return "nominal"
    if score >= 0.5:
        return "low"
    return None


def _cluster_confidence(avg_score: float) -> Confidence:
    if avg_score >= 2.5:
        return Confidence.HIGH
    if avg_score >= 1.5:
        return Confidence.MEDIUM
    return Confidence.LOW


def cluster_severity(
    point_count: int,
    maximum_frp: float | None,
    maximum_brightness: float | None,
) -> Severity:
    """Heuristic severity from cluster density and radiometric signals."""
    frp = maximum_frp or 0.0
    brightness = maximum_brightness or 0.0

    if point_count >= 20 or frp >= 500 or brightness >= 400:
        return Severity.EXTREME
    if point_count >= 10 or frp >= 100 or brightness >= 330:
        return Severity.SEVERE
    if point_count >= 5 or frp >= 30 or brightness >= 300:
        return Severity.MODERATE
    if point_count >= 2:
        return Severity.MINOR
    return Severity.UNKNOWN


def _bbox_polygon(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    *,
    pad_deg: float = 0.02,
) -> dict[str, Any]:
    south = min_lat - pad_deg
    north = max_lat + pad_deg
    west = min_lon - pad_deg
    east = max_lon + pad_deg
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


def _stable_cluster_id(grid_lat: int, grid_lon: int, time_bucket: int) -> str:
    raw = f"firms:{grid_lat}:{grid_lon}:{time_bucket}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"firms-cluster-{digest}"


def cluster_firms_points(
    points: list[FirmsPoint],
    *,
    grid_deg: float = 0.5,
    time_hours: float = 24.0,
    min_cluster_points: int = 3,
) -> list[FireCluster]:
    """Group FIRMS points by lat/lon grid cell and time bucket."""
    if not points:
        return []

    grid_deg = max(grid_deg, 0.01)
    min_cluster_points = max(min_cluster_points, 1)

    buckets: dict[tuple[int, int, int], list[FirmsPoint]] = {}
    for point in points:
        key = (
            _grid_index(point.latitude, grid_deg),
            _grid_index(point.longitude, grid_deg),
            _time_bucket(point.acquired_at, time_hours),
        )
        buckets.setdefault(key, []).append(point)

    clusters: list[FireCluster] = []
    for (grid_lat, grid_lon, time_bucket), group in sorted(buckets.items()):
        if len(group) < min_cluster_points:
            continue

        lats = [p.latitude for p in group]
        lons = [p.longitude for p in group]
        centroid_lat = mean(lats)
        centroid_lon = mean(lons)

        conf_scores = [_confidence_score(p.confidence) for p in group]
        avg_conf_score = mean(conf_scores) if conf_scores else 0.0
        max_conf_score = max(conf_scores) if conf_scores else 0.0
        max_conf_label = _score_to_confidence_label(max_conf_score)

        brightness_vals = [p.brightness for p in group if p.brightness is not None]
        frp_vals = [p.frp for p in group if p.frp is not None]
        max_brightness = max(brightness_vals) if brightness_vals else None
        max_frp = max(frp_vals) if frp_vals else None
        avg_frp = mean(frp_vals) if frp_vals else None

        satellites = sorted({p.satellite for p in group if p.satellite})

        acquired_times = [p.acquired_at for p in group]
        first_detected = min(acquired_times)
        last_detected = max(acquired_times)

        clusters.append(
            FireCluster(
                cluster_id=_stable_cluster_id(grid_lat, grid_lon, time_bucket),
                points=group,
                centroid_lat=centroid_lat,
                centroid_lon=centroid_lon,
                bounding_geometry=_bbox_polygon(min(lats), max(lats), min(lons), max(lons)),
                first_detected_at=first_detected,
                last_detected_at=last_detected,
                max_confidence=max_conf_label,
                avg_confidence_score=avg_conf_score,
                satellite_sources=satellites,
                maximum_brightness=max_brightness,
                maximum_frp=max_frp,
                avg_frp=avg_frp,
                source_record_ids=[p.point_id for p in group],
                severity=cluster_severity(len(group), max_frp, max_brightness),
                confidence=_cluster_confidence(avg_conf_score),
            )
        )

    return clusters


def cluster_to_metadata(cluster: FireCluster) -> dict[str, Any]:
    """Serialize cluster metrics for observed_event.source_metadata."""
    return {
        "cluster_id": cluster.cluster_id,
        "point_count": len(cluster.points),
        "bounding_geometry": cluster.bounding_geometry,
        "centroid": {
            "type": "Point",
            "coordinates": [cluster.centroid_lon, cluster.centroid_lat],
        },
        "first_detected_at": cluster.first_detected_at.astimezone(UTC).isoformat(),
        "last_detected_at": cluster.last_detected_at.astimezone(UTC).isoformat(),
        "max_confidence": cluster.max_confidence,
        "avg_confidence_score": round(cluster.avg_confidence_score, 2),
        "satellite_sources": cluster.satellite_sources,
        "maximum_brightness": cluster.maximum_brightness,
        "fire_radiative_power": {
            "maximum": cluster.maximum_frp,
            "average": round(cluster.avg_frp, 2) if cluster.avg_frp is not None else None,
        },
        "source_record_ids": cluster.source_record_ids,
    }
