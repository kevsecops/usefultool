"""Deterministic mock LLM provider for demo and tests."""

from __future__ import annotations

import json
from typing import Any

from app.analysis.clustering import HotspotCluster
from app.analysis.risk_score import RiskScoreResult
from app.analysis.rule_briefing import generate_rule_briefing
from app.analysis.trends import TrendAnomaly
from app.llm.evidence_package import (
    build_cross_border_relevance,
    build_evidence_gaps,
    build_observed_events_section,
    build_technology_infrastructure_risks,
    build_verified_exposure_section,
)
from app.llm.provider import LLMProvider
from app.llm.sanitize import sanitize_alert_text
from app.models.alert import Alert


class MockLLMProvider(LLMProvider):
    """Returns deterministic briefing JSON derived from analysis input."""

    @property
    def model_name(self) -> str:
        return "mock-llm"

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
    ) -> dict[str, Any]:
        del system_prompt, schema_hint
        if "<evidence_package>\n" in user_prompt:
            start = user_prompt.find("<evidence_package>\n")
            end = user_prompt.find("\n</evidence_package>")
            evidence = json.loads(user_prompt[start + len("<evidence_package>\n") : end])
            return _generate_mock_extended_briefing(evidence)

        start = user_prompt.find("<analysis_input>\n")
        end = user_prompt.find("\n</analysis_input>")
        if start == -1 or end == -1:
            raise ValueError("Mock provider: missing analysis_input or evidence_package in prompt")

        analysis_input = json.loads(user_prompt[start + len("<analysis_input>\n") : end])
        return _generate_mock_briefing(analysis_input)


def _generate_mock_extended_briefing(evidence: dict[str, Any]) -> dict[str, Any]:
    """Build extended LLM briefing from evidence package (deterministic)."""
    stats = evidence.get("stats", {})
    valid_ids = set(evidence.get("valid_source_ids", []))

    alerts_data: list[dict[str, Any]] = []
    for event in evidence.get("canonical_events", []):
        for record in event.get("source_records", []):
            if record.get("member_type") == "alert":
                alerts_data.append(record)

    mock_alerts = _alerts_from_input(alerts_data, valid_ids)
    risk = _risk_from_stats(stats)

    base = generate_rule_briefing(
        mock_alerts,
        risk=risk,
        hotspots=[],
        anomalies=[],
    )

    observed_section = build_observed_events_section(evidence)
    verified_section = build_verified_exposure_section(evidence)
    evidence_gaps = build_evidence_gaps(evidence)
    cross_border = build_cross_border_relevance(evidence)
    tech_risks = build_technology_infrastructure_risks(evidence)

    implications: dict[str, list[str]] = {
        "economy": [],
        "logistics": [],
        "infrastructure": [],
        "technology": [],
        "finance": [],
    }
    for event in evidence.get("canonical_events", []):
        for imp in event.get("implication_candidates", []):
            category = imp.get("category")
            title = imp.get("title", "")
            if category in implications and title and title not in implications[category]:
                implications[category].append(title)

    base["type"] = "llm"
    base["observed_events"] = observed_section
    base["verified_exposure"] = verified_section
    base["confirmed_impacts"] = []
    base["cross_border_relevance"] = cross_border
    base["technology_infrastructure_risks"] = tech_risks
    base["evidence_gaps"] = evidence_gaps
    base["potential_implications"] = implications
    base["section_confidence"] = {
        "observed_events": observed_section.get("confidence", "low"),
        "verified_exposure": verified_section.get("confidence", "low"),
        "potential_implications": "medium" if any(implications.values()) else "low",
        "confirmed_impacts": "low",
        "cross_border_relevance": cross_border[0]["confidence"] if cross_border else "low",
        "technology_infrastructure_risks": tech_risks[0]["confidence"] if tech_risks else "low",
    }
    base["limitations"] = list(evidence.get("known_limitations", [])) + [
        "Mock-Provider für Demo/Tests — keine echte semantische Analyse.",
    ]
    if evidence.get("truncated_events"):
        base["limitations"].append(
            f"Analyse basiert auf Top-{len(evidence.get('canonical_events', []))} Ereignissen "
            f"(von {evidence.get('total_event_count', 0)} aktiv)."
        )

    event_count = stats.get("active_event_count", len(evidence.get("canonical_events", [])))
    base["summary"] = (
        f"LLM-Evidenzanalyse: {event_count} kanonische Ereignisse, "
        f"{stats.get('active_alert_count', 0)} aktive Warnungen. "
        f"Global Risk Score: {stats.get('global_risk_score', 0)}/100. "
        + (base["summary"].split(". ", 2)[-1] if ". " in base["summary"] else base["summary"])
    )

    if len({r.get("source") for e in evidence.get("canonical_events", []) for r in e.get("source_records", [])}) >= 2:
        cross_ids = list(valid_ids)[:5]
        base["cross_border_patterns"].insert(
            0,
            {
                "type": "multi_source_events",
                "description": "Aktive kanonische Ereignisse mit Quellen aus mehreren Datenfeeds.",
                "alert_ids": [aid for aid in cross_ids if aid in valid_ids][:5],
                "confidence": "medium",
            },
        )

    base["source_alert_ids"] = [str(a.id) for a in mock_alerts]
    return base


