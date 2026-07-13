# Deployment — Docker Compose

> **Status:** Phase 7 — container-only deployment (primary)

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- `.env` copied from `.env.example` with production values
- Reverse proxy / TLS: **your responsibility** (Traefik, nginx, Caddy, etc.)

## Quick Start

```bash
cp .env.example .env
# Set NOAA_USER_AGENT and NINA_USER_AGENT with a contact email

docker compose up -d --build
curl http://localhost:8000/health
curl http://localhost:3000
```

Default Compose settings (production-like):

- `DEMO_MODE=false` — live ingest from NINA, GDACS, NOAA
- `SCHEDULER_ENABLED=true` — automatic ingest + briefing every 15 minutes
- `LLM_ENABLED=false` — rule-based briefings only
- `LOG_FORMAT=json` — structured logs

The scheduler runs the first ingest ~30s after backend start. No manual CLI needed for normal operation.

## Required Ports

| Service | Port | Purpose |
|---------|------|---------|
| `frontend` | **3000** | Dashboard (browser) |
| `backend` | **8000** | REST API + `/health` |
| `postgres` | 5432 (dev only) | Database — **do not expose in production** |

When placing a reverse proxy in front of the stack, route public traffic to ports 3000 (app) and 8000 (API). Configure TLS and admin-route protection on your proxy — this project does not ship Traefik configuration.

## Environment Variables (production)

```env
DEMO_MODE=false
SOURCES_LIVE=nina,gdacs,noaa
NOAA_USER_AGENT=GlobalRiskIntelligence/1.0 (your-contact@example.com)
NINA_USER_AGENT=GlobalRiskIntelligence/1.0 (your-contact@example.com)
NINA_FALLBACK_TO_FIXTURES=false
LLM_ENABLED=false
ADMIN_TOKEN=<random-32+-char-token>
LOG_LEVEL=INFO
LOG_FORMAT=json
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
```

## Services

| Service | Port (dev) | Healthcheck |
|---------|------------|-------------|
| `postgres` | 5432 | `pg_isready` |
| `backend` | 8000 | `GET /health` |
| `frontend` | 3000 | `GET /` |

Postgres should **not** be published on a public host port in production. Remove the `ports:` mapping and keep DB access on the Docker network only.

## Reverse Proxy (user-managed)

This repository exposes plain HTTP on 3000/8000. For production:

1. Run your preferred reverse proxy (Traefik, nginx, Caddy, …)
2. Point it at `frontend:3000` and `backend:8000` on the Docker network
3. Terminate TLS at the proxy
4. Restrict `/api/v1/admin/*` to trusted IPs or VPN
5. Set `FRONTEND_URL` and `NEXT_PUBLIC_API_URL` to your public URLs

No Traefik labels or config are included in `docker-compose.yml`.

## Scheduled Ingest

### Built-in scheduler (default)

```env
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
SCHEDULER_STARTUP_DELAY_SECONDS=30
```

### External scheduler (optional)

Disable the built-in scheduler and use cron, systemd, or n8n — see [docs/n8n-integration.md](n8n-integration.md). **n8n is not required** when the built-in scheduler is active.

```bash
docker compose exec -T backend python -m app.jobs.cli ingest
```

| Source | Minimum interval | Rationale |
|--------|------------------|-----------|
| NOAA | 30–60s | Cache max-age=5, rate-limit caution |
| NINA | 60–120s | Detail fetches per alert |
| GDACS | 300s | Slower event evolution |

For MVP, `INGEST_INTERVAL_MINUTES=15` is a safe default.

## Migrations

Alembic migrations run automatically on backend container start via `docker-entrypoint.sh`:

```bash
docker compose exec backend alembic upgrade head
```

## Health & Monitoring

### Public health

```bash
curl http://localhost:8000/health
```

Returns: `status`, `demo_mode`, `scheduler` state, `last_ingest_at`, `last_ingest_status`, `last_ingest_error`, `alert_counts` by source, `active_alert_count`.

Status is `degraded` when the database is down, the last ingest failed, or the scheduler reported an error.

### Admin status (detailed)

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:8000/api/v1/admin/status
```

Returns: recent ingest runs, per-source health/errors, scheduler next-run estimate, fixture vs live metrics.

### CLI health

```bash
docker compose exec backend python -m app.jobs.cli health
docker compose ps
```

### Logs

Structured JSON logs (default):

```bash
docker compose logs -f backend
```

Set `LOG_LEVEL=DEBUG` or `LOG_FORMAT=text` for human-readable dev output.

## Rebuild After Code Changes

```bash
docker compose up -d --build
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Map shows old demo alerts | `DEMO_MODE` must be `false`; restart backend to purge fixtures; verify `/health` shows `demo_mode: false` |
| NOAA 403 | `NOAA_USER_AGENT` set with contact email |
| NINA empty | Seasonal; MoWaS feed may still have data |
| Ingest `partial` | One source failed — check `/api/v1/admin/status` or backend logs |
| Frontend can't reach API | `NEXT_PUBLIC_API_URL` (browser) vs `API_URL` (SSR in Docker) |
