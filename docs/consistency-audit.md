# Consistency Audit — Global Risk Intelligence MVP

**Date:** 2026-07-13 (updated)  
**Scope:** Ingest, stats, briefing, dashboard, map, fixtures vs live, monitoring

## Summary

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Map showed "Hochwasserwarnung Saarland" (NINA fixture cluster) in July | `docker-compose.yml` had `DEMO_MODE=true`; stale fixture rows persisted in PostgreSQL from earlier demo ingests; public API returned all `is_active=true` rows | Default `DEMO_MODE=false`; startup + pre-ingest `deactivate_fixture_alerts()`; API/stats/briefing exclude fixtures when not in demo mode |
| January flood still **Aktiv** in July | `is_active` not reconciled when `expires_at < now()` | Expire deactivation on startup + pre-ingest + end of ingest; read-time effective-active filter |
| **Betroffene Regionen** showed only DE | Hotspot clustering hid sparse countries | Aggregate `affected_regions` by `country_code` |
| Stats vs map count mismatch (live mode) | Stats counted fixture rows still marked active | Fixture exclusion in `stats_service` when `demo_mode=false` |
| Briefing vs dashboard drift | Briefing snapshot could include fixture alerts | `_load_active_alerts()` excludes fixtures in live mode |

## Consistency Matrix

| Layer | Active filter | Expired excluded | Fixture excluded (live) | Timestamp handling | Source counts |
|-------|---------------|------------------|-------------------------|-------------------|---------------|
| DB ingest | `_should_be_active()` + stale deactivation | `deactivate_expired_alerts()` | `deactivate_fixture_alerts()` when `demo_mode=false` | UTC storage (`DateTime(timezone=True)`) | Per-run in `IngestRun` |
| `GET /api/v1/alerts` | `active` param + `expires_at >= now` | Yes when `active=true` | SQL filter when `demo_mode=false` | ISO UTC in JSON; frontend `toLocaleString()` | N/A (list) |
| `GET /api/v1/stats` | `is_active` + effective-active | Yes | Yes when `demo_mode=false` | `last_ingest` from `IngestRun` | `by_source` sums to `active_count` |
| Briefing generation | Same as stats | Yes | Yes when `demo_mode=false` | `generated_at` UTC | `by_source` in snapshot |
| Dashboard home | Uses stats + alerts API | Yes | Yes (via API) | Relative + local display | Matches stats `by_source` |
| Map (`/alerts?active=true`) | Client fetches active only | Yes (API) | Yes (API) | Popup/detail local | N/A |
| `GET /health` | Public active count | Effective-active | Fixture-excluded in live | ISO timestamps | `alert_counts` by source |
| `GET /api/v1/admin/status` | Metrics block | Same rules | Reports `fixture_alert_count` | Full ingest history | Per-source health |

## Fixture vs Live Separation

| Mechanism | When | Behavior |
|-----------|------|----------|
| `is_fixture_alert()` | Detection | `raw_payload._ingest_mode=fixture` OR `source_alert_id` contains `DEMO` |
| `deactivate_fixture_alerts()` | Startup + start of each ingest when `demo_mode=false` | Sets `is_active=false` on all fixture rows |
| API SQL filter | `demo_mode=false` | Hides fixture rows from public list/detail |
| `ingest_mode` field | All alert responses | `"live"` or `"fixture"` — frontend shows Demo/Live badge |
| Source adapters | `demo_mode=true` OR `*_USE_FIXTURES=true` | Fetch from `fixtures/` with refreshed datetimes |

## Ingest Pipeline (atomic flow)

```
startup → deactivate_expired_alerts()
       → deactivate_fixture_alerts() [if demo_mode=false]
scheduler → pre-ingest expired cleanup
         → run_ingest()
              → deactivate_fixture_alerts() [if demo_mode=false]
              → fetch/upsert per source
              → deactivate stale + expired
              → persist IngestRun
              → generate_briefing() [if enabled]
```

Briefing is generated in the same DB transaction flush cycle as ingest completion, using the same effective-active + fixture-filtered alert set as stats.

## Docker Defaults (production-like)

```yaml
DEMO_MODE=false
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
NINA_FALLBACK_TO_FIXTURES=false
LOG_FORMAT=json
LOG_LEVEL=INFO
```

## Monitoring

| Endpoint | Auth | Fields |
|----------|------|--------|
| `GET /health` | Public | `status`, `demo_mode`, `scheduler`, `last_ingest_at`, `last_ingest_status`, `last_ingest_error`, `alert_counts`, `active_alert_count` |
| `GET /api/v1/admin/status` | `X-Admin-Token` | Ingest history, per-source errors, scheduler next-run estimate, fixture vs live metrics |

## Tests

- `test_live_mode_api_excludes_fixture_alerts`
- `test_mock_live_ingest_populates_only_live_alerts`
- `test_deactivate_fixture_alerts_on_ingest`
- `test_startup_deactivates_fixture_alerts_when_live_mode`
- `test_health_reports_live_mode_metrics`
- `test_admin_status_with_token`
- Prior: `test_ingest_deactivates_expired_alerts`, `test_affected_regions_lists_all_countries`, `test_briefing_internal_consistency_mixed_sources`
