# Event Correlation (Phase 4)

> Cross-source canonical event correlation — rule-based, auditable, non-destructive.

## Overview

The correlation service links **alerts** (GDACS, NOAA, NINA) and **observed events** (USGS, EONET, FIRMS clusters, SWPC) into **canonical events** without deleting or modifying source records.

Source rows remain the system of record; canonical events are an aggregation layer for cross-source situational awareness.

## Tables

| Table | Purpose |
|-------|---------|
| `canonical_events` | Unified event (title, severity, geometry, time window, correlation metadata) |
| `canonical_event_links` | n:m links from canonical events to `alert` or `observed_event` members |

## Confidence Levels

| Level | `link_confidence` | Behavior |
|-------|-------------------|----------|
| **High** | `high` | Auto-merge: all members share one canonical event; event fields derived from primary member |
| **Medium** | `low` on secondary | Possible match only: primary gets/keeps canonical event; secondary linked with `possible_match` reason |
| **Low / none** | — | No link created |

### Scoring criteria (v1)

All of the following must pass before a pair is considered:

1. **Different sources** — no intra-source deduplication
2. **Compatible category** — same category or related (e.g. `weather` ↔ `flood`)
3. **Time proximity** — within `CORRELATION_TIME_WINDOW_HOURS` (default 24h)
4. **Geographic proximity** — haversine distance ≤ `CORRELATION_DISTANCE_KM` (default 150 km)

Bonus signals (increase confidence):

- Same category (+10)
- Matching `event_type` substring (+10)
- Title token overlap ≥ 25% (+15)
- Shared external IDs in `raw_payload` / `source_metadata` (+30)

Thresholds:

- **High** — score ≥ 70 → auto-merge
- **Medium** — score ≥ 50 → possible match link only

## Examples

### GDACS earthquake + USGS earthquake (high)

| Source | Category | Location | Time |
|--------|----------|----------|------|
| GDACS alert | `earthquake` | 35.1°N, 25.2°E | T+0 |
| USGS observed event | `earthquake` | 35.12°N, 25.18°E | T+0 |

→ One canonical event, two `high` links.

### GDACS tropical cyclone + EONET storm (high)

Same `weather` category, overlapping time/region, compatible `event_type` strings.

### FIRMS cluster + NOAA wildfire alert (medium)

Both `wildfire` or related categories, same region, overlapping time — may score medium if title/event_type signals are weak; secondary linked as `possible_match` with `link_confidence=low`.

## Operations

### CLI

```bash
cd backend
python -m app.jobs.cli correlate
```

### Admin API

```bash
curl -X POST http://localhost:8000/api/v1/admin/correlate-events \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

### Post-ingest hook

When `CORRELATION_AUTO_RUN=true` (default), correlation runs automatically after successful or partial ingest.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CORRELATION_TIME_WINDOW_HOURS` | `24` | Max hours between member `issued_at` timestamps |
| `CORRELATION_DISTANCE_KM` | `150` | Max haversine distance between member centroids |
| `CORRELATION_AUTO_RUN` | `true` | Run correlation after ingest |

## API (read-only)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/events` | List canonical events (filters: `event_type`, `severity`, `status`, `active`, `bounding_box`) |
| `GET /api/v1/events/{id}` | Detail with linked member summary |
| `GET /api/v1/events/{id}/sources` | Full linked alert and observed_event records |

## Design principles

- **Source records are never deleted** — only linked
- **Auditable** — `correlation_reason`, `link_reason`, `correlation_version` on every merge
- **Idempotent** — re-running correlation updates existing high-confidence groups
- **Conservative v1** — cross-source only; no aggressive deduplication

## Migration

Alembic revision `003_canonical_events` creates both tables with PostGIS GIST index on `canonical_events.geometry`.
