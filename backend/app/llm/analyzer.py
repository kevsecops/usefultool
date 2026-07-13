"""LLM briefing generation with validation, retry, and fallback."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

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


class LLMAnalysisError(Exception):
    """Raised when LLM analysis fails after retry."""


def _collect_validation_errors(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def _validate_alert_references(content: dict[str, Any], valid_ids: set[str]) -> list[str]:
    """Ensure referenced alert IDs exist in the input."""
    errors: list[str] = []
    for aid in content.get("source_alert_ids", []):
        if aid not in valid_ids:
            errors.append(f"source_alert_ids contains unknown id: {aid}")

    for event in content.get("major_events", []):
        aid = event.get("alert_id")
        if aid and aid not in valid_ids:
            errors.append(f"major_events references unknown alert_id: {aid}")

    for pattern in content.get("cross_border_patterns", []):
        for aid in pattern.get("alert_ids", []):
            if aid not in valid_ids:
                errors.append(f"cross_border_patterns references unknown alert_id: {aid}")

    for region in content.get("affected_regions", []):
        for aid in region.get("alert_ids", []):
            if aid not in valid_ids:
                errors.append(f"affected_regions references unknown alert_id: {aid}")

    return errors


def validate_llm_output(
    raw: dict[str, Any],
    *,
    valid_ids: set[str],
    expected_risk_score: int,
) -> BriefingContent:
    """Validate and normalize LLM output."""
    raw = dict(raw)
    raw["type"] = "llm"
    raw.setdefault("overall_risk_score", expected_risk_score)
    raw.setdefault("score_breakdown", {})

    ref_errors = _validate_alert_references(raw, valid_ids)
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
) -> tuple[dict[str, Any], str]:
    """Generate LLM briefing content. Raises LLMAnalysisError on failure."""
    provider = provider or get_llm_provider()
    analysis_input = build_analysis_input(
        alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=anomalies,
        generated_at=generated_at,
    )
    valid_ids = set(analysis_input["valid_alert_ids"])
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
                correction = build_correction_prompt(last_error, last_output)
                raw = provider.complete_json(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=correction,
                    schema_hint=SCHEMA_HINT,
                )

            last_output = json.dumps(raw, ensure_ascii=False)[:2000]
            validated = validate_llm_output(
                raw,
                valid_ids=valid_ids,
                expected_risk_score=risk.global_score,
            )
            return validated.model_dump(), provider.model_name

        except (LLMProviderError, LLMAnalysisError, ValidationError) as exc:
            last_error = str(exc)
            logger.warning("LLM briefing attempt %d failed: %s", attempt + 1, last_error)

    raise LLMAnalysisError(f"LLM briefing failed after retry: {last_error}")
