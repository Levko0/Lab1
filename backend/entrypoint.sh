#!/bin/sh
set -e

if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

PORT="${PORT:-8000}"

# If default uvicorn command is invoked, honor the PORT environment variable (Cloud Run contract)
if [ "$1" = "uvicorn" ]; then
  echo "Starting FastAPI on port ${PORT}..."
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi

exec "$@"

