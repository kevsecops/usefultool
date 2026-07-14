"""Implication candidate Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Confidence


class ImplicationCategory(StrEnum):
    LOGISTICS = "logistics"
    ECONOMY = "economy"
    INFRASTRUCTURE = "infrastructure"
    TECHNOLOGY = "technology"
    ENERGY = "energy"
    PUBLIC_HEALTH = "public_health"
    HUMANITARIAN = "humanitarian"
    FINANCE = "finance"


class EvidenceLevel(StrEnum):
    OBSERVED = "observed"
    OFFICIALLY_REPORTED = "officially_reported"
    INFERRED_FROM_EXPOSURE = "inferred_from_exposure"
    HYPOTHESIS = "hypothesis"


class GeneratedBy(StrEnum):
    RULE_BASED = "rule_based"
    LLM = "llm"


class ImplicationCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_event_id: UUID
    category: ImplicationCategory
    title: str
    description: str | None = None
    affected_region: str | None = None
    related_asset_ids: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)
    confidence: Confidence
    evidence_level: EvidenceLevel
    rationale: str | None = None
    missing_data: str | None = None
    generated_by: GeneratedBy
    created_at: datetime


class EventImplicationListResponse(BaseModel):
    event_id: UUID
    items: list[ImplicationCandidateResponse]
    total: int


class GenerateImplicationsRequest(BaseModel):
    event_id: UUID | None = None
    active_only: bool = True


class GenerateImplicationsResponse(BaseModel):
    events_processed: int
    implications_created: int
    implications_replaced: int
    engine_version: str


class ImplicationRef(BaseModel):
    """Briefing reference linking a statement to a persisted implication."""

    id: str
    text: str
    canonical_event_id: str | None = None
    evidence_level: str | None = None
