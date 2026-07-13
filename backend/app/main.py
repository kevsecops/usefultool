"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import SessionLocal
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.services.alert_fixture import deactivate_fixture_alerts
from app.services.ingest_service import deactivate_expired_alerts

setup_logging()
settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        expired = deactivate_expired_alerts(db)
        db.commit()
        if expired:
            logger.info("Startup: deactivated %d expired alerts", expired)
        if not settings.demo_mode:
            fixture_count = deactivate_fixture_alerts(db)
            db.commit()
            if fixture_count:
                logger.info(
                    "Startup: deactivated %d fixture-origin alerts (demo_mode=false)",
                    fixture_count,
                )
    except Exception:
        db.rollback()
        logger.exception("Startup expired-alert cleanup failed")
    finally:
        db.close()

    scheduler_task, stop_event = start_scheduler()
    yield
    await stop_scheduler(scheduler_task, stop_event)


app = FastAPI(
    title="Global Risk Intelligence API",
    version=settings.app_version,
    description="Aggregated public hazard alerts with LLM-powered cross-alert analysis.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(v1_router)
