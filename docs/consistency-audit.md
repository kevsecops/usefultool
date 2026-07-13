# Consistency Audit — Global Risk Intelligence MVP

**Date:** 2026-07-13  
**Scope:** Ingest, stats, briefing, dashboard API, fixtures, scheduler

## Summary

Two user-visible inconsistencies were traced to separate root causes:

| Symptom | Root cause | Fix |
|---------|------------|-----|
| January flood warning still **Aktiv** in July | `is_active` not reconciled when `expires_at < now()`; scheduler disabled so stale DB rows persisted; NINA fixture had static January dates | Expire deactivation on startup + pre-ingest + end of ingest; read-time effective-active filter; dynamic fixture datetimes |
| **Betroffene Regionen** showed only DE | `_affected_regions()` preferred hotspot clusters (≥3 alerts per sub-region); DE had 4 NINA alerts forming a cluster, hiding US/HN/PG/ID | Aggregate `affected_regions` by `country_code`, matching `top_countries` |

## Ingest

| Check | Status | Notes |
|-------|--------|-------|
| Expired alerts deactivated | Fixed | `deactivate_expired_alerts()` runs at startup, pre-ingest (scheduler), and start of `run_ingest()` |
| Stale feed alerts deactivated | OK | `_deactivate_stale_alerts()` when not in `seen_keys` |
| New/updated alerts respect expiry | Fixed | `_should_be_active()` — no `is_active=True` when canonical `expires_at` is past |
| Fixture vs live dedup | OK | Unique on `(source, source_alert_id)`; live ingest updates same row |
| Fixture dates | Fixed | `refresh_fixture_datetimes()` rewrites `sent`/`expires`/etc. relative to now |

## Stats API (`GET /api/v1/stats`)

| Check | Status | Notes |
|-------|--------|-------|
| `active_count` matches effective active | Fixed | Filters `is_active=true` **and** `expires_at >= now()` |
| Country/source breakdowns | OK | Same effective-active set as `active_count` |

## Briefing

| Check | Status | Notes |
|-------|--------|-------|
| Single snapshot | OK | `generate_briefing()` loads effective-active alerts once |
| `top_countries` vs `affected_regions` | Fixed | Both aggregate by `country_code` with matching counts |
| `by_source` vs `active_count` | OK | Sum of source counts equals `active_count` |
| `major_events` | OK | Top N by severity across all sources (severe/extreme preferred) |

## Dashboard / Frontend

| Check | Status | Notes |
|-------|--------|-------|
| Alert list `active=true` | Fixed | API excludes expired rows |
| Alert detail status | Fixed | `is_active` in response reflects effective status |
| Briefing panel | OK | Uses same briefing API snapshot |

## Source health

| Check | Status | Notes |
|-------|--------|-------|
| `last_fetch` timestamps | OK | Set on each adapter fetch (fixture or live) |
| `last_ingest` in stats | OK | `max(IngestRun.finished_at)` |

## Scheduler (Docker default)

```yaml
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
AUTO_GENERATE_BRIEFING=true
SCHEDULER_STARTUP_DELAY_SECONDS=30
```

First ingest runs ~30s after backend start; briefing auto-generated after each ingest. No manual `python -m app.jobs.cli` required for normal operation.

## Tests added

- `test_ingest_deactivates_expired_alerts`
- `test_fixture_dates_refreshed_on_ingest`
- `test_affected_regions_lists_all_countries`
- `test_briefing_internal_consistency_mixed_sources`
- `test_refresh_fixture_datetimes_rewrites_known_fields`
- `test_scheduler_enabled_via_env`
