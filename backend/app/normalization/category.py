"""Category normalization."""

from app.schemas.common import Category

_CAP_CATEGORY_MAP: dict[str, Category] = {
    "met": Category.WEATHER,
    "geo": Category.EARTHQUAKE,
    "safety": Category.CIVIL,
    "security": Category.CIVIL,
    "rescue": Category.CIVIL,
    "fire": Category.WILDFIRE,
    "health": Category.HEALTH,
    "env": Category.ENVIRONMENTAL,
    "transport": Category.INFRASTRUCTURE,
    "infra": Category.INFRASTRUCTURE,
    "cbrne": Category.ENVIRONMENTAL,
}

_GDACS_EVENT_TYPE_MAP: dict[str, Category] = {
    "eq": Category.EARTHQUAKE,
    "tc": Category.WEATHER,
    "fl": Category.FLOOD,
    "vo": Category.VOLCANO,
    "wf": Category.WILDFIRE,
    "dr": Category.ENVIRONMENTAL,
    "ts": Category.TSUNAMI,
}

_EVENT_KEYWORD_MAP: list[tuple[str, Category]] = [
    ("flood", Category.FLOOD),
    ("tsunami", Category.TSUNAMI),
    ("earthquake", Category.EARTHQUAKE),
    ("volcano", Category.VOLCANO),
    ("wildfire", Category.WILDFIRE),
    ("fire", Category.WILDFIRE),
    ("tornado", Category.WEATHER),
    ("thunderstorm", Category.WEATHER),
    ("hurricane", Category.WEATHER),
    ("cyclone", Category.WEATHER),
    ("storm", Category.WEATHER),
    ("heat", Category.WEATHER),
    ("wind", Category.WEATHER),
    ("snow", Category.WEATHER),
    ("winter", Category.WEATHER),
    ("frost", Category.WEATHER),
    ("water", Category.HEALTH),
    ("health", Category.HEALTH),
    ("evacuation", Category.CIVIL),
    ("civil", Category.CIVIL),
]


def normalize_cap_category(value: str | None) -> Category:
    if not value:
        return Category.OTHER
    return _CAP_CATEGORY_MAP.get(value.strip().lower(), Category.OTHER)


def normalize_gdacs_event_type(event_type: str | None) -> Category:
    if not event_type:
        return Category.OTHER
    return _GDACS_EVENT_TYPE_MAP.get(event_type.strip().lower(), Category.OTHER)


def normalize_event_name(event_name: str | None) -> Category:
    if not event_name:
        return Category.OTHER
    lower = event_name.lower()
    for keyword, category in _EVENT_KEYWORD_MAP:
        if keyword in lower:
            return category
    return Category.OTHER


def normalize_nina_event_code(event_code: str | None) -> Category:
    if not event_code:
        return Category.OTHER
    code = event_code.upper()
    if "FLOOD" in code or "FLD" in code:
        return Category.FLOOD
    if "FIRE" in code or "WF" in code:
        return Category.WILDFIRE
    if "WATER" in code or "HEALTH" in code:
        return Category.HEALTH
    if "STORM" in code or "WEATHER" in code or "DWD" in code:
        return Category.WEATHER
    if "EVAC" in code or "CIVIL" in code or "MOWAS" in code:
        return Category.CIVIL
    return Category.OTHER
