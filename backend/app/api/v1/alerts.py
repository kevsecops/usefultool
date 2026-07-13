"""Alerts API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.alert import AlertListResponse, AlertQueryParams, AlertResponse
from app.schemas.common import AlertSource, Category, Severity
from app.services.alert_service import get_alert, list_alerts

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
def get_alerts(
    source: AlertSource | None = None,
    country: str | None = None,
    category: Category | None = None,
    severity: Severity | None = None,
    active: bool = True,
    issued_after: str | None = None,
    issued_before: str | None = None,
    bounding_box: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_raw: bool = False,
    db: Session = Depends(get_db),
) -> AlertListResponse:
    from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box
    from app.normalization.datetime_utils import parse_datetime

    if bounding_box:
        try:
            parse_bounding_box(bounding_box)
        except BoundingBoxError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    params = AlertQueryParams(
        source=source,
        country=country,
        category=category,
        severity=severity,
        active=active,
        issued_after=parse_datetime(issued_after) if issued_after else None,
        issued_before=parse_datetime(issued_before) if issued_before else None,
        bounding_box=bounding_box,
        limit=limit,
        offset=offset,
        include_raw=include_raw,
    )
    items, total = list_alerts(db, params)
    return AlertListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert_by_id(
    alert_id: UUID,
    include_raw: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> AlertResponse:
    alert = get_alert(db, alert_id, include_raw=include_raw)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
