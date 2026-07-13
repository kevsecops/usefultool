"""Source health schemas."""

from datetime import datetime

from pydantic import BaseModel


class SourceInfo(BaseModel):
    id: str
    name: str
    healthy: bool
    last_fetch: datetime | None = None


class SourcesResponse(BaseModel):
    sources: list[SourceInfo]
