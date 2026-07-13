"""Admin API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import verify_admin_token
from app.schemas.admin import IngestRequest, IngestResponse
from app.services.ingest_service import run_ingest

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(verify_admin_token)])
async def trigger_ingest(
    request: IngestRequest | None = None,
    db: Session = Depends(get_db),
) -> IngestResponse:
    req = request or IngestRequest()
    run = await run_ingest(db, sources=req.sources)
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
