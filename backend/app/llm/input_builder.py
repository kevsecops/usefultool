"""Build compact, normalized analysis input for LLM."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.analysis.clustering import HotspotCluster
from app.analysis.risk_score import RiskScoreResult
from app.analysis.trends import TrendAnomaly
from app.llm.evidence_package import build_evidence_package, has_canonical_events
from app.llm.sanitize import sanitize_alert_text
from app.models.alert import Alert

SEVERITY_RANK = {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}
MAX_ALERTS = 50


def _region_label(alert: Alert) -> str:
    if alert.region and alert.country_code:
        return f"{alert.region}, {alert.country_code}"
    if alert.country_name:
        return alert.country_name
    if alert.country_code:
        return alert.country_code
    if alert.location_name:
        return alert.location_name
    return "unknown"


def _top_alerts(alerts: list[Alert], limit: int = MAX_ALERTS) -> list[Alert]:
    return sorted(
        alerts,
        key=lambda a: (SEVERITY_RANK.get(a.severity, 0), a.issued_at),
        reverse=True,
    )[:limit]


def _alert_summary(alert: Alert) -> dict[str, Any]:
    title = sanitize_alert_text(alert.title)
    return {
        "id": str(alert.id),
        "source": alert.source,
        "title": f"<alert_data>{title}</alert_data>",
        "severity": alert.severity,
        "category": alert.category,
        "country_code": alert.country_code,
        "region": alert.region,
        "issued_at": alert.issued_at.isoformat().replace("+00:00", "Z"),
    }


def _stats_block(
    alerts: list[Alert],
    risk: RiskScoreResult,
) -> dict[str, Any]:
    by_country: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    for alert in alerts:
        if alert.country_code:
            by_country[alert.country_code] += 1
        by_category[alert.category] += 1
        by_severity[alert.severity] += 1

    return {
        "active_count": len(alerts),
        "global_risk_score": risk.global_score,
        "by_country": dict(by_country.most_common(20)),
        "by_category": dict(by_category.most_common()),
        "by_severity": dict(by_severity.most_common()),
        "score_breakdown": risk.breakdown,
    }


def _clusters_block(hotspots: list[HotspotCluster]) -> list[dict[str, Any]]:
    return [
        {
            "region": h.region,
            "count": h.count,
            "max_severity": h.max_severity,
            "alert_ids": h.alert_ids,
            "cluster_type": h.cluster_type,
            "severe_or_extreme_count": h.severe_or_extreme_count,
        }
        for h in hotspots[:15]
    ]


def _proximity_hints(hotspots: list[HotspotCluster]) -> list[dict[str, Any]]:
    """Cross-border proximity hints from clustering."""
    hints: list[dict[str, Any]] = []
    for h in hotspots:
        if h.cluster_type == "spatial" and h.count >= 3:
            hints.append(
                {
                    "type": "spatial_cluster",
                    "region": h.region,
                    "alert_count": h.count,
                    "alert_ids": h.alert_ids,
                    "note": "Alerts within geographic proximity radius",
                }
            )
        elif h.severe_or_extreme_count >= 3:
            hints.append(
                {
                    "type": "regional_concentration",
                    "region": h.region,
                    "alert_count": h.count,
                    "alert_ids": h.alert_ids,
                }
            )
    return hints


def _build_alert_input(
    alerts: list[Alert],
    *,
    risk: RiskScoreResult,
    hotspots: list[HotspotCluster],
    anomalies: list[TrendAnomaly],
    generated_at: datetime,
) -> dict[str, Any]:
    """Legacy alert-based input when no canonical events exist."""
    active = [a for a in alerts if a.is_active]
    selected = _top_alerts(active)

    return {
        "input_mode": "alerts",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "stats": _stats_block(active, risk),
        "alerts": [_alert_summary(a) for a in selected],
        "clusters": _clusters_block(hotspots),
        "proximity_hints": _proximity_hints(hotspots),
        "trend_anomalies": [
            {
                "dimension": a.dimension,
                "key": a.key,
                "current_count": a.current_count,
                "rolling_avg": a.rolling_avg,
                "ratio": a.ratio,
            }
            for a in anomalies
        ],
        "valid_alert_ids": [str(a.id) for a in active],
        "valid_source_ids": [str(a.id) for a in active],
        "truncated": len(active) > MAX_ALERTS,
        "total_active_count": len(active),
    }


def build_analysis_input(
    alerts: list[Alert],
    *,
    risk: RiskScoreResult,
    hotspots: list[HotspotCluster],
    anomalies: list[TrendAnomaly],
    generated_at: datetime,
    db: Session | None = None,
) -> dict[str, Any]:
    """Build compact structured input — evidence package when canonical events exist."""
    active = [a for a in alerts if a.is_active]

    if db is not None and has_canonical_events(db):
        evidence = build_evidence_package(
            db,
            risk=risk,
            generated_at=generated_at,
            active_alerts=active,
        )
        return {
            "input_mode": "evidence_package",
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "stats": _stats_block(active, risk),
            "evidence_package": evidence,
            "clusters": _clusters_block(hotspots),
            "proximity_hints": _proximity_hints(hotspots),
            "trend_anomalies": [
                {
                    "dimension": a.dimension,
                    "key": a.key,
                    "current_count": a.current_count,
                    "rolling_avg": a.rolling_avg,
                    "ratio": a.ratio,
                }
                for a in anomalies
            ],
            "valid_alert_ids": [str(a.id) for a in active],
            "valid_source_ids": evidence.get("valid_source_ids", []),
            "truncated": evidence.get("truncated_events", False),
            "total_active_count": len(active),
        }

    return _build_alert_input(
        alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=anomalies,
        generated_at=generated_at,
    )
