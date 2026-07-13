"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import admin, alerts, briefings, events, fire_clusters, observed_events, sources, space_weather, stats

router = APIRouter()
router.include_router(alerts.router)
router.include_router(observed_events.router)
router.include_router(events.router)
router.include_router(space_weather.router)
router.include_router(fire_clusters.router)
router.include_router(sources.router)
router.include_router(stats.router)
router.include_router(briefings.router)
router.include_router(admin.router)
