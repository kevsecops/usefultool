# n8n Integration — Optional Orchestration

> **Status:** Optional — not required when the built-in scheduler is active

## Primary path: built-in scheduler (MVP default)

The platform includes a **built-in ingest scheduler** (`SCHEDULER_ENABLED=true` in `docker-compose.yml`). It automatically:

1. Runs full ingest every `INGEST_INTERVAL_MINUTES` (default 15)
2. Deactivates expired and fixture-origin alerts (in live mode)
3. Regenerates the briefing when `SCHEDULER_GENERATE_BRIEFING=true`

**n8n is not required** when this scheduler is enabled. Data fetching, normalization, stats, and briefing are all handled inside the backend container.

## When to use n8n (optional)

Use n8n only if you already run it and want **external** orchestration beyond what the built-in scheduler provides:

| Use case | Why n8n |
|----------|---------|
| Visibility | Central workflow dashboard for ops teams |
| Notifications | Slack/email alerts after ingest completes or fails |
| Custom logic | Run briefing only when new alerts appear; branch on severity |
| System integration | Chain ingest with ticketing, PagerDuty, or other tools |
| Multi-environment | Trigger ingest across several deployments from one workflow |

n8n does **not** replace source adapters or normalization — it only triggers actions the platform already exposes.

## Trigger options

### Option A — HTTP Admin Endpoint (recommended for n8n)

```
POST /api/v1/admin/ingest
Header: X-Admin-Token: <ADMIN_TOKEN>
```

Check status afterward:

```
GET /api/v1/admin/status
Header: X-Admin-Token: <ADMIN_TOKEN>
```

### Option B — Execute Command (Docker socket)

```bash
docker compose -f /path/to/usefultool/docker-compose.yml exec -T backend python -m app.jobs.cli ingest
```

### Option C — SSH to host

```bash
cd /opt/usefultool && docker compose exec -T backend python -m app.jobs.cli ingest
```

## If using n8n alongside the built-in scheduler

Disable the built-in scheduler to avoid duplicate ingests:

```env
SCHEDULER_ENABLED=false
```

Then schedule n8n to call ingest every 15 minutes (respecting source rate limits — see [data-sources.md](data-sources.md)).

## Recommended n8n workflows

| Workflow | Cron | Command / HTTP |
|----------|------|----------------|
| Full ingest | `*/15 * * * *` | `POST /api/v1/admin/ingest` |
| Health check | `*/5 * * * *` | `GET /health` |
| Failure notification | On ingest error | Parse `last_ingest_error` from `/health` or `/api/v1/admin/status` |
| Briefing only | On demand | `POST /api/v1/admin/generate-briefing` |

When `SCHEDULER_GENERATE_BRIEFING=true`, briefing runs automatically after ingest — a separate n8n briefing workflow is usually unnecessary.

## Environment for live sources

```env
DEMO_MODE=false
SOURCES_LIVE=nina,gdacs,noaa
NOAA_USER_AGENT=GlobalRiskIntelligence/1.0 (ops@yourdomain.com)
NINA_USER_AGENT=GlobalRiskIntelligence/1.0 (ops@yourdomain.com)
```

## Security notes

- Store `ADMIN_TOKEN` in n8n encrypted credentials
- Do not expose Docker socket to n8n unless the host is fully trusted
- Restrict admin API access (firewall, reverse proxy ACLs) in production

## CLI reference (same operations n8n would trigger)

```bash
python -m app.jobs.cli ingest
python -m app.jobs.cli health
python -m app.jobs.cli generate-briefing --type auto
```
