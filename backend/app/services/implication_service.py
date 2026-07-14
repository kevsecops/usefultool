"""Implication generation, persistence, and query service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, selectinload

from app.analysis.implications import ENGINE_VERSION, ImplicationDraft, generate_implications_for_event
from app.models.canonical_event import CanonicalEvent
from app.models.implication_candidate import ImplicationCandidate
from app.normalization.datetime_utils import utc_now
from app.schemas.implication import (
    EventImplicationListResponse,
    GenerateImplicationsResponse,
    ImplicationCandidateResponse,
)


@dataclass
class GenerateStats:
    events_processed: int = 0
    implications_created: int = 0
    implications_replaced: int = 0


def _draft_to_model(
    event_id: uuid.UUID,
    draft: ImplicationDraft,
    *,
    created_at,
) -> ImplicationCandidate:
    return ImplicationCandidate(
        canonical_event_id=event_id,
        category=draft.category,
        title=draft.title,
        description=draft.description,
        affected_region=draft.affected_region,
        related_asset_ids=[str(aid) for aid in draft.related_asset_ids],
        supporting_source_ids=draft.supporting_source_ids,
        confidence=draft.confidence,
        evidence_level=draft.evidence_level,
        rationale=draft.rationale,
        missing_data=draft.missing_data,
        generated_by=draft.generated_by,
        created_at=created_at,
    )


def _to_response(candidate: ImplicationCandidate) -> ImplicationCandidateResponse:
    fields = {
        col.key: getattr(candidate, col.key) for col in inspect(candidate).mapper.column_attrs
    }
    return ImplicationCandidateResponse.model_validate(fields)


def generate_implications_for_event_id(
    db: Session,
    event_id: uuid.UUID,
) -> tuple[int, int]:
    """Generate and persist implications for one event. Returns (created, replaced)."""
    event = db.scalar(
        select(CanonicalEvent)
        .options(selectinload(CanonicalEvent.links))
        .where(CanonicalEvent.id == event_id)
    )
    if not event:
        return 0, 0

    drafts = generate_implications_for_event(db, event)
    now = utc_now()

    existing = list(
        db.scalars(
            select(ImplicationCandidate).where(
                ImplicationCandidate.canonical_event_id == event_id,
                ImplicationCandidate.generated_by == "rule_based",
            )
        ).all()
    )
    replaced = len(existing)
    for row in existing:
        db.delete(row)

    created = 0
    for draft in drafts:
        db.add(_draft_to_model(event_id, draft, created_at=now))
        created += 1

    db.flush()
    return created, replaced


def run_generate_implications(
    db: Session,
    *,
    event_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> GenerateImplicationsResponse:
    """Generate implications for one or all canonical events."""
    stats = GenerateStats()

    if event_id:
        event_ids = [event_id]
    else:
        query = select(CanonicalEvent.id)
        if active_only:
            query = query.where(CanonicalEvent.is_active.is_(True))
        event_ids = list(db.scalars(query).all())

    for eid in event_ids:
        if not db.get(CanonicalEvent, eid):
            continue
        created, replaced = generate_implications_for_event_id(db, eid)
        stats.events_processed += 1
        stats.implications_created += created
        stats.implications_replaced += replaced

    return GenerateImplicationsResponse(
        events_processed=stats.events_processed,
        implications_created=stats.implications_created,
        implications_replaced=stats.implications_replaced,
        engine_version=ENGINE_VERSION,
    )


def list_event_implications(
    db: Session,
    event_id: uuid.UUID,
) -> EventImplicationListResponse | None:
    event = db.get(CanonicalEvent, event_id)
    if not event:
        return None

    rows = db.scalars(
        select(ImplicationCandidate)
        .where(ImplicationCandidate.canonical_event_id == event_id)
        .order_by(ImplicationCandidate.confidence.desc(), ImplicationCandidate.created_at.desc())
    ).all()

    items = [_to_response(row) for row in rows]
    return EventImplicationListResponse(event_id=event_id, items=items, total=len(items))


def list_active_implications(db: Session) -> list[ImplicationCandidate]:
    """All implications for active canonical events — used by briefing integration."""
    return list(
        db.scalars(
            select(ImplicationCandidate)
            .join(CanonicalEvent, ImplicationCandidate.canonical_event_id == CanonicalEvent.id)
            .where(CanonicalEvent.is_active.is_(True))
            .order_by(ImplicationCandidate.confidence.desc())
        ).all()
    )


def count_implications(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(ImplicationCandidate)) or 0
