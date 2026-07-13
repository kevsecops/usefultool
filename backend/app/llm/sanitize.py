"""Sanitize and truncate untrusted alert text before LLM input."""

from __future__ import annotations

import re

from app.normalization.html_sanitizer import sanitize_html

_MAX_TITLE_LEN = 200
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior)\s+instructions|"
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions|"
    r"system\s+prompt|you\s+are\s+now|act\s+as|"
    r"output\s+secret|reveal\s+secrets|"
    r"<\s*/?\s*system\s*>|```)",
    re.IGNORECASE,
)


def sanitize_alert_text(text: str | None, *, max_len: int = _MAX_TITLE_LEN) -> str:
    """Strip HTML, injection-like phrases, and truncate alert text."""
    if not text:
        return ""
    cleaned = sanitize_html(text) or ""
    cleaned = _INJECTION_PATTERNS.sub("[filtered]", cleaned)
    cleaned = cleaned.replace("\n", " ").strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned
