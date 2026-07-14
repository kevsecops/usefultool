"""Admin API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import verify_admin_token
from app.schemas.admin import IngestRequest, IngestResponse
from app.schemas.briefing import GenerateBriefingRequest, GenerateBriefingResponse
from app.schemas.canonical_event import CorrelateEventsResponse
from app.schemas.exposure import CalculateExposureRequest, CalculateExposureResponse
from app.schemas.implication import GenerateImplicationsRequest, GenerateImplicationsResponse
from app.services.briefing_service import generate_briefing
from app.services.correlation_service import run_correlation
from app.services.exposure_service import run_calculate_exposure
from app.services.implication_service import run_generate_implications
from app.services.ingest_service import run_ingest
from app.services.status_service import get_admin_status

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/status", dependencies=[Depends(verify_admin_token)])
async def admin_status(db: Session = Depends(get_db)) -> dict:
    return await get_admin_status(db)


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(verify_admin_token)])
async def trigger_ingest(
    request: IngestRequest | None = None,
    db: Session = Depends(get_db),
) -> IngestResponse:
    req = request or IngestRequest()
    run = await run_ingest(db, sources=req.sources, generate_briefing=req.generate_briefing)
    db.commit()
    return IngestResponse(
        run_id=str(run.id),
        status=run.status,
        alerts_fetched=run.alerts_fetched,
        alerts_created=run.alerts_created,
        alerts_updated=run.alerts_updated,
        alerts_deactivated=run.alerts_deactivated,
        errors=run.errors or [],
    )


@router.post(
    "/correlate-events",
    response_model=CorrelateEventsResponse,
    dependencies=[Depends(verify_admin_token)],
)
def trigger_correlate_events(db: Session = Depends(get_db)) -> CorrelateEventsResponse:
    result = run_correlation(db)
    db.commit()
    return result


@router.post(
    "/generate-briefing",
    response_model=GenerateBriefingResponse,
    dependencies=[Depends(verify_admin_token)],
)
def trigger_generate_briefing(
    request: GenerateBriefingRequest | None = None,
    db: Session = Depends(get_db),
) -> GenerateBriefingResponse:
    req = request or GenerateBriefingRequest()
    briefing = generate_briefing(db, briefing_type=req.type)
    db.commit()
    return GenerateBriefingResponse(
        briefing_id=str(briefing.id),
        type=briefing.type,
        overall_risk_score=briefing.overall_risk_score,
        generated_at=briefing.generated_at,
    )


@router.post(
    "/calculate-exposure",
    response_model=CalculateExposureResponse,
    dependencies=[Depends(verify_admin_token)],
)
def trigger_calculate_exposure(
    request: CalculateExposureRequest | None = None,
    db: Session = Depends(get_db),
) -> CalculateExposureResponse:
    req = request or CalculateExposureRequest()
    result = run_calculate_exposure(
        db,
        event_id=req.event_id,
        active_only=req.active_only,
    )
    db.commit()
    return result


@router.post(
    "/generate-implications",
    response_model=GenerateImplicationsResponse,
    dependencies=[Depends(verify_admin_token)],
)
def trigger_generate_implications(
    request: GenerateImplicationsRequest | None = None,
    db: Session = Depends(get_db),
) -> GenerateImplicationsResponse:
    req = request or GenerateImplicationsRequest()
    result = run_generate_implications(
        db,
        event_id=req.event_id,
        active_only=req.active_only,
    )
    db.commit()
    return result
