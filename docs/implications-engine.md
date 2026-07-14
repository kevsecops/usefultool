# Implications Engine (Phase 6)

> **Status:** Rule-based MVP — no LLM generation (Phase 7)

## Overview

The implications engine derives conservative **ImplicationCandidate** records from:

1. **Canonical events** and linked source records (alerts, observed events)
2. **Event asset exposures** from Phase 5 geospatial analysis
3. **Exposure assets** (ports, airports, power plants)

Output is persisted in `implication_candidates` and exposed via API and briefing snapshots.

## Evidence Levels

| Level | Meaning | Example |
|-------|---------|---------|
| `observed` | Factual data from source records | Magnitude, coordinates from USGS |
| `officially_reported` | Text from official alert/warning | Tsunami warning title from GDACS/NOAA |
| `inferred_from_exposure` | Asset in event geometry or system-level scope | Port inside storm polygon |
| `hypothesis` | Pattern-based, low confidence | Severe storm without exposure data |

## Categories

`logistics`, `economy`, `infrastructure`, `technology`, `energy`, `public_health`, `humanitarian`, `finance`

Briefing integration maps only the five briefing domains (`economy`, `logistics`, `infrastructure`, `technology`, `finance`). Other categories are stored and returned via the events API.

## Conservative Language Rules

### Allowed

- "Mögliche Beeinträchtigung regionaler Transportwege"
- "Potenzielle Belastung kritischer Infrastruktur"
- "Mögliche Beeinträchtigung technischer Systeme durch Weltraumwetter"

### Not Allowed

- "Häfen geschlossen"
- "Lieferkette bricht zusammen"
- Market/stock predictions
- Confirmed outages without operational status data

All generated titles are validated by `is_conservative_language()` before persistence.

## Rule Examples

### Storm + ports in polygon

- **Input:** Severe storm event with polygon geometry; ≥2 ports inside via `ST_Contains`
- **Output:** `logistics` implication, `confidence=medium`, `evidence_level=inferred_from_exposure`
- **Title:** "Mögliche Beeinträchtigung regionaler Transportwege"

### G4 geomagnetic storm

- **Input:** NOAA SWPC observed event with `potential_systems: [power_grid, satellite_operations]`
- **Output:** `technology` + `energy` implications, `system_level_exposure` on power plants
- **Evidence:** `inferred_from_exposure`

### Earthquake near airport

- **Input:** M6.5 earthquake; Haneda/Tokyo airport within heuristic radius
- **Output:** `logistics` and/or `infrastructure` implications referencing exposed airports

## Pipeline

```
canonical_event + links + exposures
        │
        ▼
  implications.py (rule_based)
        │
        ▼
  implication_service.py → implication_candidates table
        │
        ├── GET /api/v1/events/{id}/implications
        ├── POST /api/v1/admin/generate-implications
        └── rule_briefing → potential_implications + implication_refs
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPLICATIONS_AUTO_RUN` | `false` | Run after exposure calculation / correlation / ingest |

## CLI

```bash
python -m app.jobs.cli generate-implications
python -m app.jobs.cli generate-implications --event-id <UUID>
```

Typical workflow:

```bash
python -m app.jobs.cli import-exposure
python -m app.jobs.cli correlate
python -m app.jobs.cli calculate-exposure
python -m app.jobs.cli generate-implications
python -m app.jobs.cli generate-briefing
```

## API Examples

```bash
# Generate implications for all active events
curl -X POST http://localhost:8000/api/v1/admin/generate-implications \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"active_only": true}'

# List implications for an event
curl http://localhost:8000/api/v1/events/{event_id}/implications
```

## Briefing Integration

Rule-based briefings include:

- **`potential_implications`** — unchanged `dict[str, list[str]]` for backward compatibility
- **`implication_refs`** — new field with `{id, text, canonical_event_id, evidence_level}` per domain

Event-based implication titles are prepended to category-based fallback statements.

## Limitations

- **No LLM** — all candidates use `generated_by=rule_based`
- **No operational status** — exposure ≠ confirmed closure or damage
- **Demo assets only** — fixture ports/airports/power plants; not a global asset database
- **No assessments table** — `implication_candidates` is the primary MVP output
- **Regeneration replaces** — re-running deletes prior `rule_based` candidates for the event

## Engine Version

Current: `1` (see `ENGINE_VERSION` in `backend/app/analysis/implications.py`)
