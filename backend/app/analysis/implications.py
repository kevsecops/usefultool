"""Rule-based, exposure-aware implications engine.

Generates conservative ImplicationCandidate drafts from canonical events,
linked source records, and computed asset exposures. No LLM — Phase 7.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.event_asset_exposure import EventAssetExposure
from app.models.exposure_asset import ExposureAsset
from app.models.observed_event import ObservedEvent
from app.schemas.exposure import ExposureType
from app.schemas.implication import EvidenceLevel, GeneratedBy, ImplicationCategory

ENGINE_VERSION = "1"

# Phrases that imply confirmed outages or market predictions — never emit.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\bgeschlossen\b", re.IGNORECASE),
    re.compile(r"\bbricht\s+zusammen\b", re.IGNORECASE),
    re.compile(r"\bkomplett\s+ausgefallen\b", re.IGNORECASE),
    re.compile(r"\bLieferkette\s+bricht\b", re.IGNORECASE),
    re.compile(r"\bHäfen\s+geschlossen\b", re.IGNORECASE),
    re.compile(r"\bFlughäfen\s+geschlossen\b", re.IGNORECASE),
    re.compile(r"\bBörse\b", re.IGNORECASE),
    re.compile(r"\bAktien\b", re.IGNORECASE),
    re.compile(r"\bMarkt(?:preis|prognose)\b", re.IGNORECASE),
]

_LOGISTICS_ASSET_TYPES = {"port", "airport"}
_INFRASTRUCTURE_ASSET_TYPES = {"power_plant", "airport", "port"}
_TECHNOLOGY_ASSET_TYPES = {"power_plant", "airport"}

_STORM_EVENT_TYPES = {
    "storm",
    "tropical_cyclone",
    "cyclone",
    "hurricane",
    "typhoon",
    "flood",
    "weather",
    "geomagnetic_storm",
    "solar_radiation_storm",
    "radio_blackout",
}


@dataclass
class ImplicationDraft:
    category: str
    title: str
    description: str | None = None
    affected_region: str | None = None
    related_asset_ids: list[uuid.UUID] = field(default_factory=list)
    supporting_source_ids: list[str] = field(default_factory=list)
    confidence: str = "medium"
    evidence_level: str = EvidenceLevel.HYPOTHESIS
    rationale: str | None = None
    missing_data: str | None = None
    generated_by: str = GeneratedBy.RULE_BASED


def has_forbidden_claim(text: str) -> bool:
    """Return True when text contains disallowed outage/market claims."""
    return any(pattern.search(text) for pattern in _FORBIDDEN_PATTERNS)


def is_conservative_language(text: str, *, require_hypothesis_prefix: bool = True) -> bool:
    """Return True when text uses allowed hypothesis framing and no forbidden claims."""
    if not text or not text.strip():
        return False
    if has_forbidden_claim(text):
        return False
    if not require_hypothesis_prefix:
        return True
    lowered = text.lower()
    return any(
        prefix in lowered
        for prefix in ("mögliche", "potenzielle", "möglicher", "potenzieller", "hypothese")
    )


def validate_implication_text(title: str, description: str | None = None) -> None:
    """Raise ValueError when generated text violates conservative-language rules."""
    if not is_conservative_language(title, require_hypothesis_prefix=True):
        raise ValueError(f"Implication title fails conservative-language check: {title!r}")
    if description and has_forbidden_claim(description):
        raise ValueError(
            f"Implication description contains forbidden claims: {description!r}"
        )


def _region_from_member(member: Alert | ObservedEvent | None) -> str | None:
    if member is None:
        return None
    if member.region and member.country_code:
        return f"{member.region}, {member.country_code}"
    if getattr(member, "country_name", None):
        return member.country_name
    if member.country_code:
        return member.country_code
    if member.location_name:
        return member.location_name
    return None


def _load_members(
    db: Session, event: CanonicalEvent
) -> tuple[list[Alert], list[ObservedEvent]]:
    from sqlalchemy import select

    alerts: list[Alert] = []
    observed: list[ObservedEvent] = []
    if not event.links:
        return alerts, observed

    alert_ids = [link.member_id for link in event.links if link.member_type == "alert"]
    observed_ids = [
        link.member_id for link in event.links if link.member_type == "observed_event"
    ]
    if alert_ids:
        alerts = list(db.scalars(select(Alert).where(Alert.id.in_(alert_ids))).all())
    if observed_ids:
        observed = list(
            db.scalars(select(ObservedEvent).where(ObservedEvent.id.in_(observed_ids))).all()
        )
    return alerts, observed


def _load_exposures_with_assets(
    db: Session, event_id: uuid.UUID
) -> list[tuple[EventAssetExposure, ExposureAsset]]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    rows = db.scalars(
        select(EventAssetExposure)
        .options(selectinload(EventAssetExposure.asset))
        .where(EventAssetExposure.event_id == event_id)
    ).all()
    result: list[tuple[EventAssetExposure, ExposureAsset]] = []
    for row in rows:
        if row.asset:
            result.append((row, row.asset))
    return result


def _supporting_ids(alerts: list[Alert], observed: list[ObservedEvent]) -> list[str]:
    ids: list[str] = []
    for alert in alerts:
        ids.append(str(alert.id))
    for obs in observed:
        ids.append(str(obs.id))
    return ids


def _asset_names(assets: list[ExposureAsset], limit: int = 3) -> str:
    names = [asset.name for asset in assets[:limit]]
    if len(assets) > limit:
        names.append(f"und {len(assets) - limit} weitere")
    return ", ".join(names)


def _confidence_from_exposures(
    exposures: list[tuple[EventAssetExposure, ExposureAsset]],
    *,
    inside_only: bool = False,
) -> str:
    relevant = exposures
    if inside_only:
        relevant = [
            (exp, asset)
            for exp, asset in exposures
            if exp.exposure_type == ExposureType.INSIDE_EVENT_AREA or exp.overlap
        ]
    count = len(relevant)
    if count >= 2:
        return "medium"
    if count == 1:
        high_importance = any(asset.importance_level in ("high", "critical") for _, asset in relevant)
        return "medium" if high_importance else "low"
    return "low"


def _dedupe_key(draft: ImplicationDraft) -> tuple[str, str, str]:
    asset_key = ",".join(sorted(str(aid) for aid in draft.related_asset_ids))
    return (draft.category, draft.title, asset_key)


def _add_draft(drafts: list[ImplicationDraft], seen: set[tuple[str, str, str]], draft: ImplicationDraft) -> None:
    validate_implication_text(draft.title, draft.description)
    key = _dedupe_key(draft)
    if key not in seen:
        seen.add(key)
        drafts.append(draft)


def _exposure_logistics_implication(
    event: CanonicalEvent,
    exposures: list[tuple[EventAssetExposure, ExposureAsset]],
    region: str | None,
    source_ids: list[str],
) -> ImplicationDraft | None:
    logistics_assets = [
        asset
        for exp, asset in exposures
        if asset.asset_type in _LOGISTICS_ASSET_TYPES
        and (
            exp.exposure_type == ExposureType.INSIDE_EVENT_AREA
            or exp.exposure_type == ExposureType.NEAR_EVENT_AREA
            or exp.overlap
        )
    ]
    if not logistics_assets:
        return None

    inside = [
        asset
        for exp, asset in exposures
        if asset in logistics_assets
        and (exp.exposure_type == ExposureType.INSIDE_EVENT_AREA or exp.overlap)
    ]
    confidence = "medium" if len(inside) >= 2 else _confidence_from_exposures(exposures, inside_only=True)

    names = _asset_names(logistics_assets)
    return ImplicationDraft(
        category=ImplicationCategory.LOGISTICS,
        title="Mögliche Beeinträchtigung regionaler Transportwege",
        description=(
            f"Im Ereignisbereich von „{event.title}“ liegen {len(logistics_assets)} "
            f"exponierte Verkehrsinfrastruktur-Assets ({names}). "
            "Eine tatsächliche Betriebsunterbrechung ist nicht bestätigt."
        ),
        affected_region=region,
        related_asset_ids=[asset.id for asset in logistics_assets],
        supporting_source_ids=source_ids,
        confidence=confidence,
        evidence_level=EvidenceLevel.INFERRED_FROM_EXPOSURE,
        rationale=(
            f"{len(logistics_assets)} port/airport asset(s) in or near event geometry "
            f"({len(inside)} inside event area)"
        ),
        missing_data="Keine Echtzeit-Betriebsstatusdaten für Häfen oder Flughäfen verfügbar.",
    )


def _exposure_infrastructure_implication(
    event: CanonicalEvent,
    exposures: list[tuple[EventAssetExposure, ExposureAsset]],
    region: str | None,
    source_ids: list[str],
) -> ImplicationDraft | None:
    infra_assets = [
        asset
        for exp, asset in exposures
        if asset.asset_type in _INFRASTRUCTURE_ASSET_TYPES
        and (
            exp.exposure_type == ExposureType.INSIDE_EVENT_AREA
            or exp.exposure_type == ExposureType.NEAR_EVENT_AREA
            or exp.overlap
        )
    ]
    if not infra_assets:
        return None

    power_plants = [a for a in infra_assets if a.asset_type == "power_plant"]
    airports = [a for a in infra_assets if a.asset_type == "airport"]

    if airports and event.event_type == "earthquake":
        title = "Mögliche Beeinträchtigung von Flughafen-Infrastruktur"
        rationale = f"Earthquake event with {len(airports)} airport(s) in exposure zone"
    elif power_plants:
        title = "Mögliche Belastung kritischer Infrastruktur"
        rationale = f"{len(power_plants)} power plant(s) in exposure zone"
    else:
        title = "Mögliche Beeinträchtigung regionaler Infrastruktur"
        rationale = f"{len(infra_assets)} infrastructure asset(s) in exposure zone"

    return ImplicationDraft(
        category=ImplicationCategory.INFRASTRUCTURE,
        title=title,
        description=(
            f"Für „{event.title}“ wurden {len(infra_assets)} Infrastruktur-Assets "
            f"im Ereignisbereich identifiziert ({_asset_names(infra_assets)}). "
            "Schäden oder Ausfälle sind nicht bestätigt."
        ),
        affected_region=region,
        related_asset_ids=[asset.id for asset in infra_assets],
        supporting_source_ids=source_ids,
        confidence=_confidence_from_exposures(exposures, inside_only=True),
        evidence_level=EvidenceLevel.INFERRED_FROM_EXPOSURE,
        rationale=rationale,
        missing_data="Keine Schadensmeldungen oder Betriebsstatus für betroffene Assets.",
    )


def _space_weather_implications(
    event: CanonicalEvent,
    exposures: list[tuple[EventAssetExposure, ExposureAsset]],
    observed: list[ObservedEvent],
    region: str | None,
    source_ids: list[str],
) -> list[ImplicationDraft]:
    system_exposures = [
        (exp, asset)
        for exp, asset in exposures
        if exp.exposure_type == ExposureType.SYSTEM_LEVEL_EXPOSURE
    ]
    if not system_exposures:
        return []

    power_assets = [asset for _, asset in system_exposures if asset.asset_type == "power_plant"]
    tech_assets = [
        asset
        for _, asset in system_exposures
        if asset.asset_type in _TECHNOLOGY_ASSET_TYPES
    ]

    metadata: dict[str, Any] = {}
    for obs in observed:
        if obs.source == "noaa_swpc":
            metadata = obs.source_metadata or {}

    systems = metadata.get("potential_systems", [])
    scale_label = ""
    if metadata.get("scale_type") and metadata.get("scale_level"):
        scale_label = f" ({metadata['scale_type']}{metadata['scale_level']})"

    drafts: list[ImplicationDraft] = []
    if tech_assets:
        drafts.append(
            ImplicationDraft(
                category=ImplicationCategory.TECHNOLOGY,
                title="Mögliche Beeinträchtigung technischer Systeme durch Weltraumwetter",
                description=(
                    f"Geomagnetisches Weltraumereignis{scale_label} mit systemweiter Exposure "
                    f"für {len(tech_assets)} technische Assets. "
                    "Konkrete Störungen sind nicht bestätigt."
                ),
                affected_region=region or "Global",
                related_asset_ids=[asset.id for asset in tech_assets],
                supporting_source_ids=source_ids,
                confidence="medium" if event.spatial_scope in ("global", "orbital") else "low",
                evidence_level=EvidenceLevel.INFERRED_FROM_EXPOSURE,
                rationale=(
                    f"System-level exposure for space weather; affected systems: "
                    f"{', '.join(systems) or 'general'}"
                ),
                missing_data="Keine Echtzeit-Störungsdaten für Satelliten- oder GNSS-Systeme.",
            )
        )

    if power_assets:
        drafts.append(
            ImplicationDraft(
                category=ImplicationCategory.ENERGY,
                title="Mögliche Belastung des Stromnetzes durch geomagnetische Aktivität",
                description=(
                    f"Weltraumwetterereignis mit Exposure für {len(power_assets)} "
                    f"Kraftwerks-Assets in betroffenen Breitengraden. "
                    "Kein bestätigter Netzausfall."
                ),
                affected_region=region or "Global",
                related_asset_ids=[asset.id for asset in power_assets],
                supporting_source_ids=source_ids,
                confidence="medium",
                evidence_level=EvidenceLevel.INFERRED_FROM_EXPOSURE,
                rationale=f"G-scale space weather with {len(power_assets)} power plant(s) exposed",
                missing_data="Keine Netzbetreiber-Störungsmeldungen verfügbar.",
            )
        )

    return drafts


def _officially_reported_implications(
    event: CanonicalEvent,
    alerts: list[Alert],
    observed: list[ObservedEvent],
    region: str | None,
    source_ids: list[str],
) -> list[ImplicationDraft]:
    """Derive implications from source record titles/descriptions — factual framing only."""
    drafts: list[ImplicationDraft] = []
    members: list[Alert | ObservedEvent] = [*alerts, *observed]

    for member in members:
        title_lower = (member.title or "").lower()
        category = getattr(member, "category", None)
        event_type = (getattr(member, "event_type", None) or event.event_type or "").lower()

        if "tsunami" in title_lower or event_type == "tsunami":
            drafts.append(
                ImplicationDraft(
                    category=ImplicationCategory.HUMANITARIAN,
                    title="Mögliche humanitäre Auswirkungen bei Tsunami-Warnung",
                    description=(
                        f"Amtliche Tsunami-Meldung: „{member.title}“. "
                        "Evakuierungs- oder Schutzmaßnahmen können regional relevant sein."
                    ),
                    affected_region=region or _region_from_member(member),
                    supporting_source_ids=[str(member.id)],
                    confidence="medium" if member.severity in ("severe", "extreme") else "low",
                    evidence_level=EvidenceLevel.OFFICIALLY_REPORTED,
                    rationale="Tsunami warning in official source record",
                )
            )

        if category == "health" or "epidem" in title_lower:
            drafts.append(
                ImplicationDraft(
                    category=ImplicationCategory.PUBLIC_HEALTH,
                    title="Mögliche öffentliche Gesundheitsrisiken gemäß amtlicher Meldung",
                    description=f"Amtliche Gesundheitswarnung: „{member.title}“.",
                    affected_region=region or _region_from_member(member),
                    supporting_source_ids=[str(member.id)],
                    confidence="medium",
                    evidence_level=EvidenceLevel.OFFICIALLY_REPORTED,
                    rationale="Health-related official alert text",
                )
            )

    return drafts


def _category_hypothesis_implications(
    event: CanonicalEvent,
    region: str | None,
    source_ids: list[str],
) -> list[ImplicationDraft]:
    """Low-confidence pattern-based implications when exposure data is sparse."""
    event_type = (event.event_type or "").lower()
    drafts: list[ImplicationDraft] = []

    if event_type in _STORM_EVENT_TYPES or event.severity in ("severe", "extreme"):
        if event_type not in ("geomagnetic_storm", "solar_radiation_storm", "earthquake"):
            drafts.append(
                ImplicationDraft(
                    category=ImplicationCategory.LOGISTICS,
                    title="Mögliche regionale Verkehrsverzögerungen bei Unwetterlage",
                    description=(
                        f"Schwere Wetter-/Sturmereignis „{event.title}“ kann regional "
                        "zu Verzögerungen im Transport führen — nicht bestätigt."
                    ),
                    affected_region=region,
                    supporting_source_ids=source_ids,
                    confidence="low",
                    evidence_level=EvidenceLevel.HYPOTHESIS,
                    rationale="Severe storm event type without confirmed transport disruption",
                    missing_data="Keine Exposure-Daten oder Echtzeit-Verkehrsstatus.",
                )
            )

    if event_type == "earthquake" and event.severity in ("severe", "extreme"):
        drafts.append(
            ImplicationDraft(
                category=ImplicationCategory.HUMANITARIAN,
                title="Möglicher erhöhter humanitärer Unterstützungsbedarf",
                description=(
                    f"Starkes Erdbeben „{event.title}“ kann lokal humanitäre "
                    "Ressourcen binden — Schadensausmaß nicht bestätigt."
                ),
                affected_region=region,
                supporting_source_ids=source_ids,
                confidence="low",
                evidence_level=EvidenceLevel.HYPOTHESIS,
                rationale="High-severity earthquake pattern",
                missing_data="Keine bestätigten Schadens- oder Opferzahlen.",
            )
        )

    return drafts


def generate_implications_for_event(
    db: Session,
    event: CanonicalEvent,
    *,
    exposures: list[tuple[EventAssetExposure, ExposureAsset]] | None = None,
) -> list[ImplicationDraft]:
    """Generate implication drafts for one canonical event."""
    alerts, observed = _load_members(db, event)
    if exposures is None:
        exposures = _load_exposures_with_assets(db, event.id)

    primary_member: Alert | ObservedEvent | None = None
    if event.primary_source_id:
        for alert in alerts:
            if alert.id == event.primary_source_id:
                primary_member = alert
                break
        if primary_member is None:
            for obs in observed:
                if obs.id == event.primary_source_id:
                    primary_member = obs
                    break
    if primary_member is None and alerts:
        primary_member = alerts[0]
    elif primary_member is None and observed:
        primary_member = observed[0]

    region = _region_from_member(primary_member)
    source_ids = _supporting_ids(alerts, observed)

    drafts: list[ImplicationDraft] = []
    seen: set[tuple[str, str, str]] = set()

    event_type = (event.event_type or "").lower()
    is_space_weather = event_type in (
        "geomagnetic_storm",
        "solar_radiation_storm",
        "radio_blackout",
    ) or any(obs.source == "noaa_swpc" for obs in observed)

    if is_space_weather:
        for draft in _space_weather_implications(event, exposures, observed, region, source_ids):
            _add_draft(drafts, seen, draft)
    else:
        logistics = _exposure_logistics_implication(event, exposures, region, source_ids)
        if logistics:
            _add_draft(drafts, seen, logistics)

        infra = _exposure_infrastructure_implication(event, exposures, region, source_ids)
        if infra:
            _add_draft(drafts, seen, infra)

    for draft in _officially_reported_implications(event, alerts, observed, region, source_ids):
        _add_draft(drafts, seen, draft)

    if not drafts or not exposures:
        for draft in _category_hypothesis_implications(event, region, source_ids):
            _add_draft(drafts, seen, draft)

    return drafts
