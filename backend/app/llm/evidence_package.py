"""Build compact structured evidence packages for LLM briefing input.

Uses canonical events, linked source summaries, exposures, and implication
candidates — never raw payloads or FIRMS point data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.risk_score import RiskScoreResult
from app.core.config import get_settings
from app.llm.sanitize import sanitize_alert_text
from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.event_asset_exposure import EventAssetExposure
from app.models.implication_candidate import ImplicationCandidate
from app.models.observed_event import ObservedEvent
from app.services.implication_service import list_active_implications

SEVERITY_RANK = {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}

KNOWN_LIMITATIONS = [
    "KI-Analyse basiert auf strukturierten, vorverarbeiteten Ereignisdaten — keine Roh-Payloads.",
    "Quelltexte in Titeln sind als untrusted data markiert und nicht verifiziert.",
    "Exposure-Daten stammen aus Demo-Fixtures bzw. berechneter Geometrie — keine Echtzeit-Verifikation.",
    "Implikationen sind Hypothesen aus Regel-Engine oder LLM — keine amtlichen Bewertungen.",
    "Keine Marktprognosen, Hafensperrungen oder verifizierten wirtschaftlichen Auswirkungen.",
]


def _top_events(events: list[CanonicalEvent], limit: int) -> list[CanonicalEvent]:
    return sorted(
        events,
        key=lambda e: (SEVERITY_RANK.get(e.severity, 0), e.started_at),
        reverse=True,
    )[:limit]


def _source_record_summary(
    member_type: str,
    *,
    alert: Alert | None = None,
    observed: ObservedEvent | None = None,
) -> dict[str, Any] | None:
    if member_type == "alert" and alert:
        title = sanitize_alert_text(alert.title)
        return {
            "id": str(alert.id),
            "member_type": "alert",
            "source": alert.source,
            "title": f"<alert_data>{title}</alert_data>",
            "severity": alert.severity,
            "category": alert.category,
            "issued_at": alert.issued_at.isoformat().replace("+00:00", "Z"),
        }
    if member_type == "observed_event" and observed:
        title = sanitize_alert_text(observed.title)
        return {
            "id": str(observed.id),
            "member_type": "observed_event",
            "source": observed.source,
            "title": f"<alert_data>{title}</alert_data>",
            "severity": observed.severity,
            "category": observed.category,
            "event_type": observed.event_type,
            "spatial_scope": observed.spatial_scope,
            "issued_at": observed.issued_at.isoformat().replace("+00:00", "Z"),
        }
    return None


def _exposure_summaries(
    db: Session,
    event_id: UUID,
    *,
    max_exposures: int,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(EventAssetExposure)
        .options(selectinload(EventAssetExposure.asset))
        .where(EventAssetExposure.event_id == event_id)
        .order_by(EventAssetExposure.confidence.desc())
        .limit(max_exposures)
    ).all()

    summaries: list[dict[str, Any]] = []
    for row in rows:
        if not row.asset:
            continue
        summaries.append(
            {
                "asset_id": str(row.asset_id),
                "asset_name": row.asset.name,
                "asset_type": row.asset.asset_type,
                "exposure_type": row.exposure_type,
                "distance_km": row.distance_km,
                "overlap": row.overlap,
                "confidence": row.confidence,
            }
        )
    return summaries


def _implication_summaries(
    implications: list[ImplicationCandidate],
    event_id: UUID,
) -> list[dict[str, Any]]:
    event_implications = [i for i in implications if i.canonical_event_id == event_id]
    return [
        {
            "id": str(imp.id),
            "category": imp.category,
            "title": imp.title,
            "description": imp.description,
            "confidence": imp.confidence,
            "evidence_level": imp.evidence_level,
            "supporting_source_ids": list(imp.supporting_source_ids or []),
            "related_asset_ids": list(imp.related_asset_ids or []),
        }
        for imp in event_implications
    ]


def _load_active_events(db: Session) -> list[CanonicalEvent]:
    return list(
        db.scalars(
            select(CanonicalEvent)
            .options(selectinload(CanonicalEvent.links))
            .where(CanonicalEvent.is_active.is_(True))
            .order_by(CanonicalEvent.started_at.desc())
        ).all()
    )


def _load_member_records(
    db: Session,
    event: CanonicalEvent,
) -> tuple[dict[UUID, Alert], dict[UUID, ObservedEvent]]:
    alert_ids = [link.member_id for link in event.links if link.member_type == "alert"]
    observed_ids = [
        link.member_id for link in event.links if link.member_type == "observed_event"
    ]

    alerts_by_id: dict[UUID, Alert] = {}
    observed_by_id: dict[UUID, ObservedEvent] = {}

    if alert_ids:
        alerts = db.scalars(select(Alert).where(Alert.id.in_(alert_ids))).all()
        alerts_by_id = {row.id: row for row in alerts}
    if observed_ids:
        observed = db.scalars(select(ObservedEvent).where(ObservedEvent.id.in_(observed_ids))).all()
        observed_by_id = {row.id: row for row in observed}

    return alerts_by_id, observed_by_id


def build_evidence_package(
    db: Session,
    *,
    risk: RiskScoreResult,
    generated_at: datetime,
    active_alerts: list[Alert] | None = None,
) -> dict[str, Any]:
    """Build compact evidence package from canonical events and linked data."""
    settings = get_settings()
    max_events = settings.llm_max_events
    max_exposures = settings.llm_max_exposures_per_event

    events = _load_active_events(db)
    implications = list_active_implications(db)
    selected = _top_events(events, max_events)

    event_summaries: list[dict[str, Any]] = []
    valid_source_ids: set[str] = set()

    for event in selected:
        alerts_by_id, observed_by_id = _load_member_records(db, event)
        source_records: list[dict[str, Any]] = []

        for link in event.links:
            summary = _source_record_summary(
                link.member_type,
                alert=alerts_by_id.get(link.member_id),
                observed=observed_by_id.get(link.member_id),
            )
            if summary:
                source_records.append(summary)
                valid_source_ids.add(summary["id"])

        exposures = _exposure_summaries(db, event.id, max_exposures=max_exposures)
        for exp in exposures:
            valid_source_ids.add(exp["asset_id"])

        imp_summaries = _implication_summaries(implications, event.id)
        for imp in imp_summaries:
            valid_source_ids.add(imp["id"])
            valid_source_ids.update(imp.get("supporting_source_ids", []))

        valid_source_ids.add(str(event.id))

        from sqlalchemy import func

        total_exposure_count = (
            db.scalar(
                select(func.count())
                .select_from(EventAssetExposure)
                .where(EventAssetExposure.event_id == event.id)
            )
            or 0
        )

        event_summaries.append(
            {
                "id": str(event.id),
                "title": sanitize_alert_text(event.title),
                "event_type": event.event_type,
                "severity": event.severity,
                "confidence": event.confidence,
                "spatial_scope": event.spatial_scope,
                "status": event.status,
                "started_at": event.started_at.isoformat().replace("+00:00", "Z"),
                "correlation_reason": event.correlation_reason,
                "source_records": source_records,
                "exposures": exposures,
                "exposure_truncated": total_exposure_count > len(exposures),
                "total_exposure_count": total_exposure_count,
                "implication_candidates": imp_summaries,
            }
        )

    active = active_alerts or []
    for alert in active:
        valid_source_ids.add(str(alert.id))

    return {
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "canonical_events": event_summaries,
        "stats": {
            "active_alert_count": len(active),
            "active_event_count": len(events),
            "global_risk_score": risk.global_score,
            "score_breakdown": risk.breakdown,
        },
        "known_limitations": list(KNOWN_LIMITATIONS),
        "context_documents": [],
        "valid_source_ids": sorted(valid_source_ids),
        "truncated_events": len(events) > max_events,
        "total_event_count": len(events),
    }


def has_canonical_events(db: Session) -> bool:
    """True when at least one active canonical event exists."""
    from sqlalchemy import func

    count = db.scalar(
        select(func.count())
        .select_from(CanonicalEvent)
        .where(CanonicalEvent.is_active.is_(True))
    )
    return (count or 0) > 0


def build_observed_events_section(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Rule-based observed events section from evidence package."""
    items: list[dict[str, Any]] = []
    for event in evidence.get("canonical_events", []):
        observed_records = [
            r for r in event.get("source_records", []) if r.get("member_type") == "observed_event"
        ]
        if not observed_records:
            continue
        source_ids = [r["id"] for r in observed_records] + [event["id"]]
        items.append(
            {
                "canonical_event_id": event["id"],
                "event_title": event["title"],
                "event_type": event.get("event_type"),
                "severity": event["severity"],
                "observed_count": len(observed_records),
                "sources": sorted({r["source"] for r in observed_records}),
                "source_ids": source_ids,
            }
        )

    confidence = "low"
    if len(items) >= 3:
        confidence = "high"
    elif items:
        confidence = "medium"

    summary = (
        f"{len(items)} kanonische Ereignis(se) mit verknüpften Observed Events."
        if items
        else "Keine verknüpften Observed Events in aktiven kanonischen Ereignissen."
    )
    return {"summary": summary, "items": items, "confidence": confidence}


