"""Statistics service with rule-based analysis."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.clustering import detect_hotspots
from app.analysis.risk_score import compute_global_risk_score
from app.analysis.trends import detect_trend_anomalies
from app.services.risk_score_service import gather_risk_inputs
from app.core.config import get_settings
from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.ingest_run import IngestRun
from app.models.observed_event import ObservedEvent
from app.normalization.datetime_utils import utc_now
from app.schemas.stats import CountryCount, HotspotRegion, StatsResponse, TrendAnomalyItem
from app.services.alert_active import filter_effectively_active
from app.services.alert_fixture import is_fixture_alert


def get_stats(db: Session) -> StatsResponse:
    settings = get_settings()
    now = utc_now()
    db_alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    active_alerts = filter_effectively_active(db_alerts, now=now)
    if not settings.demo_mode:
        active_alerts = [alert for alert in active_alerts if not is_fixture_alert(alert)]

    by_country: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_source: Counter[str] = Counter()

    for alert in active_alerts:
        if alert.country_code:
            by_country[alert.country_code] += 1
        by_category[alert.category] += 1
        by_severity[alert.severity] += 1
        by_source[alert.source] += 1

    hotspots = detect_hotspots(active_alerts)
    risk_inputs = gather_risk_inputs(db, active_alerts)
    risk = compute_global_risk_score(inputs=risk_inputs, now=now)
    anomalies = detect_trend_anomalies(active_alerts, now=now)

    top_countries = [
        CountryCount(code=code, count=count)
        for code, count in by_country.most_common(10)
    ]
    hotspot_regions = [
        HotspotRegion(
            region=h.region,
            count=h.count,
            max_severity=h.max_severity,
            severe_or_extreme_count=h.severe_or_extreme_count,
        )
        for h in hotspots[:10]
    ]

    last_ingest = db.scalar(select(func.max(IngestRun.finished_at)))
    canonical_count = (
        db.scalar(
            select(func.count()).select_from(CanonicalEvent).where(CanonicalEvent.is_active.is_(True))
        )
        or 0
    )
    observed_count = (
        db.scalar(
            select(func.count()).select_from(ObservedEvent).where(ObservedEvent.is_active.is_(True))
        )
        or 0
    )

    return StatsResponse(
        active_count=len(active_alerts),
        global_risk_score=risk.global_score,
        score_breakdown=risk.breakdown,
        by_country=dict(by_country),
        by_category=dict(by_category),
        by_severity=dict(by_severity),
        by_source=dict(by_source),
        top_countries=top_countries,
        hotspot_regions=hotspot_regions,
        trend_anomalies=[
            TrendAnomalyItem(
                dimension=a.dimension,
                key=a.key,
                current_count=a.current_count,
                rolling_avg=a.rolling_avg,
                ratio=a.ratio,
            )
            for a in anomalies
        ],
        last_ingest=last_ingest,
        canonical_event_count=canonical_count,
        observed_event_count=observed_count,
    )
