# Consistency Audit — Global Risk Intelligence MVP

**Date:** 2026-07-16 (Phase 9 update)  
**Scope:** Ingest, stats, briefing, dashboard, map, fixtures vs live, showcase/events/exposure layer, retention, scheduler

## Summary

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Map showed "Hochwasserwarnung Saarland" (NINA fixture cluster) in July | `docker-compose.yml` had `DEMO_MODE=true`; stale fixture rows persisted in PostgreSQL from earlier demo ingests; public API returned all `is_active=true` rows | Default `DEMO_MODE=false`; startup + pre-ingest `deactivate_fixture_alerts()`; API/stats/briefing exclude fixtures when not in demo mode |
| January flood still **Aktiv** in July | `is_active` not reconciled when `expires_at < now()` | Expire deactivation on startup + pre-ingest + end of ingest; read-time effective-active filter |
| **Betroffene Regionen** showed only DE | Hotspot clustering hid sparse countries | Aggregate `affected_regions` by `country_code` |
| Stats vs map count mismatch (live mode) | Stats counted fixture rows still marked active | Fixture exclusion in `stats_service` when `demo_mode=false` |
| Briefing vs dashboard drift | Briefing snapshot could include fixture alerts | `_load_active_alerts()` excludes fixtures in live mode |
| Showcase vs live mixed counts | `SHOWCASE_MODE` loads curated fixtures alongside live | Showcase path bypasses live ingest; `/health` reports `showcase_mode`; UI disclaimer |
| Observed events DB growth | Append-only snapshots per ingest cycle | Retention cleanup deletes inactive rows older than `OBSERVED_EVENTS_RETENTION_DAYS` |
| All sources polled at same 15 min rate | Global scheduler | Per-source asyncio loops with `SOURCE_SCHEDULES` / `*_INTERVAL_MINUTES` |

## Consistency Matrix

| Layer | Active filter | Expired excluded | Fixture excluded (live) | Showcase handling | Timestamp handling | Source counts |
|-------|---------------|------------------|-------------------------|-------------------|-------------------|---------------|
| DB ingest | `_should_be_active()` + stale deactivation | `deactivate_expired_alerts()` | `deactivate_fixture_alerts()` when `demo_mode=false` | `showcase_service` when `showcase_mode=true` | UTC storage | Per-run in `IngestRun` |
| Observed events | `is_active` + stale deactivation | `ends_at < now` | Fixture via adapter mode | Showcase fixtures in `fixtures/showcase/` | UTC | Per-source in health |
| Canonical events | `is_active` + correlation rules | Linked member expiry | Excludes fixture alerts in live | Showcase scenarios seed events | UTC | `canonical_event_count` in health |
| Exposure | `active_only` in calculations | N/A | Static fixtures in `fixtures/exposure/` | Showcase exposure overlays | UTC | Per-event in API detail |
| `GET /api/v1/alerts` | `active` param + `expires_at >= now` | Yes when `active=true` | SQL filter when `demo_mode=false` | N/A | ISO UTC | N/A |
| `GET /api/v1/observed-events` | `active` filter | Yes | Adapter ingest_mode | Showcase labels | ISO UTC | N/A |
| `GET /api/v1/events` | `is_active` on canonical | Member expiry reflected | Fixture members excluded in live | Showcase filter available | ISO UTC | N/A |
| `GET /api/v1/stats` | effective-active | Yes | Yes when `demo_mode=false` | Event metrics when enabled | `last_ingest` from `IngestRun` | `by_source` sums to `active_count` |
| Briefing generation | Same as stats + evidence package | Yes | Yes when `demo_mode=false` | Observed events + exposure sections | `generated_at` UTC | `by_source` in snapshot |
| Dashboard home | Uses stats + alerts/events API | Yes | Yes (via API) | Showcase teaser when mode on | Relative + local display | Matches stats |
| Map layers | Client fetches active only | Yes (API) | Yes (API) | Layer toggle alerts/events/fire | Popup local | N/A |
| `GET /health` | Public active count | Effective-active | Fixture-excluded in live | `showcase_mode` flag | ISO timestamps | `alert_counts`, `observed_event_counts` |
| Retention cleanup | Deletes **inactive** only | N/A | N/A | N/A | `last_seen_at` cutoff | Deleted counts in logs |
| Per-source scheduler | Independent loops per `SOURCES_LIVE` source | Pre-ingest expired cleanup | Per-source stale deactivation | Disabled in showcase | Per-source `last_run_at` | `scheduler.per_source` in health |

## Fixture vs Live vs Showcase Separation

| Mechanism | When | Behavior |
|-----------|------|----------|
| `is_fixture_alert()` | Detection | `raw_payload._ingest_mode=fixture` OR `source_alert_id` contains `DEMO` |
| `deactivate_fixture_alerts()` | Startup + start of each ingest when `demo_mode=false` | Sets `is_active=false` on all fixture rows |
| API SQL filter | `demo_mode=false` | Hides fixture rows from public list/detail |
| `showcase_mode=true` | Startup pipeline | Loads `fixtures/showcase/` via `showcase_service`; skips live scheduler sources |
| `ingest_mode` field | All alert responses | `"live"` or `"fixture"` — frontend shows Demo/Live badge |
| Source adapters | `demo_mode=true` OR `*_USE_FIXTURES=true` OR not in `SOURCES_LIVE` | Fetch from `fixtures/` with refreshed datetimes |

## Ingest Pipeline (atomic flow)

```
startup → retention cleanup [if enabled]
       → deactivate_expired_alerts()
       → deactivate_fixture_alerts() [if demo_mode=false]
       → showcase ingest OR live ingest
per-source scheduler (each source in SOURCES_LIVE):
       → pre-ingest expired cleanup
       → run_ingest(sources=[source_id])
briefing scheduler (if SCHEDULER_GENERATE_BRIEFING):
       → generate_briefing()
retention scheduler (daily):
       → delete inactive alerts/events past retention window
```

Briefing runs on a separate global interval; per-source ingests do not each regenerate briefings.

## Docker Defaults (production-like)

```yaml
DEMO_MODE=false
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
NINA_FALLBACK_TO_FIXTURES=false
OBSERVED_EVENTS_RETENTION_DAYS=90
ALERTS_RETENTION_DAYS=30
RETENTION_CLEANUP_ENABLED=true
LOG_FORMAT=json
LOG_LEVEL=INFO
```

## Monitoring

| Endpoint | Auth | Fields |
|----------|------|--------|
| `GET /health` | Public | `status`, `demo_mode`, `showcase_mode`, `scheduler.per_source`, `last_ingest_at`, `alert_counts`, `observed_event_counts`, `canonical_event_count` |
| `GET /api/v1/admin/status` | `X-Admin-Token` | Ingest history, per-source errors, scheduler details, fixture vs live metrics |

## Tests

- `test_live_mode_api_excludes_fixture_alerts`
- `test_mock_live_ingest_populates_only_live_alerts`
- `test_deactivate_fixture_alerts_on_ingest`
- `test_startup_deactivates_fixture_alerts_when_live_mode`
- `test_health_reports_live_mode_metrics`
- `test_admin_status_with_token`
- `test_per_source_interval_from_env_var`
- `test_cleanup_deletes_old_inactive_alerts`
- `test_cleanup_deletes_old_inactive_observed_events`
- `test_security_headers_on_health`
- Prior: `test_ingest_deactivates_expired_alerts`, `test_affected_regions_lists_all_countries`, `test_briefing_internal_consistency_mixed_sources`