def _generate_mock_briefing(analysis_input: dict[str, Any]) -> dict[str, Any]:
    """Build LLM-style briefing from alert-based input (deterministic)."""
    stats = analysis_input.get("stats", {})
    alerts_data = analysis_input.get("alerts", [])
    clusters = analysis_input.get("clusters", [])
    anomalies = analysis_input.get("trend_anomalies", [])
    valid_ids = set(analysis_input.get("valid_alert_ids", []))

    mock_alerts = _alerts_from_input(alerts_data, valid_ids)
    hotspots = _hotspots_from_clusters(clusters)
    risk = _risk_from_stats(stats)
    trend_anomalies = _anomalies_from_input(anomalies)

    base = generate_rule_briefing(
        mock_alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=trend_anomalies,
    )

    base["type"] = "llm"
    base["observed_events"] = {"summary": "Keine kanonischen Ereignisse — nur Alert-Daten.", "items": [], "confidence": "low"}
    base["verified_exposure"] = {"summary": "Keine Exposure-Daten verfügbar.", "items": [], "confidence": "low"}
    base["confirmed_impacts"] = []
    base["cross_border_relevance"] = []
    base["technology_infrastructure_risks"] = []
    base["evidence_gaps"] = ["Keine kanonischen Ereignisse — Alert-basierter Fallback-Input."]
    base["section_confidence"] = {
        "observed_events": "low",
        "verified_exposure": "low",
        "potential_implications": "low",
        "confirmed_impacts": "low",
        "cross_border_relevance": "low",
        "technology_infrastructure_risks": "low",
    }
    base["limitations"] = [
        "KI-generierte Interpretation basierend auf strukturierten Warnungsdaten.",
        "Keine amtlichen Bewertungen — Muster sind Beobachtungen, keine Kausalitätsnachweise.",
        "Mock-Provider für Demo/Tests — keine echte semantische Analyse.",
    ]
    if analysis_input.get("truncated"):
        base["limitations"].append(
            f"Analyse basiert auf Top-{len(alerts_data)} Warnungen "
            f"(von {analysis_input.get('total_active_count', len(alerts_data))} aktiv)."
        )

    sources = {a.get("source") for a in alerts_data}
    if len(sources) >= 2 and len(alerts_data) >= 2:
        cross_ids = [a["id"] for a in alerts_data[:5] if a["id"] in valid_ids]
        base["cross_border_patterns"].insert(
            0,
            {
                "type": "cross_source_correlation",
                "description": (
                    f"Aktive Warnungen aus {len(sources)} Quellen "
                    f"({', '.join(sorted(sources))}) — mögliche regionale Korrelation."
                ),
                "alert_ids": cross_ids,
                "confidence": "medium" if len(sources) >= 3 else "low",
            },
        )

    base["summary"] = (
        f"LLM-Analyse: {stats.get('active_count', 0)} aktive Warnungen weltweit. "
        f"Global Risk Score: {stats.get('global_risk_score', 0)}/100. "
        + (base["summary"].split(". ", 2)[-1] if ". " in base["summary"] else base["summary"])
    )

    return base


def _alerts_from_input(alerts_data: list[dict], valid_ids: set[str]) -> list[Alert]:
    """Create minimal Alert ORM instances from input summaries."""
    from datetime import UTC, datetime
    from uuid import UUID

    alerts: list[Alert] = []
    now = datetime.now(UTC)
    for item in alerts_data:
        aid = item.get("id", "")
        if valid_ids and aid not in valid_ids:
            continue
        title = item.get("title", "")
        if title.startswith("<alert_data>") and title.endswith("</alert_data>"):
            title = title[len("<alert_data>") : -len("</alert_data>")]
        title = sanitize_alert_text(title)

        try:
            alert_id = UUID(aid)
        except (ValueError, AttributeError):
            continue

        alerts.append(
            Alert(
                id=alert_id,
                source=item.get("source", "unknown"),
                source_alert_id=f"mock-{aid[:8]}",
                title=title,
                category=item.get("category", "other"),
                severity=item.get("severity", "unknown"),
                status="actual",
                country_code=item.get("country_code"),
                region=item.get("region"),
                issued_at=now,
                ingested_at=now,
                last_seen_at=now,
                raw_payload={},
                fingerprint=f"mock-{aid}",
                is_active=True,
            )
        )
    return alerts


def _hotspots_from_clusters(clusters: list[dict]) -> list[HotspotCluster]:
    return [
        HotspotCluster(
            region=c.get("region", "unknown"),
            count=c.get("count", 0),
            max_severity=c.get("max_severity", "unknown"),
            alert_ids=c.get("alert_ids", []),
            severe_or_extreme_count=c.get("severe_or_extreme_count", 0),
            moderate_count=0,
            cluster_type=c.get("cluster_type", "country_region"),
        )
        for c in clusters
    ]


def _risk_from_stats(stats: dict) -> RiskScoreResult:
    from app.analysis.risk_score import RiskScoreResult

    return RiskScoreResult(
        global_score=stats.get("global_risk_score", 0),
        raw_total=float(stats.get("global_risk_score", 0)),
        trend_modifier=1.0,
        breakdown=stats.get("score_breakdown", {}),
    )


def _anomalies_from_input(anomalies: list[dict]) -> list[TrendAnomaly]:
    return [
        TrendAnomaly(
            dimension=a.get("dimension", "global"),
            key=a.get("key", ""),
            current_count=a.get("current_count", 0),
            rolling_avg=a.get("rolling_avg", 0.0),
            ratio=a.get("ratio", 0.0),
        )
        for a in anomalies
    ]
