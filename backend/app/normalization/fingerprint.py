"""Alert fingerprint generation for deduplication."""

import hashlib
import re
from datetime import datetime

from app.schemas.common import Category, Severity
from app.schemas.common import AlertSource


def _normalize_title(title: str) -> str:
    lowered = title.lower().strip()
    return re.sub(r"\s+", " ", lowered)


def generate_fingerprint(
    source: AlertSource | str,
    source_alert_id: str,
    title: str,
    issued_at: datetime,
    severity: Severity | str,
    category: Category | str,
) -> str:
    issued_iso = issued_at.strftime("%Y-%m-%dT%H:%M:%SZ") if issued_at.tzinfo else issued_at.isoformat()
    payload = "|".join(
        [
            str(source),
            source_alert_id,
            _normalize_title(title),
            issued_iso,
            str(severity),
            str(category),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
