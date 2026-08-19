#!/bin/sh
set -e

celery --workdir /app/src -A config.celery:app inspect ping --timeout 5 | grep -q 'OK'
