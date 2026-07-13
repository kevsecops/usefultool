"""Statistics service."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.ingest_run import IngestRun
from app.schemas.stats import CountryCount, HotspotRegion, StatsResponse


def get_stats(db: Session) -> StatsResponse:
    active_alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()

    by_country: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_region: Counter[str] = Counter()

    for alert in active_alerts:
        if alert.country_code:
            by_country[alert.country_code] += 1
        by_category[alert.category] += 1
        by_severity[alert.severity] += 1
        if alert.region and alert.country_code:
            by_region[f"{alert.region}, {alert.country_code}"] += 1
        elif alert.location_name:
            by_region[alert.location_name] += 1

    top_countries = [
        CountryCount(code=code, count=count)
        for code, count in by_country.most_common(10)
    ]
    hotspot_regions = [
        HotspotRegion(region=region, count=count)
        for region, count in by_region.most_common(10)
    ]

    last_ingest = db.scalar(select(func.max(IngestRun.finished_at)))

    return StatsResponse(
        active_count=len(active_alerts),
        global_risk_score=0,
        score_breakdown={},
        by_country=dict(by_country),
        by_category=dict(by_category),
        by_severity=dict(by_severity),
        top_countries=top_countries,
        hotspot_regions=hotspot_regions,
        last_ingest=last_ingest,
    )
