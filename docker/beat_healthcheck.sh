#!/bin/sh
set -e

python /app/src/manage.py shell -c \
  "from django.core.cache import cache; assert cache.get('noshiro:beat:heartbeat')"
