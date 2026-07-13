"""Alert query and mapping service."""

from uuid import UUID

from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box
from app.normalization.geometry import wkt_element_to_geojson
from app.schemas.alert import AlertQueryParams, AlertResponse


def _alert_to_response(alert: Alert, include_raw: bool = False) -> AlertResponse:
    geometry = alert.geometry_json or wkt_element_to_geojson(alert.geometry)
    fields = {col.key: getattr(alert, col.key) for col in inspect(alert).mapper.column_attrs}
    fields.pop("geometry", None)
    fields["geometry"] = geometry
    if not include_raw:
        fields["raw_payload"] = None
    return AlertResponse.model_validate(fields)


def list_alerts(db: Session, params: AlertQueryParams) -> tuple[list[AlertResponse], int]:
    query = select(Alert)
    count_query = select(func.count()).select_from(Alert)

    if params.active is not None:
        query = query.where(Alert.is_active == params.active)
        count_query = count_query.where(Alert.is_active == params.active)
    if params.source:
        query = query.where(Alert.source == params.source)
        count_query = count_query.where(Alert.source == params.source)
    if params.country:
        query = query.where(Alert.country_code == params.country.upper())
        count_query = count_query.where(Alert.country_code == params.country.upper())
    if params.category:
        query = query.where(Alert.category == params.category)
        count_query = count_query.where(Alert.category == params.category)
    if params.severity:
        query = query.where(Alert.severity == params.severity)
        count_query = count_query.where(Alert.severity == params.severity)
    if params.issued_after:
        query = query.where(Alert.issued_at >= params.issued_after)
        count_query = count_query.where(Alert.issued_at >= params.issued_after)
    if params.issued_before:
        query = query.where(Alert.issued_at <= params.issued_before)
        count_query = count_query.where(Alert.issued_at <= params.issued_before)
    if params.bounding_box:
        try:
            bbox = parse_bounding_box(params.bounding_box)
        except BoundingBoxError:
            raise
        envelope = ST_MakeEnvelope(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, 4326)
        geo_filter = Alert.geometry.isnot(None) & ST_Intersects(Alert.geometry, envelope)
        query = query.where(geo_filter)
        count_query = count_query.where(geo_filter)

    total = db.scalar(count_query) or 0
    rows = (
        db.scalars(
            query.order_by(Alert.issued_at.desc()).limit(params.limit).offset(params.offset)
        ).all()
    )
    items = [_alert_to_response(row, include_raw=params.include_raw) for row in rows]
    return items, total


def get_alert(db: Session, alert_id: UUID, include_raw: bool = False) -> AlertResponse | None:
    alert = db.get(Alert, alert_id)
    if not alert:
        return None
    return _alert_to_response(alert, include_raw=include_raw)
