"""Admin and ingest schemas."""

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    sources: list[str] | None = None
    force: bool = False


class IngestResponse(BaseModel):
    run_id: str
    status: str
    alerts_fetched: int
    alerts_created: int
    alerts_updated: int
    alerts_deactivated: int
    errors: list[dict] = Field(default_factory=list)
