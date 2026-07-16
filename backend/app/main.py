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
from app.services.startup_service import run_startup_pipeline

setup_logging()
settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        await run_startup_pipeline(db)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Startup pipeline failed")
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
