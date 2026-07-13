#!/bin/sh
set -e

echo "Waiting for database..."
until python -c "
import sys, time
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL', '')
for i in range(30):
    try:
        e = create_engine(url)
        with e.connect() as c:
            c.execute(text('SELECT 1'))
        sys.exit(0)
    except Exception:
        time.sleep(2)
sys.exit(1)
"; do
  echo "Database not ready, retrying..."
  sleep 2
done

echo "Running migrations..."
alembic upgrade head

exec "$@"
