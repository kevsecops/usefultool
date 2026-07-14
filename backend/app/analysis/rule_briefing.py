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

SOURCE_LABELS: dict[str, str] = {
    "nina": "NINA/BBK",
    "gdacs": "GDACS",
    "noaa": "NOAA/NWS",
}

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
        "infrastructure": ["Potenzielle Luftqualitätsbelastung in umliegenden Regionen."],
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

# Legacy/alias domain keys in CATEGORY_IMPLICATIONS mapped to briefing schema domains.
IMPLICATION_DOMAIN_ALIASES: dict[str, str] = {
    "environmental": "infrastructure",
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


def build_by_source(alerts: list[Alert]) -> list[dict[str, Any]]:
    """Per-source alert counts for briefing snapshots."""
    from collections import Counter

    counts = Counter(a.source for a in alerts)
    return [
        {
            "source": src,
            "label": SOURCE_LABELS.get(src, src),
            "count": count,
        }
        for src, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _by_source(alerts: list[Alert]) -> list[dict[str, Any]]:
    return build_by_source(alerts)


def _top_countries(alerts: list[Alert], limit: int = 5) -> list[dict[str, Any]]:
    from collections import Counter

    counts = Counter(a.country_code for a in alerts if a.country_code)
    return [{"code": code, "count": count} for code, count in counts.most_common(limit)]


def _format_source_counts(by_source: list[dict[str, Any]]) -> str:
    if not by_source:
        return ""
    return ", ".join(f"{item['label']}: {item['count']}" for item in by_source)


def _format_top_countries(top_countries: list[dict[str, Any]]) -> str:
    if not top_countries:
        return ""
    return ", ".join(f"{item['code']} ({item['count']})" for item in top_countries)


def _build_summary(
    alerts: list[Alert],
    risk: RiskScoreResult,
    hotspots: list[HotspotCluster],
    *,
    by_source: list[dict[str, Any]],
    top_countries: list[dict[str, Any]],
) -> str:
    factors = risk.breakdown.get("factor_totals", {})
    parts = [
        f"{len(alerts)} aktive Warnung{'en' if len(alerts) != 1 else ''} weltweit.",
        f"Global Risk Score: {risk.global_score}/100",
        (
            f"(Schwere: {int(factors.get('event_severity', 0))}, "
            f"Infrastruktur: {int(factors.get('infrastructure_exposure', 0))}, "
            f"Quellen: {int(factors.get('multi_source_corroboration', 0))}, "
            f"Auswirkung: {int(factors.get('humanitarian_impact', 0))})."
        ),
    ]
    source_text = _format_source_counts(by_source)
    if source_text:
        parts.append(f"Quellen: {source_text}.")
    country_text = _format_top_countries(top_countries)
    if country_text:
        parts.append(f"Top-Länder: {country_text}.")
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
    """Aggregate active alerts by country — consistent with top_countries."""
    from collections import defaultdict

    del hotspots  # hotspots used for cross_border_patterns, not region listing

    by_country: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        if alert.country_code:
            by_country[alert.country_code].append(alert)

    regions: list[dict[str, Any]] = []
    sorted_countries = sorted(
        by_country.items(),
        key=lambda item: (
            -len(item[1]),
            -max(SEVERITY_RANK.get(a.severity, 0) for a in item[1]),
            item[0],
        ),
    )
    for code, group in sorted_countries[:10]:
        country_name = next((a.country_name for a in group if a.country_name), None)
        region_label = f"{country_name} ({code})" if country_name else code
        max_sev = max(group, key=lambda a: SEVERITY_RANK.get(a.severity, 0)).severity
        regions.append(
            {
                "region": region_label,
                "country_code": code,
                "alert_count": len(group),
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


def _potential_implications(
    alerts: list[Alert],
    implication_candidates: list | None = None,
) -> dict[str, list[str]]:
    implications: dict[str, list[str]] = {
        "economy": [],
        "logistics": [],
        "infrastructure": [],
        "technology": [],
        "finance": [],
    }
    seen: set[str] = set()

    # Event-based implications from persisted candidates (Phase 6)
    if implication_candidates:
        briefing_domains = set(implications.keys())
        for candidate in implication_candidates:
            category = getattr(candidate, "category", None) or candidate.get("category")
            if category not in briefing_domains:
                continue
            text = getattr(candidate, "title", None) or candidate.get("title", "")
            if text and text not in seen:
                seen.add(text)
                implications[category].append(text)

    categories_present = {a.category for a in alerts}
    for category in categories_present:
        mapping = CATEGORY_IMPLICATIONS.get(category, {})
        for domain, statements in mapping.items():
            domain = IMPLICATION_DOMAIN_ALIASES.get(domain, domain)
            if domain not in implications:
                continue
            for stmt in statements:
                if stmt not in seen:
                    seen.add(stmt)
                    implications[domain].append(stmt)
    return implications


def _implication_refs(implication_candidates: list | None) -> dict[str, list[dict[str, str]]]:
    """Map persisted implication candidates to briefing refs with real IDs."""
    refs: dict[str, list[dict[str, str]]] = {
        "economy": [],
        "logistics": [],
        "infrastructure": [],
        "technology": [],
        "finance": [],
    }
    if not implication_candidates:
        return refs

    briefing_domains = set(refs.keys())
    for candidate in implication_candidates:
        category = getattr(candidate, "category", None) or candidate.get("category")
        if category not in briefing_domains:
            continue
        candidate_id = str(getattr(candidate, "id", None) or candidate.get("id", ""))
        event_id = str(
            getattr(candidate, "canonical_event_id", None)
            or candidate.get("canonical_event_id", "")
        )
        text = getattr(candidate, "title", None) or candidate.get("title", "")
        evidence = getattr(candidate, "evidence_level", None) or candidate.get("evidence_level")
        if not candidate_id or not text:
            continue
        refs[category].append(
            {
                "id": candidate_id,
                "text": text,
                "canonical_event_id": event_id,
                "evidence_level": evidence,
            }
        )
    return refs


def _limitations(
    anomalies: list[TrendAnomaly],
    *,
    by_source: list[dict[str, Any]],
) -> list[str]:
    limits = [
        "Regelbasierte Zusammenfassung ohne semantische Interpretation.",
        "Keine wirtschaftlichen Prognosen — nur konservative Hypothesen.",
        "Implikationen basieren auf Kategorie-Mapping, nicht auf Quelltextanalyse.",
    ]
    if by_source:
        source_names = ", ".join(item["label"] for item in by_source)
        limits.append(f"Datenbasis aus {len(by_source)} Quelle(n): {source_names}.")
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
    implication_candidates: list | None = None,
    evidence_enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate structured rule-based briefing content."""
    active = [a for a in alerts if a.is_active]
    now = generated_at or datetime.now(UTC)
    anomalies = anomalies or []
    by_source = _by_source(active)
    top_countries = _top_countries(active)

    source_ids = [str(a.id) for a in active]
    implication_refs = _implication_refs(implication_candidates)

    content = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "type": "rule_based",
        "active_count": len(active),
        "overall_risk_score": risk.global_score,
        "summary": _build_summary(
            active,
            risk,
            hotspots,
            by_source=by_source,
            top_countries=top_countries,
        ),
        "overall_confidence": _confidence(active, hotspots),
        "by_source": by_source,
        "top_countries": top_countries,
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
        "potential_implications": _potential_implications(active, implication_candidates),
        "implication_refs": implication_refs,
        "limitations": _limitations(anomalies, by_source=by_source),
        "source_alert_ids": source_ids,
        "score_breakdown": risk.breakdown,
        "observed_events": {"summary": "", "items": [], "confidence": "low"},
        "verified_exposure": {"summary": "", "items": [], "confidence": "low"},
        "confirmed_impacts": [],
        "cross_border_relevance": [],
        "technology_infrastructure_risks": [],
        "evidence_gaps": [],
        "section_confidence": {
            "observed_events": "low",
            "verified_exposure": "low",
            "potential_implications": "low",
            "confirmed_impacts": "low",
            "cross_border_relevance": "low",
            "technology_infrastructure_risks": "low",
        },
    }

    if evidence_enrichment:
        for key in (
            "observed_events",
            "verified_exposure",
            "confirmed_impacts",
            "cross_border_relevance",
            "technology_infrastructure_risks",
            "evidence_gaps",
            "section_confidence",
        ):
            if key in evidence_enrichment:
                content[key] = evidence_enrichment[key]

    return content
