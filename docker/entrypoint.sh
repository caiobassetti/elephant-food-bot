#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Starting web container…"

# Only wait for DB if Postgres (dev)
if [[ "${DATABASE_URL:-}" == postgresql* ]]; then
  DB_HOST="db"
  DB_PORT="5432"
  echo "[entrypoint] Waiting for Postgres at ${DB_HOST}:${DB_PORT}…"
  until nc -z "$DB_HOST" "$DB_PORT"; do
    echo "[entrypoint] Postgres not ready - sleeping"
    sleep 1
  done
fi

echo "[entrypoint] Running migrations…"
python /app/app/manage.py migrate --noinput

echo "[entrypoint] Starting gunicorn (WSGI)…"
exec python /app/app/manage.py runserver 0.0.0.0:8000
# exec gunicorn config.wsgi:application --chdir /app/app --bind 0.0.0.0:8000 --workers 1 --timeout 60
