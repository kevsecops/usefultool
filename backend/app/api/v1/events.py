"""Canonical events API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.canonical_event import (
    CanonicalEventListResponse,
    CanonicalEventQueryParams,
    CanonicalEventResponse,
    CanonicalEventSourcesResponse,
)
from app.schemas.common import Severity
from app.services.canonical_event_service import (
    get_canonical_event,
    get_canonical_event_sources,
    list_canonical_events,
)

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=CanonicalEventListResponse)
def get_events(
    event_type: str | None = None,
    severity: Severity | None = None,
    status: str | None = None,
    active: bool = True,
    bounding_box: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CanonicalEventListResponse:
    from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box

    if bounding_box:
        try:
            parse_bounding_box(bounding_box)
        except BoundingBoxError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    params = CanonicalEventQueryParams(
        event_type=event_type,
        severity=severity,
        status=status,
        active=active,
        bounding_box=bounding_box,
        limit=limit,
        offset=offset,
    )
    items, total = list_canonical_events(db, params)
    return CanonicalEventListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{event_id}", response_model=CanonicalEventResponse)
def get_event_by_id(
    event_id: UUID,
    db: Session = Depends(get_db),
) -> CanonicalEventResponse:
    event = get_canonical_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Canonical event not found")
    return event


@router.get("/{event_id}/sources", response_model=CanonicalEventSourcesResponse)
def get_event_sources(
    event_id: UUID,
    db: Session = Depends(get_db),
) -> CanonicalEventSourcesResponse:
    sources = get_canonical_event_sources(db, event_id)
    if not sources:
        raise HTTPException(status_code=404, detail="Canonical event not found")
    return sources
