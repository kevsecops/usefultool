#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
fi

docker compose up -d --build "$@"
echo "Waiting for services to become healthy..."
for i in {1..60}; do
  if docker compose ps --format json 2>/dev/null | grep -q '"Health":"healthy"'; then
    healthy=$(docker compose ps | grep -c healthy || true)
    if [[ "$healthy" -ge 3 ]]; then
      break
    fi
  fi
  sleep 2
done
docker compose ps
echo ""
echo "Frontend: http://localhost:3000"
echo "API:      http://localhost:8000"
echo "Ingest:   docker compose exec backend python -m app.jobs.cli ingest"
