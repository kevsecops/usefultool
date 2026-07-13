# Deployment — Docker Compose & Traefik

> **Status:** Phase 7 — container-only deployment (primary)

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Domain names and TLS certificates (production with Traefik)
- `.env` copied from `.env.example` with production values

## Quick Start (Development)

```bash
cp .env.example .env
# Edit ADMIN_TOKEN, NOAA_USER_AGENT (required for live NOAA)

docker compose up -d --build
docker compose exec backend python -m app.jobs.cli ingest
curl http://localhost:8000/health
```

Default Compose settings:
- `DEMO_MODE=true` — fixture-based ingest (offline)
- `LLM_ENABLED=false` — rule-based briefings only
- `SOURCES_LIVE=nina,gdacs,noaa` — used when `DEMO_MODE=false`

## Live Ingest (Production)

Set in `.env` or override in `docker-compose.yml`:

```env
DEMO_MODE=false
SOURCES_LIVE=nina,gdacs,noaa
NOAA_USER_AGENT=GlobalRiskIntelligence/1.0 (your-contact@example.com)
NINA_USER_AGENT=GlobalRiskIntelligence/1.0 (your-contact@example.com)
LLM_ENABLED=false
ADMIN_TOKEN=<random-32+-char-token>
```

```bash
docker compose up -d --build
docker compose exec backend python -m app.jobs.cli ingest
docker compose exec backend python -m app.jobs.cli health
```

Per-source fallback (recommended for resilience):

```env
NINA_FALLBACK_TO_FIXTURES=true
GDACS_FALLBACK_TO_FIXTURES=true
NOAA_FALLBACK_TO_FIXTURES=true
```

## Services

| Service | Port (dev) | Healthcheck |
|---------|------------|-------------|
| `postgres` | 5432 | `pg_isready` |
| `backend` | 8000 | `GET /health` |
| `frontend` | 3000 | `GET /` |

Postgres should **not** be exposed on a public host port in production. Remove the `ports:` mapping and keep DB access on the Docker network only.

## Traefik Integration

`docker-compose.yml` includes commented Traefik labels on `backend` and `frontend`. To enable:

1. Add Traefik to your Compose stack or use an external Traefik instance on the same Docker network
2. Uncomment the `labels:` blocks on `backend` and `frontend`
3. Replace `api.example.com` / `app.example.com` with your domains
4. Connect services to the Traefik network:

```yaml
services:
  backend:
    networks:
      - default
      - traefik
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=traefik"
      - "traefik.http.routers.usefultool-api.rule=Host(`api.example.com`)"
      - "traefik.http.routers.usefultool-api.entrypoints=websecure"
      - "traefik.http.routers.usefultool-api.tls.certresolver=letsencrypt"
      - "traefik.http.services.usefultool-api.loadbalancer.server.port=8000"

networks:
  traefik:
    external: true
```

### Recommended Production Settings

| Setting | Value |
|---------|-------|
| TLS | Traefik `websecure` + Let's Encrypt |
| Admin routes | IP whitelist middleware on Traefik for `/api/v1/admin/*` |
| DB port | Not published |
| `DEMO_MODE` | `false` |
| `LLM_ENABLED` | `false` (enable only when LLM provider configured) |
| Log level | `INFO` or `WARNING` |

## Scheduled Ingest

### Option A — Built-in backend scheduler (container-friendly)

Enable in `.env` or `docker-compose.yml`:

```env
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
SCHEDULER_STARTUP_DELAY_SECONDS=30
```

The backend runs ingest (and optional briefing regeneration) on a loop inside the API container. Default interval: **15 minutes**. Disable with `SCHEDULER_ENABLED=false` (default).

### Option B — cron, systemd, or n8n

Use cron, systemd timer, or n8n workflow (see [docs/n8n-integration.md](n8n-integration.md)):

```bash
# Every 15 minutes (adjust per source rate limits)
docker compose exec -T backend python -m app.jobs.cli ingest
```

Recommended polling intervals (per-source minimums — full ingest should not run faster than the slowest constraint):

| Source | Minimum interval | Rationale |
|--------|------------------|-----------|
| NOAA | 30–60s | Cache max-age=5, rate-limit caution |
| NINA | 60–120s | Detail fetches per alert, cache max-age=10 |
| GDACS | 300s | Slower event evolution, 100-event cap |

For MVP container deployments, `INGEST_INTERVAL_MINUTES=15` is a safe default that respects all three sources.

## Migrations

Alembic migrations run automatically on backend container start via `docker-entrypoint.sh`. For manual runs:

```bash
docker compose exec backend alembic upgrade head
```

## Health Monitoring

```bash
# API + all source adapters
docker compose exec backend python -m app.jobs.cli health

# Container health
docker compose ps
```

## Rebuild After Code Changes

```bash
docker compose up -d --build
# or full no-cache:
docker compose build --no-cache && docker compose up -d
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| NOAA 403 | `NOAA_USER_AGENT` set with contact email |
| NINA empty | `dwd/mapData.json` may be empty seasonally; MoWaS should still return data |
| GDACS partial | `iscurrent=false` events are filtered |
| Ingest `partial` status | One source failed — check `run.errors` in ingest logs |
| Frontend can't reach API | `NEXT_PUBLIC_API_URL` (browser) vs `API_URL` (SSR in Docker) |
