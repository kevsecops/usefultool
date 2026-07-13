"""HTML sanitization for alert descriptions."""

import bleach

_ALLOWED_TAGS: list[str] = []
_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}


def sanitize_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = bleach.clean(text, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRIBUTES, strip=True)
    cleaned = cleaned.replace("<br/>", "\n").replace("<br>", "\n")
    return cleaned.strip() or None
