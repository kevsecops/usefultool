"""Canonical event query and mapping service."""

from uuid import UUID

from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, selectinload

from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.observed_event import ObservedEvent
from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box
from app.normalization.geometry import wkt_element_to_geojson
from app.schemas.canonical_event import (
    CanonicalEventMemberSummary,
    CanonicalEventQueryParams,
    CanonicalEventResponse,
    CanonicalEventSourcesResponse,
)


def _severity_rank(severity: str) -> int:
    return {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}.get(severity, 0)


def _member_summary(
    link: CanonicalEventLink,
    alert: Alert | None,
    observed: ObservedEvent | None,
) -> CanonicalEventMemberSummary:
    source = None
    title = None
    if link.member_type == "alert" and alert:
        source = alert.source
        title = alert.title
    elif link.member_type == "observed_event" and observed:
        source = observed.source
        title = observed.title

    return CanonicalEventMemberSummary(
        member_type=link.member_type,
        member_id=link.member_id,
        link_confidence=link.link_confidence,
        link_reason=link.link_reason,
        source=source,
        title=title,
    )


def _event_to_response(
    event: CanonicalEvent,
    alerts_by_id: dict[UUID, Alert] | None = None,
    observed_by_id: dict[UUID, ObservedEvent] | None = None,
) -> CanonicalEventResponse:
    geometry = event.geometry_json or wkt_element_to_geojson(event.geometry)
    fields = {col.key: getattr(event, col.key) for col in inspect(event).mapper.column_attrs}
    fields.pop("geometry", None)
    fields["geometry"] = geometry

    members: list[CanonicalEventMemberSummary] = []
    for link in event.links:
        alert = alerts_by_id.get(link.member_id) if alerts_by_id else None
        observed = observed_by_id.get(link.member_id) if observed_by_id else None
        members.append(_member_summary(link, alert, observed))

    fields["member_count"] = len(members)
    fields["members"] = members
    return CanonicalEventResponse.model_validate(fields)


def _load_member_maps(
    db: Session, links: list[CanonicalEventLink]
) -> tuple[dict[UUID, Alert], dict[UUID, ObservedEvent]]:
    alert_ids = [link.member_id for link in links if link.member_type == "alert"]
    observed_ids = [link.member_id for link in links if link.member_type == "observed_event"]

    alerts_by_id: dict[UUID, Alert] = {}
    observed_by_id: dict[UUID, ObservedEvent] = {}

    if alert_ids:
        alerts = db.scalars(select(Alert).where(Alert.id.in_(alert_ids))).all()
        alerts_by_id = {alert.id: alert for alert in alerts}
    if observed_ids:
        observed = db.scalars(select(ObservedEvent).where(ObservedEvent.id.in_(observed_ids))).all()
        observed_by_id = {event.id: event for event in observed}

    return alerts_by_id, observed_by_id


def list_canonical_events(
    db: Session, params: CanonicalEventQueryParams
) -> tuple[list[CanonicalEventResponse], int]:
    query = select(CanonicalEvent).options(selectinload(CanonicalEvent.links))
    count_query = select(func.count()).select_from(CanonicalEvent)

    if params.active is not None:
        query = query.where(CanonicalEvent.is_active == params.active)
        count_query = count_query.where(CanonicalEvent.is_active == params.active)
    if params.event_type:
        query = query.where(CanonicalEvent.event_type == params.event_type)
        count_query = count_query.where(CanonicalEvent.event_type == params.event_type)
    if params.severity:
        query = query.where(CanonicalEvent.severity == params.severity)
        count_query = count_query.where(CanonicalEvent.severity == params.severity)
    if params.status:
        query = query.where(CanonicalEvent.status == params.status)
        count_query = count_query.where(CanonicalEvent.status == params.status)
    if params.bounding_box:
        try:
            bbox = parse_bounding_box(params.bounding_box)
        except BoundingBoxError:
            raise
        envelope = ST_MakeEnvelope(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, 4326)
        geo_filter = CanonicalEvent.geometry.isnot(None) & ST_Intersects(
            CanonicalEvent.geometry, envelope
        )
        query = query.where(geo_filter)
        count_query = count_query.where(geo_filter)

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(CanonicalEvent.started_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()

    all_links = [link for row in rows for link in row.links]
    alerts_by_id, observed_by_id = _load_member_maps(db, all_links)

    items = [
        _event_to_response(row, alerts_by_id=alerts_by_id, observed_by_id=observed_by_id)
        for row in rows
    ]
    return items, total


def get_canonical_event(db: Session, event_id: UUID) -> CanonicalEventResponse | None:
    event = db.scalar(
        select(CanonicalEvent)
        .options(selectinload(CanonicalEvent.links))
        .where(CanonicalEvent.id == event_id)
    )
    if not event:
        return None
    alerts_by_id, observed_by_id = _load_member_maps(db, event.links)
    return _event_to_response(event, alerts_by_id=alerts_by_id, observed_by_id=observed_by_id)


def _serialize_alert(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "source": alert.source,
        "source_alert_id": alert.source_alert_id,
        "title": alert.title,
        "category": alert.category,
        "severity": alert.severity,
        "issued_at": alert.issued_at.isoformat(),
        "is_active": alert.is_active,
    }


def _serialize_observed_event(event: ObservedEvent) -> dict:
    return {
        "id": str(event.id),
        "source": event.source,
        "source_event_id": event.source_event_id,
        "title": event.title,
        "category": event.category,
        "severity": event.severity,
        "issued_at": event.issued_at.isoformat(),
        "is_active": event.is_active,
    }


def get_canonical_event_sources(
    db: Session, event_id: UUID
) -> CanonicalEventSourcesResponse | None:
    event = db.scalar(
        select(CanonicalEvent)
        .options(selectinload(CanonicalEvent.links))
        .where(CanonicalEvent.id == event_id)
    )
    if not event:
        return None

    alerts_by_id, observed_by_id = _load_member_maps(db, event.links)
    alerts = [
        _serialize_alert(alerts_by_id[link.member_id])
        for link in event.links
        if link.member_type == "alert" and link.member_id in alerts_by_id
    ]
    observed_events = [
        _serialize_observed_event(observed_by_id[link.member_id])
        for link in event.links
        if link.member_type == "observed_event" and link.member_id in observed_by_id
    ]

    return CanonicalEventSourcesResponse(
        canonical_event_id=event.id,
        alerts=alerts,
        observed_events=observed_events,
    )