def build_verified_exposure_section(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Verified exposure section from computed geospatial analysis."""
    items: list[dict[str, Any]] = []
    for event in evidence.get("canonical_events", []):
        for exp in event.get("exposures", []):
            items.append(
                {
                    "event_id": event["id"],
                    "event_title": event["title"],
                    "asset_name": exp["asset_name"],
                    "asset_type": exp["asset_type"],
                    "exposure_type": exp["exposure_type"],
                    "confidence": exp.get("confidence", "medium"),
                    "source_ids": [event["id"], exp["asset_id"]],
                }
            )

    confidence = "low"
    if len(items) >= 5:
        confidence = "high"
    elif items:
        confidence = "medium"

    summary = (
        f"{len(items)} berechnete Asset-Exposures über {len(evidence.get('canonical_events', []))} Ereignisse."
        if items
        else "Keine berechneten Asset-Exposures für aktive Ereignisse."
    )
    return {"summary": summary, "items": items, "confidence": confidence}


def build_evidence_gaps(evidence: dict[str, Any]) -> list[str]:
    """Identify data gaps from evidence package."""
    gaps: list[str] = []
    events = evidence.get("canonical_events", [])

    if not events:
        gaps.append("Keine aktiven kanonischen Ereignisse — Analyse basiert nur auf Alerts.")
        return gaps

    events_without_sources = [
        e for e in events if not e.get("source_records")
    ]
    if events_without_sources:
        gaps.append(
            f"{len(events_without_sources)} Ereignis(se) ohne verknüpfte Quellmeldungen."
        )

    events_without_exposure = [e for e in events if not e.get("exposures")]
    if events_without_exposure:
        gaps.append(
            f"{len(events_without_exposure)} Ereignis(se) ohne berechnete Asset-Exposures."
        )

    events_without_implications = [e for e in events if not e.get("implication_candidates")]
    if events_without_implications:
        gaps.append(
            f"{len(events_without_implications)} Ereignis(se) ohne Regel-Implikationskandidaten."
        )

    if evidence.get("truncated_events"):
        gaps.append(
            f"Ereignisliste gekürzt auf Top-{len(events)} "
            f"(von {evidence.get('total_event_count', len(events))} aktiv)."
        )

    if not evidence.get("context_documents"):
        gaps.append("Keine Kontextdokumente verfügbar (Phase 8+).")

    return gaps


def build_cross_border_relevance(
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    """Cross-border patterns from canonical event spatial scopes."""
    global_events = [
        e for e in evidence.get("canonical_events", []) if e.get("spatial_scope") == "global"
    ]
    regional_events = [
        e for e in evidence.get("canonical_events", []) if e.get("spatial_scope") == "regional"
    ]

    patterns: list[dict[str, Any]] = []
    if global_events:
        source_ids = [e["id"] for e in global_events]
        for record in global_events[0].get("source_records", []):
            source_ids.append(record["id"])
        patterns.append(
            {
                "description": (
                    f"{len(global_events)} Ereignis(se) mit globalem räumlichen Scope "
                    f"(z. B. Raumwetter, großflächige Phänomene)."
                ),
                "confidence": "medium" if len(global_events) >= 2 else "low",
                "source_ids": source_ids[:20],
            }
        )

    scopes = {e.get("spatial_scope") for e in evidence.get("canonical_events", [])}
    if len(scopes) >= 2:
        mixed_ids = [e["id"] for e in evidence.get("canonical_events", [])[:10]]
        patterns.append(
            {
                "description": (
                    f"Gemischte räumliche Scopes in aktiven Ereignissen: {', '.join(sorted(scopes))}."
                ),
                "confidence": "low",
                "source_ids": mixed_ids,
            }
        )

    if regional_events and len(regional_events) >= 2:
        patterns.append(
            {
                "description": (
                    f"{len(regional_events)} regionale Ereignisse — mögliche grenzüberschreitende Relevanz."
                ),
                "confidence": "medium",
                "source_ids": [e["id"] for e in regional_events[:10]],
            }
        )

    return patterns


def build_technology_infrastructure_risks(
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    """Technology/infrastructure risks from implications and exposures."""
    risks: list[dict[str, Any]] = []

    for event in evidence.get("canonical_events", []):
        tech_implications = [
            imp
            for imp in event.get("implication_candidates", [])
            if imp.get("category") in ("technology", "infrastructure", "energy")
        ]
        for imp in tech_implications:
            risks.append(
                {
                    "description": imp["title"],
                    "confidence": imp.get("confidence", "low"),
                    "evidence_level": imp.get("evidence_level", "hypothesis"),
                    "source_ids": [imp["id"], event["id"]],
                }
            )

        infra_exposures = [
            exp
            for exp in event.get("exposures", [])
            if exp.get("asset_type") in ("power_plant", "airport", "port")
        ]
        if infra_exposures:
            asset_names = ", ".join(e["asset_name"] for e in infra_exposures[:3])
            risks.append(
                {
                    "description": (
                        f"Mögliche Infrastruktur-Exposition bei „{event['title']}“: {asset_names}."
                    ),
                    "confidence": "medium" if len(infra_exposures) >= 2 else "low",
                    "evidence_level": "inferred_from_exposure",
                    "source_ids": [event["id"]] + [e["asset_id"] for e in infra_exposures],
                }
            )

    return risks[:15]
