"""Transparent global risk score v2 (0-100) with documented multi-factor weighting.

See docs/risk-scoring.md for the full specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.event_asset_exposure import EventAssetExposure
from app.models.exposure_asset import ExposureAsset
from app.models.implication_candidate import ImplicationCandidate

SCORE_VERSION = "2"

# --- Factor caps ---
EVENT_SEVERITY_CAP = 40
INFRASTRUCTURE_EXPOSURE_CAP = 30
MULTI_SOURCE_CAP = 15
HUMANITARIAN_IMPACT_CAP = 15

# --- Event severity (canonical events; alert fallback uses reduced weights) ---
EVENT_SEVERITY_WEIGHTS: dict[str, float] = {
    "minor": 2,
    "moderate": 6,
    "severe": 12,
    "extreme": 20,
    "unknown": 2,
}

ALERT_FALLBACK_SEVERITY_WEIGHTS: dict[str, float] = {
    "minor": 0.5,
    "moderate": 2,
    "severe": 5,
    "extreme": 8,
    "unknown": 0.5,
}

CONFIDENCE_MODIFIERS: dict[str, float] = {
    "low": 0.7,
    "medium": 1.0,
    "high": 1.2,
    "unknown": 1.0,
}

# --- Infrastructure exposure ---
ASSET_TYPE_WEIGHTS: dict[str, float] = {
    "port": 3,
    "airport": 2,
    "power_plant": 4,
}

IMPORTANCE_MODIFIERS: dict[str, float] = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
    "critical": 2.0,
}

EXPOSURE_TYPE_MODIFIERS: dict[str, float] = {
    "inside_event_area": 1.0,
    "near_event_area": 0.5,
    "system_level_exposure": 0.7,
    "unknown": 0.4,
}

EXPOSURE_CONFIDENCE_MODIFIERS: dict[str, float] = {
    "low": 0.7,
    "medium": 1.0,
    "high": 1.2,
}

# --- Humanitarian / impact implications ---
IMPACT_EVIDENCE_WEIGHTS: dict[str, float] = {
    "officially_reported": 5,
    "observed": 4,
    "inferred_from_exposure": 3,
    "hypothesis": 0,
}

IMPACT_CATEGORIES = frozenset({"humanitarian", "public_health", "infrastructure", "energy"})

SEVERITY_RANK = {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}


@dataclass
class RiskScoreResult:
    global_score: int
    raw_total: float
    trend_modifier: float = 1.0
    alert_scores: list = field(default_factory=list)
    cluster_bonuses: list = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskScoreInputs:
    alerts: list[Alert] = field(default_factory=list)
    canonical_events: list[CanonicalEvent] = field(default_factory=list)
    event_exposures: list[EventAssetExposure] = field(default_factory=list)
    implications: list[ImplicationCandidate] = field(default_factory=list)


def _diminishing_sum(scores: list[float], decay: float = 0.65) -> float:
    """Sum scores with exponential decay so additional events add less."""
    if not scores:
        return 0.0
    total = 0.0
    for idx, score in enumerate(scores):
        total += score * (decay**idx)
    return total


def _event_contribution(severity: str, confidence: str, *, use_alerts: bool = False) -> float:
    weights = ALERT_FALLBACK_SEVERITY_WEIGHTS if use_alerts else EVENT_SEVERITY_WEIGHTS
    base = weights.get(severity, weights["unknown"])
    conf_mod = CONFIDENCE_MODIFIERS.get(confidence, 1.0)
    return base * conf_mod


def compute_event_severity_index(
    canonical_events: list[CanonicalEvent],
    alerts: list[Alert],
) -> tuple[float, dict[str, Any]]:
    """Factor 1: Event Severity Index (0-40)."""
    if canonical_events:
        contributions = [
            _event_contribution(event.severity, event.confidence)
            for event in canonical_events
        ]
        source = "canonical_events"
        event_count = len(canonical_events)
    else:
        ranked_alerts = sorted(
            alerts,
            key=lambda a: (
                SEVERITY_RANK.get(a.severity, 0),
                a.issued_at,
            ),
            reverse=True,
        )
        contributions = [
            _event_contribution(a.severity, a.certainty or "medium", use_alerts=True)
            for a in ranked_alerts[:5]
        ]
        source = "alert_fallback"
        event_count = len(contributions)

    contributions.sort(reverse=True)
    raw = _diminishing_sum(contributions)
    # Reference: one extreme high-confidence event ≈ 24; three severe events ≈ ~28 raw
    reference_max = 28.0
    index = min(EVENT_SEVERITY_CAP, round(raw * EVENT_SEVERITY_CAP / reference_max))

    detail = {
        "source": source,
        "event_count": event_count,
        "raw_contribution": round(raw, 2),
        "top_contributions": [round(c, 2) for c in contributions[:5]],
        "index": index,
        "cap": EVENT_SEVERITY_CAP,
    }
    return float(index), detail


def compute_infrastructure_exposure_index(
    exposures: list[EventAssetExposure],
) -> tuple[float, dict[str, Any]]:
    """Factor 2: Infrastructure Exposure Index (0-30)."""
    if not exposures:
        return 0.0, {
            "exposure_count": 0,
            "unique_assets": 0,
            "raw_contribution": 0,
            "index": 0,
            "cap": INFRASTRUCTURE_EXPOSURE_CAP,
        }

    asset_scores: dict[str, float] = {}
    asset_details: list[dict[str, Any]] = []

    for exposure in exposures:
        asset: ExposureAsset | None = exposure.asset
        if asset is None:
            continue

        type_weight = ASSET_TYPE_WEIGHTS.get(asset.asset_type, 1)
        importance_mod = IMPORTANCE_MODIFIERS.get(asset.importance_level, 1.0)
        overlap_mod = (
            1.0
            if exposure.overlap
            else EXPOSURE_TYPE_MODIFIERS.get(exposure.exposure_type, 0.4)
        )
        conf_mod = EXPOSURE_CONFIDENCE_MODIFIERS.get(exposure.confidence, 1.0)
        score = type_weight * importance_mod * overlap_mod * conf_mod

        asset_key = str(asset.id)
        if score > asset_scores.get(asset_key, 0):
            asset_scores[asset_key] = score
            asset_details.append(
                {
                    "asset_id": asset_key,
                    "asset_name": asset.name,
                    "asset_type": asset.asset_type,
                    "importance_level": asset.importance_level,
                    "exposure_type": exposure.exposure_type,
                    "overlap": exposure.overlap,
                    "score": round(score, 2),
                }
            )

    ranked = sorted(asset_scores.values(), reverse=True)
    raw = _diminishing_sum(ranked, decay=0.6)
    # Reference: two critical ports inside event area ≈ 18 raw
    reference_max = 20.0
    index = min(INFRASTRUCTURE_EXPOSURE_CAP, round(raw * INFRASTRUCTURE_EXPOSURE_CAP / reference_max))

    detail = {
        "exposure_count": len(exposures),
        "unique_assets": len(asset_scores),
        "raw_contribution": round(raw, 2),
        "top_assets": sorted(asset_details, key=lambda d: d["score"], reverse=True)[:5],
        "index": index,
        "cap": INFRASTRUCTURE_EXPOSURE_CAP,
    }
    return float(index), detail


def compute_multi_source_corroboration(
    canonical_events: list[CanonicalEvent],
) -> tuple[float, dict[str, Any]]:
    """Factor 3: Multi-Source Corroboration (0-15)."""
    if not canonical_events:
        return 0.0, {
            "corroborated_events": 0,
            "index": 0,
            "cap": MULTI_SOURCE_CAP,
            "events": [],
        }

    event_details: list[dict[str, Any]] = []
    total_bonus = 0.0

    for event in canonical_events:
        sources: set[str] = set()
        for link in event.links or []:
            sources.add(f"{link.member_type}:{link.member_id}")

        source_count = len(sources)
        if source_count < 2:
            continue

        bonus = min(5.0, (source_count - 1) * 2.0)
        total_bonus += bonus
        event_details.append(
            {
                "event_id": str(event.id),
                "title": event.title,
                "source_count": source_count,
                "bonus": round(bonus, 2),
            }
        )

    index = min(MULTI_SOURCE_CAP, round(total_bonus))

    detail = {
        "corroborated_events": len(event_details),
        "raw_contribution": round(total_bonus, 2),
        "events": event_details,
        "index": index,
        "cap": MULTI_SOURCE_CAP,
    }
    return float(index), detail


def compute_humanitarian_impact_signal(
    implications: list[ImplicationCandidate],
    canonical_events: list[CanonicalEvent],
) -> tuple[float, dict[str, Any]]:
    """Factor 4: Humanitarian/Impact Signal (0-15)."""
    if not implications:
        return 0.0, {
            "qualifying_implications": 0,
            "raw_contribution": 0,
            "index": 0,
            "cap": HUMANITARIAN_IMPACT_CAP,
            "implications": [],
        }

    severity_by_event = {str(e.id): e.severity for e in canonical_events}
    implication_scores: list[float] = []
    implication_details: list[dict[str, Any]] = []

    for impl in implications:
        evidence_weight = IMPACT_EVIDENCE_WEIGHTS.get(impl.evidence_level, 0)
        if evidence_weight <= 0:
            continue

        conf_mod = CONFIDENCE_MODIFIERS.get(impl.confidence, 1.0)
        category_mod = 1.5 if impl.category in IMPACT_CATEGORIES else 1.0
        event_severity = severity_by_event.get(str(impl.canonical_event_id), "moderate")
        severity_mod = 1.0 + SEVERITY_RANK.get(event_severity, 0) * 0.1

        score = evidence_weight * conf_mod * category_mod * severity_mod
        implication_scores.append(score)
        implication_details.append(
            {
                "implication_id": str(impl.id),
                "title": impl.title,
                "category": impl.category,
                "evidence_level": impl.evidence_level,
                "confidence": impl.confidence,
                "score": round(score, 2),
            }
        )

    implication_scores.sort(reverse=True)
    raw = _diminishing_sum(implication_scores, decay=0.7)
    reference_max = 12.0
    index = min(HUMANITARIAN_IMPACT_CAP, round(raw * HUMANITARIAN_IMPACT_CAP / reference_max))

    detail = {
        "qualifying_implications": len(implication_details),
        "raw_contribution": round(raw, 2),
        "top_implications": sorted(implication_details, key=lambda d: d["score"], reverse=True)[:5],
        "index": index,
        "cap": HUMANITARIAN_IMPACT_CAP,
    }
    return float(index), detail


def compute_global_risk_score(
    alerts: list[Alert] | None = None,
    *,
    canonical_events: list[CanonicalEvent] | None = None,
    event_exposures: list[EventAssetExposure] | None = None,
    implications: list[ImplicationCandidate] | None = None,
    inputs: RiskScoreInputs | None = None,
    now: datetime | None = None,
    # Legacy kwargs — ignored in v2, kept for call-site compatibility during migration
    cluster_bonuses: list | None = None,
    trend_modifier: float | None = None,
    rolling_avg_active: float | None = None,
) -> RiskScoreResult:
    """Compute normalized global risk score (0-100) with transparent v2 breakdown."""
    del cluster_bonuses, trend_modifier, rolling_avg_active
    now = now or datetime.now(UTC)

    if inputs is not None:
        alerts = inputs.alerts
        canonical_events = inputs.canonical_events
        event_exposures = inputs.event_exposures
        implications = inputs.implications

    alerts = alerts or []
    canonical_events = canonical_events or []
    event_exposures = event_exposures or []
    implications = implications or []

    event_idx, event_detail = compute_event_severity_index(canonical_events, alerts)
    infra_idx, infra_detail = compute_infrastructure_exposure_index(event_exposures)
    corroboration_idx, corroboration_detail = compute_multi_source_corroboration(canonical_events)
    impact_idx, impact_detail = compute_humanitarian_impact_signal(implications, canonical_events)

    raw_total = event_idx + infra_idx + corroboration_idx + impact_idx
    global_score = min(100, round(raw_total))

    breakdown: dict[str, Any] = {
        "version": SCORE_VERSION,
        "computed_at": now.isoformat(),
        "event_severity_index": event_detail,
        "infrastructure_exposure_index": infra_detail,
        "multi_source_corroboration": corroboration_detail,
        "humanitarian_impact_signal": impact_detail,
        "factor_totals": {
            "event_severity": event_idx,
            "infrastructure_exposure": infra_idx,
            "multi_source_corroboration": corroboration_idx,
            "humanitarian_impact": impact_idx,
        },
        "raw_total": round(raw_total, 2),
        "active_alert_count": len(alerts),
        "canonical_event_count": len(canonical_events),
    }

    return RiskScoreResult(
        global_score=global_score,
        raw_total=raw_total,
        breakdown=breakdown,
    )
