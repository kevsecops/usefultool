"""Statistics service with rule-based analysis."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.clustering import clusters_to_bonus_details, detect_hotspots
from app.analysis.risk_score import compute_global_risk_score
from app.analysis.trends import detect_trend_anomalies, global_rolling_avg
from app.models.alert import Alert
from app.models.ingest_run import IngestRun
from app.normalization.datetime_utils import utc_now
from app.schemas.stats import CountryCount, HotspotRegion, StatsResponse, TrendAnomalyItem


def get_stats(db: Session) -> StatsResponse:
    active_alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    now = utc_now()

    by_country: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()

    for alert in active_alerts:
        if alert.country_code:
            by_country[alert.country_code] += 1
        by_category[alert.category] += 1
        by_severity[alert.severity] += 1

    hotspots = detect_hotspots(active_alerts)
    cluster_bonuses = clusters_to_bonus_details(hotspots)
    rolling_avg = global_rolling_avg(active_alerts, now=now)
    risk = compute_global_risk_score(
        active_alerts,
        now=now,
        cluster_bonuses=cluster_bonuses,
        rolling_avg_active=rolling_avg,
    )
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

    return StatsResponse(
        active_count=len(active_alerts),
        global_risk_score=risk.global_score,
        score_breakdown=risk.breakdown,
        by_country=dict(by_country),
        by_category=dict(by_category),
        by_severity=dict(by_severity),
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
    )
