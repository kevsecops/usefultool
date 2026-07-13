"""Briefing API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.briefing import BriefingListResponse, BriefingResponse
from app.services.briefing_service import get_latest_briefing, list_briefings, prepare_briefing_for_response

router = APIRouter(prefix="/api/v1/briefings", tags=["briefings"])


def _to_response(briefing, db: Session) -> BriefingResponse:
    briefing = prepare_briefing_for_response(db, briefing)
    return BriefingResponse(
        id=briefing.id,
        generated_at=briefing.generated_at,
        type=briefing.type,
        overall_risk_score=briefing.overall_risk_score,
        overall_confidence=briefing.overall_confidence,
        content=briefing.content,
        source_alert_ids=briefing.source_alert_ids or [],
        llm_model=briefing.llm_model,
    )


@router.get("/latest", response_model=BriefingResponse)
def read_latest_briefing(db: Session = Depends(get_db)) -> BriefingResponse:
    briefing = get_latest_briefing(db)
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing generated yet")
    return _to_response(briefing, db)


@router.get("", response_model=BriefingListResponse)
def read_briefings(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> BriefingListResponse:
    items, total = list_briefings(db, limit=limit, offset=offset)
    return BriefingListResponse(
        items=[_to_response(b, db) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )
