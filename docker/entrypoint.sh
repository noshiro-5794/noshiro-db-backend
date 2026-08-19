#!/bin/sh
set -e

if [ "${COLLECT_STATIC:-false}" = "true" ]; then
  python /app/src/manage.py collectstatic --noinput
fi

exec "$@"
