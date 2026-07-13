"""Shared Pydantic enums and types."""

from enum import StrEnum


class AlertSource(StrEnum):
    NINA = "nina"
    GDACS = "gdacs"
    NOAA = "noaa"


class DataSource(StrEnum):
    """All ingest sources including observed-event feeds."""

    NINA = "nina"
    GDACS = "gdacs"
    NOAA = "noaa"
    USGS = "usgs"
    EONET = "eonet"
    NOAA_SWPC = "noaa_swpc"


class RecordType(StrEnum):
    ALERT = "alert"
    OBSERVED_EVENT = "observed_event"


class ObservedEventStatus(StrEnum):
    AUTOMATIC = "automatic"
    REVIEWED = "reviewed"
    DELETED = "deleted"
    UNKNOWN = "unknown"


class SpatialScope(StrEnum):
    LOCAL = "local"
    REGIONAL = "regional"
    CONTINENTAL = "continental"
    GLOBAL = "global"
    ORBITAL = "orbital"


class Severity(StrEnum):
    UNKNOWN = "unknown"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    EXTREME = "extreme"


class Urgency(StrEnum):
    IMMEDIATE = "immediate"
    EXPECTED = "expected"
    FUTURE = "future"
    PAST = "past"
    UNKNOWN = "unknown"


class Certainty(StrEnum):
    OBSERVED = "observed"
    LIKELY = "likely"
    POSSIBLE = "possible"
    UNLIKELY = "unlikely"
    UNKNOWN = "unknown"


class Category(StrEnum):
    WEATHER = "weather"
    FLOOD = "flood"
    WILDFIRE = "wildfire"
    EARTHQUAKE = "earthquake"
    VOLCANO = "volcano"
    TSUNAMI = "tsunami"
    HEALTH = "health"
    CIVIL = "civil"
    INFRASTRUCTURE = "infrastructure"
    ENVIRONMENTAL = "environmental"
    OTHER = "other"


class AlertStatus(StrEnum):
    ACTUAL = "actual"
    EXERCISE = "exercise"
    TEST = "test"
    DRAFT = "draft"
    UNKNOWN = "unknown"


class IngestRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class BriefingType(StrEnum):
    RULE_BASED = "rule_based"
    LLM = "llm"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
