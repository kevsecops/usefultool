"""Source adapter protocol and shared types."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from app.schemas.alert import CanonicalAlert
from app.schemas.observed_event import CanonicalObservedEvent

RecordTypeLiteral = Literal["alert", "observed_event"]


@dataclass
class RawAlertPayload:
    source: str
    data: dict[str, Any]
    detail: dict[str, Any] | None = None
    geometry: dict[str, Any] | None = None
    ingest_mode: str | None = None


@dataclass
class ParsedAlert:
    source: str
    source_alert_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedObservedEvent:
    source: str
    source_event_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceHealth:
    source: str
    is_healthy: bool
    checked_at: datetime
    latency_ms: int | None = None
    last_success_at: datetime | None = None
    error_message: str | None = None
    ingest_mode: str | None = None
    records_fetched: int | None = None
    alerts_fetched: int | None = None


class BaseSourceAdapter(Protocol):
    source_id: str
    record_type: RecordTypeLiteral


class AlertSourceAdapter(BaseSourceAdapter, Protocol):
    async def fetch_alerts(self) -> list[RawAlertPayload]: ...

    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert: ...

    def normalize_alert(self, parsed: ParsedAlert) -> CanonicalAlert: ...

    async def health_check(self) -> SourceHealth: ...


class ObservedEventSourceAdapter(BaseSourceAdapter, Protocol):
    async def fetch_alerts(self) -> list[RawAlertPayload]: ...

    def parse_observed_event(self, raw: RawAlertPayload) -> ParsedObservedEvent: ...

    def normalize_observed_event(self, parsed: ParsedObservedEvent) -> CanonicalObservedEvent: ...

    async def health_check(self) -> SourceHealth: ...
