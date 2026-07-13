"""UTC datetime parsing utilities."""

from datetime import UTC, datetime

from dateutil import parser as date_parser


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = date_parser.isoparse(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)
