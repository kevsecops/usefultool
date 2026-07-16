"""LLM briefing generation with validation, retry, and fallback."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.analysis.clustering import HotspotCluster
from app.analysis.risk_score import RiskScoreResult
from app.analysis.trends import TrendAnomaly
from app.core.logging import get_logger
from app.llm.input_builder import build_analysis_input
from app.llm.openai_compat import LLMProviderError
from app.llm.prompts import SYSTEM_PROMPT, build_correction_prompt, build_user_prompt
from app.llm.provider import LLMProvider, get_llm_provider
from app.models.alert import Alert
from app.schemas.briefing import BriefingContent

logger = get_logger(__name__)

SCHEMA_HINT = BriefingContent.model_json_schema()

_SECTIONS_WITH_SOURCE_IDS = (
    "cross_border_patterns",
    "cross_border_relevance",
    "technology_infrastructure_risks",
    "confirmed_impacts",
    "affected_regions",
    "major_events",
)


class LLMAnalysisError(Exception):
    """Raised when LLM analysis fails after retry."""


def _collect_validation_errors(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def _validate_alert_references(
    content: dict[str, Any],
    valid_ids: set[str],
    *,
    valid_source_ids: set[str] | None = None,
) -> list[str]:
    """Ensure referenced alert/source IDs exist in the input."""
    errors: list[str] = []
    source_ids = valid_source_ids or valid_ids

    for aid in content.get("source_alert_ids", []):
        if aid not in valid_ids:
            errors.append(f"source_alert_ids contains unknown id: {aid}")

    for event in content.get("major_events", []):
        aid = event.get("alert_id")
        if aid and aid not in valid_ids:
            errors.append(f"major_events references unknown alert_id: {aid}")

    for pattern in content.get("cross_border_patterns", []):
        for aid in pattern.get("alert_ids", []):
            if aid not in source_ids:
                errors.append(f"cross_border_patterns references unknown alert_id: {aid}")

    for region in content.get("affected_regions", []):
        for aid in region.get("alert_ids", []):
            if aid not in valid_ids:
                errors.append(f"affected_regions references unknown alert_id: {aid}")

    return errors


def _validate_source_ids(content: dict[str, Any], valid_source_ids: set[str]) -> list[str]:
    """Ensure source_ids in extended sections reference evidence package IDs."""
    errors: list[str] = []

    for section_key in ("cross_border_relevance", "technology_infrastructure_risks", "confirmed_impacts"):
        for item in content.get(section_key, []):
            for sid in item.get("source_ids", []):
                if sid not in valid_source_ids:
                    errors.append(f"{section_key} references unknown source_id: {sid}")

    observed = content.get("observed_events", {})
    for item in observed.get("items", []):
        for sid in item.get("source_ids", []):
            if sid not in valid_source_ids:
                errors.append(f"observed_events references unknown source_id: {sid}")

    verified = content.get("verified_exposure", {})
    for item in verified.get("items", []):
        for sid in item.get("source_ids", []):
            if sid not in valid_source_ids:
                errors.append(f"verified_exposure references unknown source_id: {sid}")

    return errors


def validate_llm_output(
    raw: dict[str, Any],
    *,
    valid_ids: set[str],
    valid_source_ids: set[str] | None = None,
    expected_risk_score: int,
) -> BriefingContent:
    """Validate and normalize LLM output."""
    raw = dict(raw)
    raw["type"] = "llm"
    raw.setdefault("overall_risk_score", expected_risk_score)
    raw.setdefault("score_breakdown", {})
    raw.setdefault("observed_events", {"summary": "", "items": [], "confidence": "low"})
    raw.setdefault("verified_exposure", {"summary": "", "items": [], "confidence": "low"})
    raw.setdefault("confirmed_impacts", [])
    raw.setdefault("cross_border_relevance", [])
    raw.setdefault("technology_infrastructure_risks", [])
    raw.setdefault("evidence_gaps", [])
    raw.setdefault("section_confidence", {})

    source_ids = valid_source_ids or valid_ids
    source_ids = valid_source_ids or valid_ids
    ref_errors = _validate_alert_references(raw, valid_ids, valid_source_ids=source_ids)
    ref_errors.extend(_validate_source_ids(raw, source_ids))
    if ref_errors:
        raise LLMAnalysisError("; ".join(ref_errors))

    try:
        return BriefingContent.model_validate(raw)
    except ValidationError as exc:
        raise LLMAnalysisError(_collect_validation_errors(exc)) from exc


def generate_llm_briefing_content(
    alerts: list[Alert],
    *,
    risk: RiskScoreResult,
    hotspots: list[HotspotCluster],
    anomalies: list[TrendAnomaly],
    generated_at,
    provider: LLMProvider | None = None,
    db: Session | None = None,
) -> tuple[dict[str, Any], str]:
    """Generate LLM briefing content. Raises LLMAnalysisError on failure."""
    provider = provider or get_llm_provider()
    analysis_input = build_analysis_input(
        alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=anomalies,
        generated_at=generated_at,
        db=db,
    )
    valid_ids = set(analysis_input.get("valid_alert_ids", []))
    valid_source_ids = set(analysis_input.get("valid_source_ids", [])) | valid_ids
    user_prompt = build_user_prompt(analysis_input)

    last_error = ""
    last_output = ""

    for attempt in range(2):
        try:
            if attempt == 0:
                raw = provider.complete_json(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    schema_hint=SCHEMA_HINT,
                )
            else:
                correction = build_correction_prompt(
                    last_error,
                    last_output,
                    original_user_prompt=user_prompt,
                )
                raw = provider.complete_json(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=correction,
                    schema_hint=SCHEMA_HINT,
                )

            last_output = json.dumps(raw, ensure_ascii=False)[:2000]
            validated = validate_llm_output(
                raw,
                valid_ids=valid_ids,
                valid_source_ids=valid_source_ids,
                expected_risk_score=risk.global_score,
            )
            return validated.model_dump(), provider.model_name

        except (LLMProviderError, LLMAnalysisError, ValidationError) as exc:
            last_error = str(exc)
            logger.warning("LLM briefing attempt %d failed: %s", attempt + 1, last_error)

    raise LLMAnalysisError(f"LLM briefing failed after retry: {last_error}")
