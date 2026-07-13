"""Transparent global risk score (0-100) with documented weighting.

See docs/risk-scoring.md for the full specification.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import shape

from app.core.config import get_settings
from app.models.alert import Alert

# Stage 1: severity base weights
SEVERITY_WEIGHTS: dict[str, int] = {
    "minor": 1,
    "moderate": 3,
    "severe": 6,
    "extreme": 10,
    "unknown": 1,
}

# Stage 2: per-alert modifiers
URGENCY_MODIFIERS: dict[str, float] = {
    "immediate": 1.5,
    "expected": 1.2,
}

CERTAINTY_MODIFIERS: dict[str, float] = {
    "observed": 1.3,
    "likely": 1.1,
}

GEO_AREA_THRESHOLDS_KM2: list[tuple[float, float]] = [
    (50_000, 1.5),
    (10_000, 1.2),
]

DURATION_MODIFIERS_HOURS: list[tuple[int, float]] = [
    (7 * 24, 1.2),
    (48, 1.1),
]

MODERATE_PLUS = frozenset({"moderate", "severe", "extreme"})


@dataclass
class AlertScoreDetail:
    alert_id: str
    base_weight: int
    urgency_mod: float
    certainty_mod: float
    geo_mod: float
    duration_mod: float
    alert_score: float
    area_km2: float | None = None


@dataclass
class ClusterBonusDetail:
    region: str
    bonus: float
    alert_ids: list[str]
    severe_or_extreme_count: int
    moderate_count: int


@dataclass
class RiskScoreResult:
    global_score: int
    raw_total: float
    trend_modifier: float
    alert_scores: list[AlertScoreDetail] = field(default_factory=list)
    cluster_bonuses: list[ClusterBonusDetail] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)


def _geometry_area_km2(alert: Alert) -> float | None:
    geojson = alert.geometry_json
    if not geojson:
        return None
    try:
        geom = shape(geojson)
        # Approximate area in km² using equirectangular projection at centroid latitude
        centroid = geom.centroid
        lat_rad = centroid.y * 3.14159265 / 180.0
        area_deg2 = abs(geom.area)
        km_per_deg_lat = 111.32
        km_per_deg_lon = 111.32 * abs(__import__("math").cos(lat_rad))
        return area_deg2 * km_per_deg_lat * km_per_deg_lon
    except Exception:
        return None


def _geo_modifier(area_km2: float | None) -> float:
    if area_km2 is None:
        return 1.0
    mod = 1.0
    for threshold, multiplier in GEO_AREA_THRESHOLDS_KM2:
        if area_km2 > threshold:
            mod = multiplier
    return mod


def _duration_modifier(alert: Alert, now: datetime) -> float:
    start = alert.effective_at or alert.issued_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=now.tzinfo)
    hours_active = (now - start).total_seconds() / 3600
    mod = 1.0
    for threshold_hours, multiplier in DURATION_MODIFIERS_HOURS:
        if hours_active > threshold_hours:
            mod = multiplier
    return mod


def compute_alert_score(alert: Alert, now: datetime) -> AlertScoreDetail:
    """Stage 1+2: base weight × urgency × certainty × geo × duration."""
    base = SEVERITY_WEIGHTS.get(alert.severity, 1)
    urgency_mod = URGENCY_MODIFIERS.get(alert.urgency or "", 1.0)
    certainty_mod = CERTAINTY_MODIFIERS.get(alert.certainty or "", 1.0)
    area_km2 = _geometry_area_km2(alert)
    geo_mod = _geo_modifier(area_km2)
    duration_mod = _duration_modifier(alert, now)
    score = base * urgency_mod * certainty_mod * geo_mod * duration_mod
    return AlertScoreDetail(
        alert_id=str(alert.id),
        base_weight=base,
        urgency_mod=urgency_mod,
        certainty_mod=certainty_mod,
        geo_mod=geo_mod,
        duration_mod=duration_mod,
        alert_score=round(score, 2),
        area_km2=round(area_km2, 2) if area_km2 is not None else None,
    )


def _region_label(alert: Alert) -> str:
    if alert.region and alert.country_code:
        return f"{alert.region}, {alert.country_code}"
    if alert.country_code:
        return alert.country_code
    if alert.location_name:
        return alert.location_name
    return "unknown"


def compute_cluster_bonuses(
    alerts: list[Alert],
    cluster_details: list[ClusterBonusDetail] | None = None,
) -> list[ClusterBonusDetail]:
    """Stage 3: regional cluster bonus from pre-computed hotspots."""
    if cluster_details is not None:
        return cluster_details
    # Fallback: country+region grouping for moderate+ alerts
    from collections import defaultdict

    groups: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        if alert.severity in MODERATE_PLUS:
            groups[_region_label(alert)].append(alert)

    bonuses: list[ClusterBonusDetail] = []
    for region, group in groups.items():
        if len(group) < 3:
            continue
        severe_extreme = sum(1 for a in group if a.severity in ("severe", "extreme"))
        moderate = sum(1 for a in group if a.severity == "moderate")
        bonus = severe_extreme * 2 + moderate * 1
        bonuses.append(
            ClusterBonusDetail(
                region=region,
                bonus=float(bonus),
                alert_ids=[str(a.id) for a in group],
                severe_or_extreme_count=severe_extreme,
                moderate_count=moderate,
            )
        )
    return bonuses


def compute_trend_modifier(current_count: int, rolling_avg: float) -> float:
    """Stage 4: compare active alerts vs 7-day rolling average."""
    if rolling_avg <= 0:
        return 1.0 if current_count == 0 else 1.3
    ratio = current_count / rolling_avg
    if ratio < 0.8:
        return 0.9
    if ratio <= 1.2:
        return 1.0
    if ratio <= 1.5:
        return 1.1
    if ratio <= 2.0:
        return 1.2
    return 1.3


def compute_global_risk_score(
    alerts: list[Alert],
    *,
    now: datetime | None = None,
    cluster_bonuses: list[ClusterBonusDetail] | None = None,
    trend_modifier: float | None = None,
    rolling_avg_active: float | None = None,
) -> RiskScoreResult:
    """Compute normalized global risk score (0-100) with full breakdown."""
    settings = get_settings()
    now = now or datetime.now(UTC)

    alert_details = [compute_alert_score(a, now) for a in alerts]
    alert_total = sum(d.alert_score for d in alert_details)

    clusters = compute_cluster_bonuses(alerts, cluster_bonuses)
    cluster_total = sum(c.bonus for c in clusters)

    raw_total = alert_total + cluster_total

    if trend_modifier is None:
        avg = rolling_avg_active if rolling_avg_active is not None else len(alerts)
        trend_modifier = compute_trend_modifier(len(alerts), avg)

    scaling = settings.risk_score_scaling
    # scaling_factor calibrates sensitivity: at default (50), score ≈ raw_total
    normalized = min(100, round(raw_total * trend_modifier * 50 / scaling))

    breakdown: dict[str, Any] = {
        "alert_score_sum": round(alert_total, 2),
        "cluster_bonus_sum": round(cluster_total, 2),
        "raw_total": round(raw_total, 2),
        "trend_modifier": trend_modifier,
        "scaling_factor": scaling,
        "active_count": len(alerts),
        "alert_details": [
            {
                "alert_id": d.alert_id,
                "base_weight": d.base_weight,
                "urgency_mod": d.urgency_mod,
                "certainty_mod": d.certainty_mod,
                "geo_mod": d.geo_mod,
                "duration_mod": d.duration_mod,
                "area_km2": d.area_km2,
                "alert_score": d.alert_score,
            }
            for d in alert_details
        ],
        "cluster_bonuses": [
            {
                "region": c.region,
                "bonus": c.bonus,
                "alert_ids": c.alert_ids,
                "severe_or_extreme_count": c.severe_or_extreme_count,
                "moderate_count": c.moderate_count,
            }
            for c in clusters
        ],
    }

    return RiskScoreResult(
        global_score=normalized,
        raw_total=raw_total,
        trend_modifier=trend_modifier,
        alert_scores=alert_details,
        cluster_bonuses=clusters,
        breakdown=breakdown,
    )


def alert_duration_hours(alert: Alert, now: datetime) -> float:
    start = alert.effective_at or alert.issued_at
    return (now - start).total_seconds() / 3600
