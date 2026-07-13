"""Rule-based cross-source event correlation service."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.observed_event import ObservedEvent
from app.normalization.datetime_utils import utc_now
from app.normalization.geometry import geojson_to_wkt_element
from app.schemas.canonical_event import CorrelateEventsResponse

logger = get_logger(__name__)

CORRELATION_VERSION = "1"
MemberType = Literal["alert", "observed_event"]
MatchLevel = Literal["none", "medium", "high"]

_RELATED_CATEGORIES: dict[str, frozenset[str]] = {
    "earthquake": frozenset({"earthquake"}),
    "weather": frozenset({"weather", "flood", "tsunami"}),
    "flood": frozenset({"flood", "weather"}),
    "wildfire": frozenset({"wildfire", "weather"}),
    "volcano": frozenset({"volcano", "earthquake"}),
    "tsunami": frozenset({"tsunami", "earthquake", "weather"}),
}


@dataclass
class CorrelatableMember:
    member_type: MemberType
    member_id: uuid.UUID
    source: str
    source_record_id: str
    title: str
    description: str | None
    category: str
    event_type: str | None
    severity: str
    status: str
    spatial_scope: str
    issued_at: datetime
    ends_at: datetime | None
    latitude: float | None
    longitude: float | None
    geometry_json: dict | None
    external_ids: set[str] = field(default_factory=set)


@dataclass
class CorrelationMatch:
    left: CorrelatableMember
    right: CorrelatableMember
    level: MatchLevel
    reasons: list[str]


@dataclass
class CorrelationStats:
    canonical_events_created: int = 0
    canonical_events_updated: int = 0
    links_created: int = 0
    possible_matches: int = 0
    members_processed: int = 0


def _normalize_token(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2}


def _title_similarity(left: str, right: str) -> float:
    left_tokens = _normalize_token(left)
    right_tokens = _normalize_token(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def _categories_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    left_related = _RELATED_CATEGORIES.get(left, frozenset({left}))
    return right in left_related or left in _RELATED_CATEGORIES.get(right, frozenset({right}))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


def _extract_external_ids(
    source: str,
    source_record_id: str,
    raw_payload: dict | None,
    source_metadata: dict | None = None,
) -> set[str]:
    ids: set[str] = set()
    if source_record_id:
        ids.add(source_record_id.lower())

    payload = raw_payload or {}
    if isinstance(payload, dict):
        for key in ("eventid", "event_id", "id", "episodeid", "episode_id"):
            value = payload.get(key)
            if value is not None:
                ids.add(str(value).lower())
        properties = payload.get("properties")
        if isinstance(properties, dict):
            for key in ("eventid", "event_id", "episodeid", "episode_id"):
                value = properties.get(key)
                if value is not None:
                    ids.add(str(value).lower())

    meta = source_metadata or {}
    if isinstance(meta, dict):
        for key in ("eventid", "event_id", "magnitude", "usgs_id"):
            value = meta.get(key)
            if value is not None:
                ids.add(str(value).lower())

    if source == "gdacs" and "-" in source_record_id:
        parts = source_record_id.split("-")
        if len(parts) >= 2:
            ids.add(parts[1].lower())

    return ids


def _member_from_alert(alert: Alert) -> CorrelatableMember:
    return CorrelatableMember(
        member_type="alert",
        member_id=alert.id,
        source=alert.source,
        source_record_id=alert.source_alert_id,
        title=alert.title,
        description=alert.description,
        category=alert.category,
        event_type=alert.event_type,
        severity=alert.severity,
        status=alert.status,
        spatial_scope="local",
        issued_at=alert.issued_at,
        ends_at=alert.expires_at,
        latitude=alert.latitude,
        longitude=alert.longitude,
        geometry_json=alert.geometry_json,
        external_ids=_extract_external_ids(alert.source, alert.source_alert_id, alert.raw_payload),
    )


def _member_from_observed_event(event: ObservedEvent) -> CorrelatableMember:
    return CorrelatableMember(
        member_type="observed_event",
        member_id=event.id,
        source=event.source,
        source_record_id=event.source_event_id,
        title=event.title,
        description=event.description,
        category=event.category,
        event_type=event.event_type,
        severity=event.severity,
        status=event.status,
        spatial_scope=event.spatial_scope,
        issued_at=event.issued_at,
        ends_at=event.ends_at,
        latitude=event.latitude,
        longitude=event.longitude,
        geometry_json=event.geometry_json,
        external_ids=_extract_external_ids(
            event.source,
            event.source_event_id,
            event.raw_payload,
            event.source_metadata,
        ),
    )


def _geo_distance_km(left: CorrelatableMember, right: CorrelatableMember) -> float | None:
    if (
        left.latitude is not None
        and left.longitude is not None
        and right.latitude is not None
        and right.longitude is not None
    ):
        return _haversine_km(left.latitude, left.longitude, right.latitude, right.longitude)
    return None


def _geo_match(left: CorrelatableMember, right: CorrelatableMember, distance_km: float) -> bool:
    dist = _geo_distance_km(left, right)
    if dist is not None:
        return dist <= distance_km
    return False


def _time_match(left: CorrelatableMember, right: CorrelatableMember, window_hours: float) -> bool:
    delta = abs((left.issued_at - right.issued_at).total_seconds()) / 3600
    return delta <= window_hours


def _external_id_match(left: CorrelatableMember, right: CorrelatableMember) -> bool:
    if not left.external_ids or not right.external_ids:
        return False
    return bool(left.external_ids & right.external_ids)


def score_pair(left: CorrelatableMember, right: CorrelatableMember) -> CorrelationMatch:
    settings = get_settings()
    reasons: list[str] = []

    if left.source == right.source:
        return CorrelationMatch(left, right, "none", [])

    if not _categories_compatible(left.category, right.category):
        return CorrelationMatch(left, right, "none", [])

    if not _time_match(left, right, settings.correlation_time_window_hours):
        return CorrelationMatch(left, right, "none", [])

    reasons.append("category_match")
    reasons.append("time_proximity")

    if not _geo_match(left, right, settings.correlation_distance_km):
        return CorrelationMatch(left, right, "none", [])

    reasons.append("geo_proximity")

    score = 60
    if left.category == right.category:
        score += 10
        reasons.append("same_category")
    if _external_id_match(left, right):
        score += 30
        reasons.append("external_id_match")

    title_sim = _title_similarity(left.title, right.title)
    if title_sim >= 0.25:
        score += 15
        reasons.append(f"title_similarity:{title_sim:.2f}")

    if left.event_type and right.event_type:
        left_type = left.event_type.lower()
        right_type = right.event_type.lower()
        if left_type in right_type or right_type in left_type:
            score += 10
            reasons.append("event_type_match")

    if score >= 70:
        return CorrelationMatch(left, right, "high", reasons)
    if score >= 50:
        return CorrelationMatch(left, right, "medium", reasons)
    return CorrelationMatch(left, right, "none", reasons)


def _severity_rank(severity: str) -> int:
    return {"extreme": 4, "severe": 3, "moderate": 2, "minor": 1, "unknown": 0}.get(severity, 0)


def _pick_primary(members: list[CorrelatableMember]) -> CorrelatableMember:
    return max(
        members,
        key=lambda member: (
            _severity_rank(member.severity),
            -member.issued_at.timestamp(),
        ),
    )


def _build_canonical_fields(
    members: list[CorrelatableMember],
    primary: CorrelatableMember,
    reasons: list[str],
    confidence: str,
) -> dict:
    now = utc_now()
    max_severity = max(members, key=lambda m: _severity_rank(m.severity)).severity
    started_at = min(m.issued_at for m in members)
    ended_candidates = [m.ends_at for m in members if m.ends_at is not None]
    ended_at = max(ended_candidates) if ended_candidates else None
    return {
        "event_type": primary.event_type or primary.category,
        "title": primary.title,
        "status": "active" if ended_at is None or ended_at >= now else "ended",
        "severity": max_severity,
        "geometry": geojson_to_wkt_element(primary.geometry_json),
        "geometry_json": primary.geometry_json,
        "spatial_scope": primary.spatial_scope,
        "started_at": started_at,
        "updated_at": now,
        "ended_at": ended_at,
        "confidence": confidence,
        "primary_source_id": primary.member_id,
        "correlation_reason": "; ".join(reasons),
        "correlation_version": CORRELATION_VERSION,
        "is_active": ended_at is None or ended_at >= now,
    }


class _UnionFind:
    def __init__(self, keys: list[str]) -> None:
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def _member_key(member: CorrelatableMember) -> str:
    return f"{member.member_type}:{member.member_id}"


def _load_members(db: Session) -> list[CorrelatableMember]:
    alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    events = db.scalars(select(ObservedEvent).where(ObservedEvent.is_active.is_(True))).all()
    members = [_member_from_alert(alert) for alert in alerts]
    members.extend(_member_from_observed_event(event) for event in events)
    return members


def _existing_links(db: Session) -> dict[str, CanonicalEventLink]:
    links = db.scalars(select(CanonicalEventLink)).all()
    return {f"{link.member_type}:{link.member_id}": link for link in links}


def _create_link(
    db: Session,
    canonical_event_id: uuid.UUID,
    member: CorrelatableMember,
    link_confidence: str,
    link_reason: str,
    now: datetime,
    stats: CorrelationStats,
) -> CanonicalEventLink:
    link = CanonicalEventLink(
        canonical_event_id=canonical_event_id,
        member_type=member.member_type,
        member_id=member.member_id,
        link_confidence=link_confidence,
        link_reason=link_reason,
        created_at=now,
    )
    db.add(link)
    stats.links_created += 1
    return link


def run_correlation(db: Session) -> CorrelateEventsResponse:
    """Correlate active alerts and observed events into canonical events."""
    settings = get_settings()
    stats = CorrelationStats()
    now = utc_now()

    members = _load_members(db)
    stats.members_processed = len(members)
    if len(members) < 2:
        logger.info("Correlation skipped: fewer than 2 active members")
        return CorrelateEventsResponse(
            canonical_events_created=stats.canonical_events_created,
            canonical_events_updated=stats.canonical_events_updated,
            links_created=stats.links_created,
            possible_matches=stats.possible_matches,
            members_processed=stats.members_processed,
        )

    existing_links = _existing_links(db)
    member_by_key = {_member_key(member): member for member in members}

    high_matches: list[CorrelationMatch] = []
    medium_matches: list[CorrelationMatch] = []

    for i, left in enumerate(members):
        for right in members[i + 1 :]:
            match = score_pair(left, right)
            if match.level == "high":
                high_matches.append(match)
            elif match.level == "medium":
                medium_matches.append(match)

    uf = _UnionFind(list(member_by_key.keys()))
    for match in high_matches:
        uf.union(_member_key(match.left), _member_key(match.right))

    high_groups: dict[str, list[CorrelatableMember]] = {}
    for key, member in member_by_key.items():
        root = uf.find(key)
        high_groups.setdefault(root, []).append(member)

    merged_member_keys: set[str] = set()

    for group_members in high_groups.values():
        if len(group_members) < 2:
            continue

        primary = _pick_primary(group_members)
        reasons: list[str] = []
        for match in high_matches:
            if match.left in group_members and match.right in group_members:
                reasons.extend(match.reasons)

        unique_reasons = list(dict.fromkeys(reasons))
        fields = _build_canonical_fields(group_members, primary, unique_reasons, "high")

        linked_event_id: uuid.UUID | None = None
        for member in group_members:
            existing = existing_links.get(_member_key(member))
            if existing and existing.link_confidence == "high":
                linked_event_id = existing.canonical_event_id
                break

        if linked_event_id:
            canonical = db.get(CanonicalEvent, linked_event_id)
            if canonical:
                for key, value in fields.items():
                    setattr(canonical, key, value)
                stats.canonical_events_updated += 1
        else:
            canonical = CanonicalEvent(**fields)
            db.add(canonical)
            db.flush()
            stats.canonical_events_created += 1

        for member in group_members:
            member_key = _member_key(member)
            merged_member_keys.add(member_key)
            existing = existing_links.get(member_key)
            if existing:
                if existing.canonical_event_id != canonical.id:
                    existing.canonical_event_id = canonical.id
                existing.link_confidence = "high"
                existing.link_reason = "; ".join(unique_reasons)
            else:
                link = _create_link(
                    db,
                    canonical.id,
                    member,
                    "high",
                    "; ".join(unique_reasons),
                    now,
                    stats,
                )
                existing_links[member_key] = link

    for match in medium_matches:
        left_key = _member_key(match.left)
        right_key = _member_key(match.right)
        if left_key in merged_member_keys and right_key in merged_member_keys:
            continue

        primary = _pick_primary([match.left, match.right])
        secondary = match.left if primary.member_id == match.right.member_id else match.right

        primary_key = _member_key(primary)
        secondary_key = _member_key(secondary)

        primary_link = existing_links.get(primary_key)
        if primary_link:
            canonical = db.get(CanonicalEvent, primary_link.canonical_event_id)
        else:
            fields = _build_canonical_fields(
                [primary],
                primary,
                match.reasons,
                "medium",
            )
            canonical = CanonicalEvent(**fields)
            db.add(canonical)
            db.flush()
            stats.canonical_events_created += 1
            primary_link = _create_link(
                db,
                canonical.id,
                primary,
                "high",
                "; ".join(match.reasons),
                now,
                stats,
            )
            existing_links[primary_key] = primary_link

        if canonical is None:
            continue

        secondary_link = existing_links.get(secondary_key)
        reason = f"possible_match; {'; '.join(match.reasons)}"
        if secondary_link:
            if secondary_link.canonical_event_id != canonical.id:
                secondary_link.canonical_event_id = canonical.id
            secondary_link.link_confidence = "low"
            secondary_link.link_reason = reason
        else:
            _create_link(db, canonical.id, secondary, "low", reason, now, stats)
        stats.possible_matches += 1

    db.flush()
    logger.info(
        "Correlation complete: created=%d updated=%d links=%d possible=%d",
        stats.canonical_events_created,
        stats.canonical_events_updated,
        stats.links_created,
        stats.possible_matches,
    )
    return CorrelateEventsResponse(
        canonical_events_created=stats.canonical_events_created,
        canonical_events_updated=stats.canonical_events_updated,
        links_created=stats.links_created,
        possible_matches=stats.possible_matches,
        members_processed=stats.members_processed,
    )
