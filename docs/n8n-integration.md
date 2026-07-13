# n8n Integration — Scheduled Ingest

> **Status:** Phase 7 — workflow template for production ingest scheduling

## Overview

n8n can trigger the ingest CLI on a schedule without modifying the application. The backend container exposes all ingest logic via:

```bash
python -m app.jobs.cli ingest
python -m app.jobs.cli health
python -m app.jobs.cli generate-briefing --type auto
```

## Prerequisites

- n8n instance with Docker socket access (or SSH access to the host)
- Global Risk Intelligence stack running (`docker compose up -d`)
- `ADMIN_TOKEN` configured (not required for ingest CLI, only API admin endpoints)

## Workflow: Scheduled Ingest

### Option A — Execute Command (Docker socket)

Use n8n **Execute Command** node:

```bash
docker compose -f /path/to/usefultool/docker-compose.yml exec -T backend python -m app.jobs.cli ingest
```

Schedule: every **2–5 minutes** (see interval recommendations below).

### Option B — HTTP Admin Endpoint

If you expose the admin API (with Traefik IP whitelist):

```
POST /api/v1/admin/ingest
Header: X-Admin-Token: <ADMIN_TOKEN>
```

Use n8n **HTTP Request** node with the admin token stored in n8n credentials.

### Option C — SSH to Host

```bash
cd /opt/usefultool && docker compose exec -T backend python -m app.jobs.cli ingest
```

## Recommended Schedule

| Workflow | Cron | Command |
|----------|------|---------|
| Full ingest (all sources) | `*/2 * * * *` | `ingest` (every 2 min) |
| Health check | `*/5 * * * *` | `health` |
| Briefing (rule-based) | `0 */6 * * *` | `generate-briefing --type rule_based` |

When `LLM_ENABLED=true`:

| Workflow | Cron | Command |
|----------|------|---------|
| LLM briefing | `0 */6 * * *` | `generate-briefing --type auto` |

## Example n8n Workflow (JSON outline)

```json
{
  "nodes": [
    {
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "parameters": {
        "rule": { "interval": [{ "field": "minutes", "minutesInterval": 2 }] }
      }
    },
    {
      "name": "Run Ingest",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "docker compose -f /opt/usefultool/docker-compose.yml exec -T backend python -m app.jobs.cli ingest"
      }
    },
    {
      "name": "Check Exit Code",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "number": [{ "value1": "={{ $json.exitCode }}", "operation": "notEqual", "value2": 0 }]
        }
      }
    }
  ]
}
```

## Error Handling

- Ingest returns exit code `1` when all sources fail (`status=failed`)
- Exit code `0` for `success` or `partial` (some sources succeeded)
- On `partial`, inspect ingest run errors via admin API or backend logs:

```bash
docker compose logs backend --tail 50
```

## Environment for Live Sources

Ensure the backend container has:

```env
DEMO_MODE=false
SOURCES_LIVE=nina,gdacs,noaa
NOAA_USER_AGENT=GlobalRiskIntelligence/1.0 (ops@yourdomain.com)
NINA_USER_AGENT=GlobalRiskIntelligence/1.0 (ops@yourdomain.com)
```

## Security Notes

- Do not store `LLM_API_KEY` in n8n unless using n8n encrypted credentials
- Restrict n8n Execute Command to trusted workflows only
- Prefer admin HTTP endpoint behind Traefik with IP whitelist over exposing Docker socket to n8n
