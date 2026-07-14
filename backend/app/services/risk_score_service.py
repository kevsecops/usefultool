"""Load multi-factor inputs for global risk score v2."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.risk_score import RiskScoreInputs
from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.event_asset_exposure import EventAssetExposure
from app.models.implication_candidate import ImplicationCandidate


def gather_risk_inputs(db: Session, alerts: list[Alert]) -> RiskScoreInputs:
    """Collect canonical events, exposures, and implications for risk scoring."""
    canonical_events = list(
        db.scalars(
            select(CanonicalEvent)
            .options(selectinload(CanonicalEvent.links))
            .where(CanonicalEvent.is_active.is_(True))
        ).all()
    )

    active_event_ids = {event.id for event in canonical_events}

    if active_event_ids:
        event_exposures = list(
            db.scalars(
                select(EventAssetExposure)
                .options(selectinload(EventAssetExposure.asset))
                .where(EventAssetExposure.event_id.in_(active_event_ids))
            ).all()
        )
    else:
        event_exposures = []

    implications = list(db.scalars(select(ImplicationCandidate)).all())

    return RiskScoreInputs(
        alerts=alerts,
        canonical_events=canonical_events,
        event_exposures=event_exposures,
        implications=implications,
    )
