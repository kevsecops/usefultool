"""Deterministic mock LLM provider for demo and tests."""

from __future__ import annotations

import json
from typing import Any

from app.analysis.clustering import HotspotCluster
from app.analysis.risk_score import RiskScoreResult
from app.analysis.rule_briefing import generate_rule_briefing
from app.analysis.trends import TrendAnomaly
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
        # Extract analysis input from user prompt
        start = user_prompt.find("<analysis_input>\n")
        end = user_prompt.find("\n</analysis_input>")
        if start == -1 or end == -1:
            raise ValueError("Mock provider: missing analysis_input in prompt")

        analysis_input = json.loads(user_prompt[start + len("<analysis_input>\n") : end])
        return _generate_mock_briefing(analysis_input)


def _generate_mock_briefing(analysis_input: dict[str, Any]) -> dict[str, Any]:
    """Build LLM-style briefing from structured input (deterministic)."""
    stats = analysis_input.get("stats", {})
    alerts_data = analysis_input.get("alerts", [])
    clusters = analysis_input.get("clusters", [])
    anomalies = analysis_input.get("trend_anomalies", [])
    valid_ids = set(analysis_input.get("valid_alert_ids", []))

    # Reconstruct minimal alert-like objects for rule_briefing helper logic
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

    # Transform to LLM briefing
    base["type"] = "llm"
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

    # Add cross-source correlation pattern if multiple sources present
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
