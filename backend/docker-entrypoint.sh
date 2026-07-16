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

echo "Checking schema integrity..."
python -c "
import os, sys
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', '')
if not url:
    sys.exit(0)

engine = create_engine(url)
with engine.connect() as conn:
    has_version = conn.execute(text(
        \"SELECT EXISTS (SELECT 1 FROM information_schema.tables \"
        \"WHERE table_schema = 'public' AND table_name = 'alembic_version')\"
    )).scalar()
    has_alerts = conn.execute(text(
        \"SELECT EXISTS (SELECT 1 FROM information_schema.tables \"
        \"WHERE table_schema = 'public' AND table_name = 'alerts')\"
    )).scalar()
    if has_version and not has_alerts:
        print('Schema drift: alembic_version without tables (likely pytest drop_all). Resetting.')
        conn.execute(text('DELETE FROM alembic_version'))
        conn.commit()
"

echo "Ensuring test database exists..."
python -c "
import os
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', '')
if not url:
    raise SystemExit(0)

admin_url = url.rsplit('/', 1)[0] + '/postgres'
engine = create_engine(admin_url, isolation_level='AUTOCOMMIT')
with engine.connect() as conn:
    exists = conn.execute(text(
        \"SELECT 1 FROM pg_database WHERE datname = 'usefultool_test'\"
    )).scalar()
    if not exists:
        conn.execute(text('CREATE DATABASE usefultool_test'))
        print('Created database usefultool_test')
test_url = url.rsplit('/', 1)[0] + '/usefultool_test'
test_engine = create_engine(test_url)
with test_engine.connect() as conn:
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
    conn.commit()
"

echo "Running migrations..."
alembic upgrade head

exec "$@"
