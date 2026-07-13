"""Detect regions with multiple parallel severe/extreme alerts."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from app.core.config import get_settings
from app.models.alert import Alert

SEVERE_PLUS = frozenset({"severe", "extreme"})
MODERATE_PLUS = frozenset({"moderate", "severe", "extreme"})


@dataclass
class HotspotCluster:
    region: str
    count: int
    max_severity: str
    alert_ids: list[str]
    severe_or_extreme_count: int
    moderate_count: int
    cluster_type: str  # "country_region" | "spatial" | "country_category"


def _region_label(alert: Alert) -> str:
    if alert.region and alert.country_code:
        return f"{alert.region}, {alert.country_code}"
    if alert.country_name and alert.country_code:
        return f"{alert.country_code}"
    if alert.country_code:
        return alert.country_code
    if alert.location_name:
        return alert.location_name
    return "unknown"


def _severity_rank(severity: str) -> int:
    return {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}.get(severity, 0)


def _max_severity(alerts: list[Alert]) -> str:
    return max(alerts, key=lambda a: _severity_rank(a.severity)).severity


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _detect_country_region_clusters(alerts: list[Alert]) -> list[HotspotCluster]:
    """Group by country+region with >=3 moderate+ alerts."""
    groups: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        if alert.severity in MODERATE_PLUS:
            groups[_region_label(alert)].append(alert)

    clusters: list[HotspotCluster] = []
    for region, group in groups.items():
        if len(group) < 3:
            continue
        severe_extreme = [a for a in group if a.severity in SEVERE_PLUS]
        moderate = [a for a in group if a.severity == "moderate"]
        clusters.append(
            HotspotCluster(
                region=region,
                count=len(group),
                max_severity=_max_severity(group),
                alert_ids=[str(a.id) for a in group],
                severe_or_extreme_count=len(severe_extreme),
                moderate_count=len(moderate),
                cluster_type="country_region",
            )
        )
    return clusters


def _detect_country_category_clusters(alerts: list[Alert]) -> list[HotspotCluster]:
    """Same country + category with >=3 severe/extreme alerts."""
    groups: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        if alert.severity in SEVERE_PLUS and alert.country_code:
            key = f"{alert.country_code}:{alert.category}"
            groups[key].append(alert)

    clusters: list[HotspotCluster] = []
    for key, group in groups.items():
        if len(group) < 3:
            continue
        country, category = key.split(":", 1)
        clusters.append(
            HotspotCluster(
                region=f"{country} ({category})",
                count=len(group),
                max_severity=_max_severity(group),
                alert_ids=[str(a.id) for a in group],
                severe_or_extreme_count=len(group),
                moderate_count=0,
                cluster_type="country_category",
            )
        )
    return clusters


def _detect_spatial_clusters(alerts: list[Alert], radius_km: float) -> list[HotspotCluster]:
    """Group alerts within radius_km with >=3 severe/extreme."""
    located = [
        a for a in alerts if a.severity in SEVERE_PLUS and a.latitude is not None and a.longitude is not None
    ]
    if len(located) < 3:
        return []

    used: set[int] = set()
    clusters: list[HotspotCluster] = []

    for i, seed in enumerate(located):
        if i in used:
            continue
        group = [seed]
        used.add(i)
        for j, other in enumerate(located):
            if j in used:
                continue
            dist = _haversine_km(seed.latitude, seed.longitude, other.latitude, other.longitude)
            if dist <= radius_km:
                group.append(other)
                used.add(j)

        if len(group) >= 3:
            region = _region_label(seed)
            severe_extreme = [a for a in group if a.severity in SEVERE_PLUS]
            clusters.append(
                HotspotCluster(
                    region=region,
                    count=len(group),
                    max_severity=_max_severity(group),
                    alert_ids=[str(a.id) for a in group],
                    severe_or_extreme_count=len(severe_extreme),
                    moderate_count=0,
                    cluster_type="spatial",
                )
            )
    return clusters


def detect_hotspots(alerts: list[Alert]) -> list[HotspotCluster]:
    """Detect hotspot regions with multiple parallel severe/extreme alerts."""
    settings = get_settings()
    active = [a for a in alerts if a.is_active]

    clusters: list[HotspotCluster] = []
    clusters.extend(_detect_country_region_clusters(active))
    clusters.extend(_detect_country_category_clusters(active))
    clusters.extend(_detect_spatial_clusters(active, settings.risk_cluster_radius_km))

    # Deduplicate by alert_ids set, keep highest count
    seen: dict[frozenset[str], HotspotCluster] = {}
    for cluster in clusters:
        key = frozenset(cluster.alert_ids)
        if key not in seen or cluster.count > seen[key].count:
            seen[key] = cluster

    result = sorted(seen.values(), key=lambda c: (-c.severe_or_extreme_count, -c.count))
    return result


def clusters_to_bonus_details(clusters: list[HotspotCluster]):
    """Convert hotspot clusters to risk score cluster bonus details."""
    from app.analysis.risk_score import ClusterBonusDetail

    return [
        ClusterBonusDetail(
            region=c.region,
            bonus=float(c.severe_or_extreme_count * 2 + c.moderate_count),
            alert_ids=c.alert_ids,
            severe_or_extreme_count=c.severe_or_extreme_count,
            moderate_count=c.moderate_count,
        )
        for c in clusters
        if c.count >= 3
    ]
