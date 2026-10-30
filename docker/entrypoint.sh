#!/bin/sh
# Container entrypoint: wait for the database, create tables, optionally add demo data, then run the command.
set -e
cd "/app/services/${SERVICE}"
export PYTHONPATH=/app/shared
python /app/docker/wait_for.py
if [ "${MIGRATE:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi
if [ "${SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo
fi
exec "$@"
