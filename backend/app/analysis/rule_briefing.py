"""Rule-based briefing generation without LLM.

Produces structured JSON from alerts and computed stats only.
Observations are factual; implications use conservative hypothesis language.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.analysis.clustering import HotspotCluster
from app.analysis.risk_score import RiskScoreResult
from app.analysis.trends import TrendAnomaly
from app.models.alert import Alert

SEVERITY_RANK = {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}

CATEGORY_IMPLICATIONS: dict[str, dict[str, list[str]]] = {
    "flood": {
        "logistics": ["Mögliche Beeinträchtigung von Straßen und Schifffahrtswegen in betroffenen Gebieten."],
        "infrastructure": ["Potenzielle Belastung von Entwässerungssystemen."],
    },
    "weather": {
        "logistics": ["Mögliche Verzögerungen im Luft- und Straßenverkehr bei Unwetterlagen."],
        "infrastructure": ["Potenzielle Störungen bei Strom- und Kommunikationsnetzen."],
    },
    "wildfire": {
        "logistics": ["Mögliche Sperrungen von Verkehrswegen in Brandgebieten."],
        "environmental": ["Potenzielle Luftqualitätsbelastung in umliegenden Regionen."],
    },
    "earthquake": {
        "infrastructure": ["Mögliche Schäden an Gebäuden und kritischer Infrastruktur."],
        "logistics": ["Potenzielle Unterbrechung von Transportkorridoren."],
    },
    "civil": {
        "logistics": ["Mögliche Einschränkungen öffentlicher Verkehrsmittel."],
        "economy": ["Potenzielle lokale Betriebsunterbrechungen in Evakuierungszonen."],
    },
    "infrastructure": {
        "economy": ["Mögliche lokale wirtschaftliche Auswirkungen bei Infrastrukturausfällen."],
        "technology": ["Potenzielle Beeinträchtigung digitaler Dienste in betroffenen Gebieten."],
    },
}


def _region_label(alert: Alert) -> str:
    if alert.region and alert.country_code:
        return f"{alert.region}, {alert.country_code}"
    if alert.country_name:
        return alert.country_name
    if alert.country_code:
        return alert.country_code
    if alert.location_name:
        return alert.location_name
    return "Unbekannt"


def _confidence(alerts: list[Alert], hotspots: list[HotspotCluster]) -> str:
    if len(alerts) >= 20 and len(hotspots) >= 2:
        return "high"
    if len(alerts) >= 5:
        return "medium"
    return "low"


def _top_alerts(alerts: list[Alert], limit: int = 10) -> list[Alert]:
    return sorted(
        alerts,
        key=lambda a: (SEVERITY_RANK.get(a.severity, 0), a.issued_at),
        reverse=True,
    )[:limit]


def _build_summary(
    alerts: list[Alert],
    risk: RiskScoreResult,
    hotspots: list[HotspotCluster],
) -> str:
    parts = [
        f"{len(alerts)} aktive Warnung{'en' if len(alerts) != 1 else ''} weltweit.",
        f"Global Risk Score: {risk.global_score}/100.",
    ]
    if hotspots:
        top = hotspots[0]
        parts.append(
            f"Schwerpunkt: {top.region} ({top.count} Warnungen, max. {top.max_severity})."
        )
    elif alerts:
        top_alert = _top_alerts(alerts, 1)[0]
        parts.append(f"Höchste Einzelwarnung: {top_alert.title} ({top_alert.severity}).")
    return " ".join(parts)


def _affected_regions(alerts: list[Alert], hotspots: list[HotspotCluster]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    if hotspots:
        for h in hotspots[:10]:
            regions.append(
                {
                    "region": h.region,
                    "alert_count": h.count,
                    "max_severity": h.max_severity,
                    "alert_ids": h.alert_ids,
                }
            )
        return regions

    from collections import Counter

    by_region: Counter[str] = Counter()
    region_alerts: dict[str, list[Alert]] = {}
    for alert in alerts:
        label = _region_label(alert)
        by_region[label] += 1
        region_alerts.setdefault(label, []).append(alert)

    for region, count in by_region.most_common(10):
        group = region_alerts[region]
        max_sev = max(group, key=lambda a: SEVERITY_RANK.get(a.severity, 0)).severity
        regions.append(
            {
                "region": region,
                "alert_count": count,
                "max_severity": max_sev,
                "alert_ids": [str(a.id) for a in group],
            }
        )
    return regions


def _major_events(alerts: list[Alert]) -> list[dict[str, Any]]:
    severe_plus = [a for a in alerts if a.severity in ("severe", "extreme")]
    candidates = severe_plus if severe_plus else alerts
    return [
        {
            "title": a.title,
            "severity": a.severity,
            "source": a.source,
            "category": a.category,
            "region": _region_label(a),
            "alert_id": str(a.id),
        }
        for a in _top_alerts(candidates, 10)
    ]


def _cross_border_patterns(alerts: list[Alert], hotspots: list[HotspotCluster]) -> list[dict[str, Any]]:
    """Observations only: multiple countries with same category spikes."""
    from collections import defaultdict

    by_category_countries: dict[str, set[str]] = defaultdict(set)
    for alert in alerts:
        if alert.country_code:
            by_category_countries[alert.category].add(alert.country_code)

    patterns: list[dict[str, Any]] = []
    for category, countries in by_category_countries.items():
        if len(countries) >= 2:
            country_alerts = [a for a in alerts if a.category == category and a.country_code in countries]
            patterns.append(
                {
                    "type": "multi_country_category",
                    "description": (
                        f"Kategorie '{category}' mit aktiven Warnungen in "
                        f"{len(countries)} Ländern: {', '.join(sorted(countries))}."
                    ),
                    "alert_ids": [str(a.id) for a in country_alerts[:20]],
                    "confidence": "medium" if len(countries) >= 3 else "low",
                }
            )

    for hotspot in hotspots:
        if hotspot.severe_or_extreme_count >= 3:
            patterns.append(
                {
                    "type": "regional_cluster",
                    "description": (
                        f"{hotspot.count} parallele Warnungen (max. {hotspot.max_severity}) "
                        f"in {hotspot.region}."
                    ),
                    "alert_ids": hotspot.alert_ids,
                    "confidence": "high" if hotspot.severe_or_extreme_count >= 3 else "medium",
                }
            )
    return patterns


def _potential_implications(alerts: list[Alert]) -> dict[str, list[str]]:
    implications: dict[str, list[str]] = {
        "economy": [],
        "logistics": [],
        "infrastructure": [],
        "technology": [],
        "finance": [],
    }
    seen: set[str] = set()
    categories_present = {a.category for a in alerts}
    for category in categories_present:
        mapping = CATEGORY_IMPLICATIONS.get(category, {})
        for domain, statements in mapping.items():
            for stmt in statements:
                if stmt not in seen:
                    seen.add(stmt)
                    implications[domain].append(stmt)
    return implications


def _limitations(anomalies: list[TrendAnomaly]) -> list[str]:
    limits = [
        "Regelbasierte Zusammenfassung ohne semantische Interpretation.",
        "Keine wirtschaftlichen Prognosen — nur konservative Hypothesen.",
        "Implikationen basieren auf Kategorie-Mapping, nicht auf Quelltextanalyse.",
    ]
    if anomalies:
        limits.append(
            f"{len(anomalies)} Trend-Anomalie(n) erkannt — Verhältnis zu 7-Tage-Durchschnitt geprüft."
        )
    return limits


def generate_rule_briefing(
    alerts: list[Alert],
    *,
    risk: RiskScoreResult,
    hotspots: list[HotspotCluster],
    anomalies: list[TrendAnomaly] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Generate structured rule-based briefing content."""
    active = [a for a in alerts if a.is_active]
    now = generated_at or datetime.now(UTC)
    anomalies = anomalies or []

    source_ids = [str(a.id) for a in active]

    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "type": "rule_based",
        "overall_risk_score": risk.global_score,
        "summary": _build_summary(active, risk, hotspots),
        "overall_confidence": _confidence(active, hotspots),
        "affected_regions": _affected_regions(active, hotspots),
        "major_events": _major_events(active),
        "cross_border_patterns": _cross_border_patterns(active, hotspots),
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
        "potential_implications": _potential_implications(active),
        "limitations": _limitations(anomalies),
        "source_alert_ids": source_ids,
        "score_breakdown": risk.breakdown,
    }
