"""Observed events API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import Category, DataSource, Severity
from app.schemas.observed_event import (
    ObservedEventListResponse,
    ObservedEventQueryParams,
    ObservedEventResponse,
)
from app.services.observed_event_service import get_observed_event, list_observed_events

router = APIRouter(prefix="/api/v1/observed-events", tags=["observed-events"])


@router.get("", response_model=ObservedEventListResponse)
def get_observed_events(
    source: DataSource | None = None,
    category: Category | None = None,
    severity: Severity | None = None,
    active: bool = True,
    bounding_box: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_raw: bool = False,
    db: Session = Depends(get_db),
) -> ObservedEventListResponse:
    from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box

    if bounding_box:
        try:
            parse_bounding_box(bounding_box)
        except BoundingBoxError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    params = ObservedEventQueryParams(
        source=source,
        category=category,
        severity=severity,
        active=active,
        bounding_box=bounding_box,
        limit=limit,
        offset=offset,
        include_raw=include_raw,
    )
    items, total = list_observed_events(db, params)
    return ObservedEventListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{event_id}", response_model=ObservedEventResponse)
def get_observed_event_by_id(
    event_id: UUID,
    include_raw: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ObservedEventResponse:
    event = get_observed_event(db, event_id, include_raw=include_raw)
    if not event:
        raise HTTPException(status_code=404, detail="Observed event not found")
    return event
