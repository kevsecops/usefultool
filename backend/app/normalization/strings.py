"""String helpers for DB-safe field values."""


def clamp_str(value: str | None, max_len: int) -> str | None:
    """Truncate strings to fit VARCHAR columns without failing ingest."""
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3] + "..."
