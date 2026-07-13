"""Observed event query and mapping service."""

from uuid import UUID

from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.observed_event import ObservedEvent
from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box
from app.normalization.geometry import wkt_element_to_geojson
from app.schemas.observed_event import ObservedEventQueryParams, ObservedEventResponse


def _extract_ingest_mode(event: ObservedEvent) -> str:
    payload = event.raw_payload or {}
    if isinstance(payload, dict) and payload.get("_ingest_mode"):
        return str(payload["_ingest_mode"])
    meta = event.source_metadata or {}
    if isinstance(meta, dict) and meta.get("_ingest_mode"):
        return str(meta["_ingest_mode"])
    return "live"


def _event_to_response(event: ObservedEvent, include_raw: bool = False) -> ObservedEventResponse:
    geometry = event.geometry_json or wkt_element_to_geojson(event.geometry)
    fields = {col.key: getattr(event, col.key) for col in inspect(event).mapper.column_attrs}
    fields.pop("geometry", None)
    fields["geometry"] = geometry
    fields["ingest_mode"] = _extract_ingest_mode(event)
    if not include_raw:
        fields["raw_payload"] = None
    return ObservedEventResponse.model_validate(fields)


def list_observed_events(
    db: Session, params: ObservedEventQueryParams
) -> tuple[list[ObservedEventResponse], int]:
    query = select(ObservedEvent)
    count_query = select(func.count()).select_from(ObservedEvent)

    if params.active is not None:
        query = query.where(ObservedEvent.is_active == params.active)
        count_query = count_query.where(ObservedEvent.is_active == params.active)
    if params.source:
        query = query.where(ObservedEvent.source == params.source)
        count_query = count_query.where(ObservedEvent.source == params.source)
    if params.event_type:
        query = query.where(ObservedEvent.event_type == params.event_type)
        count_query = count_query.where(ObservedEvent.event_type == params.event_type)
    if params.category:
        query = query.where(ObservedEvent.category == params.category)
        count_query = count_query.where(ObservedEvent.category == params.category)
    if params.severity:
        query = query.where(ObservedEvent.severity == params.severity)
        count_query = count_query.where(ObservedEvent.severity == params.severity)
    if params.bounding_box:
        try:
            bbox = parse_bounding_box(params.bounding_box)
        except BoundingBoxError:
            raise
        envelope = ST_MakeEnvelope(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, 4326)
        geo_filter = ObservedEvent.geometry.isnot(None) & ST_Intersects(
            ObservedEvent.geometry, envelope
        )
        query = query.where(geo_filter)
        count_query = count_query.where(geo_filter)

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(ObservedEvent.issued_at.desc()).limit(params.limit).offset(params.offset)
    ).all()
    items = [_event_to_response(row, include_raw=params.include_raw) for row in rows]
    return items, total


def get_observed_event(
    db: Session, event_id: UUID, include_raw: bool = False
) -> ObservedEventResponse | None:
    event = db.get(ObservedEvent, event_id)
    if not event:
        return None
    return _event_to_response(event, include_raw=include_raw)
