"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import admin, alerts, briefings, sources, stats

router = APIRouter()
router.include_router(alerts.router)
router.include_router(sources.router)
router.include_router(stats.router)
router.include_router(briefings.router)
router.include_router(admin.router)
