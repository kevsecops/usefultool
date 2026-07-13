"""Fire cluster convenience API — filters FIRMS active_fire_cluster observed events."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import DataSource, Severity
from app.schemas.observed_event import ObservedEventListResponse, ObservedEventQueryParams
from app.services.observed_event_service import list_observed_events

router = APIRouter(prefix="/api/v1/fire-clusters", tags=["fire-clusters"])


@router.get("", response_model=ObservedEventListResponse)
def get_fire_clusters(
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
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=str(exc)) from exc

    params = ObservedEventQueryParams(
        source=DataSource.FIRMS,
        event_type="active_fire_cluster",
        severity=severity,
        active=active,
        bounding_box=bounding_box,
        limit=limit,
        offset=offset,
        include_raw=include_raw,
    )
    items, total = list_observed_events(db, params)
    return ObservedEventListResponse(items=items, total=total, limit=limit, offset=offset)
