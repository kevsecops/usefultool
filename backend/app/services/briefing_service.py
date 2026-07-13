"""Briefing orchestration: LLM analysis with rule-based fallback."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.analysis.clustering import clusters_to_bonus_details, detect_hotspots
from app.analysis.risk_score import compute_global_risk_score
from app.analysis.rule_briefing import generate_rule_briefing
from app.analysis.trends import detect_trend_anomalies, global_rolling_avg
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.analyzer import LLMAnalysisError, generate_llm_briefing_content
from app.models.alert import Alert
from app.models.briefing import Briefing
from app.normalization.datetime_utils import utc_now
from app.schemas.common import BriefingType

logger = get_logger(__name__)


def is_briefing_stale(briefing: Briefing, last_ingest: datetime | None) -> bool:
    """True when alerts were ingested after this briefing was generated."""
    if last_ingest is None:
        return False
    return briefing.generated_at < last_ingest


def _finalize_briefing_content(
    content: dict,
    *,
    risk,
    active_count: int,
) -> dict:
    """Ensure snapshot fields match computed analysis at generation time."""
    finalized = dict(content)
    finalized["active_count"] = active_count
    finalized["overall_risk_score"] = risk.global_score
    return finalized


def generate_briefing(
    db: Session,
    *,
    briefing_type: str = "auto",
) -> Briefing:
    """Generate and persist a briefing.

    ``auto`` uses LLM when ``LLM_ENABLED=true``, otherwise rule_based.
    Falls back to rule_based when LLM fails.
    """
    settings = get_settings()

    if briefing_type == "auto":
        use_llm = settings.llm_enabled
    elif briefing_type == BriefingType.LLM:
        use_llm = True
    elif briefing_type == BriefingType.RULE_BASED:
        use_llm = False
    else:
        use_llm = settings.llm_enabled

    if use_llm:
        try:
            return _generate_llm_briefing(db)
        except LLMAnalysisError as exc:
            logger.warning("LLM briefing failed, falling back to rule_based: %s", exc)
            return _generate_rule_based_briefing(db)

    return _generate_rule_based_briefing(db)


def _collect_analysis_context(db: Session, alerts: list[Alert], now):
    """Shared stats/hotspots/anomalies/risk computation."""
    hotspots = detect_hotspots(alerts)
    cluster_bonuses = clusters_to_bonus_details(hotspots)
    rolling_avg = global_rolling_avg(alerts, now=now)
    risk = compute_global_risk_score(
        alerts,
        now=now,
        cluster_bonuses=cluster_bonuses,
        rolling_avg_active=rolling_avg,
    )
    anomalies = detect_trend_anomalies(alerts, now=now)
    return hotspots, risk, anomalies


def _generate_llm_briefing(db: Session) -> Briefing:
    now = utc_now()
    alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    hotspots, risk, anomalies = _collect_analysis_context(db, alerts, now)

    content, llm_model = generate_llm_briefing_content(
        alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=anomalies,
        generated_at=now,
    )
    content = _finalize_briefing_content(content, risk=risk, active_count=len(alerts))

    source_ids = [uuid.UUID(aid) for aid in content["source_alert_ids"]]

    briefing = Briefing(
        generated_at=now,
        type=BriefingType.LLM,
        overall_risk_score=risk.global_score,
        overall_confidence=content["overall_confidence"],
        content=content,
        source_alert_ids=source_ids,
        llm_model=llm_model,
    )
    db.add(briefing)
    db.flush()
    db.refresh(briefing)
    return briefing


def _generate_rule_based_briefing(db: Session) -> Briefing:
    now = utc_now()
    alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    hotspots, risk, anomalies = _collect_analysis_context(db, alerts, now)
    content = generate_rule_briefing(
        alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=anomalies,
        generated_at=now,
    )
    content = _finalize_briefing_content(content, risk=risk, active_count=len(alerts))

    source_ids = [uuid.UUID(aid) for aid in content["source_alert_ids"]]

    briefing = Briefing(
        generated_at=now,
        type=BriefingType.RULE_BASED,
        overall_risk_score=risk.global_score,
        overall_confidence=content["overall_confidence"],
        content=content,
        source_alert_ids=source_ids,
        llm_model=None,
    )
    db.add(briefing)
    db.flush()
    db.refresh(briefing)
    return briefing


def get_latest_briefing(db: Session) -> Briefing | None:
    return db.scalar(select(Briefing).order_by(desc(Briefing.generated_at)).limit(1))


def list_briefings(db: Session, *, limit: int = 20, offset: int = 0) -> tuple[list[Briefing], int]:
    total = db.scalar(select(func.count()).select_from(Briefing)) or 0
    items = db.scalars(
        select(Briefing).order_by(desc(Briefing.generated_at)).offset(offset).limit(limit)
    ).all()
    return list(items), total
