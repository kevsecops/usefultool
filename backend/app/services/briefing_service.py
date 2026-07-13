"""Briefing orchestration: generate and persist rule-based briefings."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.analysis.clustering import clusters_to_bonus_details, detect_hotspots
from app.analysis.risk_score import compute_global_risk_score
from app.analysis.rule_briefing import generate_rule_briefing
from app.analysis.trends import detect_trend_anomalies, global_rolling_avg
from app.models.alert import Alert
from app.models.briefing import Briefing
from app.normalization.datetime_utils import utc_now
from app.schemas.common import BriefingType


def generate_briefing(
    db: Session,
    *,
    briefing_type: str = "auto",
) -> Briefing:
    """Generate and persist a briefing. ``auto`` maps to rule_based until Phase 6 LLM."""
    if briefing_type == "auto":
        effective_type = BriefingType.RULE_BASED
    elif briefing_type in (BriefingType.RULE_BASED, BriefingType.LLM):
        effective_type = briefing_type
    else:
        effective_type = BriefingType.RULE_BASED

    # Phase 6: LLM path; for now always rule_based
    return _generate_rule_based_briefing(db)


def _generate_rule_based_briefing(db: Session) -> Briefing:
    now = utc_now()
    alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()

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
    content = generate_rule_briefing(
        alerts,
        risk=risk,
        hotspots=hotspots,
        anomalies=anomalies,
        generated_at=now,
    )

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
