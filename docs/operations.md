# Operations

## Processes

API server:

```bash
./venv/bin/python manage.py runserver 0.0.0.0:8008
```

Celery worker:

```bash
celery -A config worker -l info
```

Celery Beat:

```bash
celery -A config beat -l info
```

Beat is required for scheduled sync jobs. Stop Beat before a large manual full sync if overlap is not desired.

## Docker Deployment

Create the environment file:

```bash
cp .env.production.example .env.production
```

Update `.env.production`:

```text
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
CORS_ALLOWED_ORIGINS
CSRF_TRUSTED_ORIGINS
DATABASE_URL
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
MINIO_ENDPOINT
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
RESEND_API_KEY
BANGUMI_API_KEY
AI_AGENT_API_KEY
```

Start the stack:

```bash
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production up -d --build
```

After code changes that affect Celery tasks or Django models, recreate all app containers:

```bash
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production up -d --build --force-recreate
```

View logs:

```bash
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production logs -f web
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production logs -f worker
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production logs -f beat
```

Run management commands:

```bash
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python manage.py check
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python manage.py migrate
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python manage.py sync_calendar
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python manage.py sync_subject --bangumi-id 515759
```

The `web` service runs migrations and `collectstatic` on startup. The `worker` and `beat` services share the same image and environment.

`docker-compose.app.yml` only starts:

```text
web
worker
beat
```

It connects to host services through `host.docker.internal`, which is mapped to the Linux Docker host by `extra_hosts`.

## Scheduled Sync

Default schedules:

```text
03:30 daily calendar sync
04:00 daily incremental sync
```

Relevant environment variables:

```text
SYNC_CALENDAR_CRON_HOUR
SYNC_CALENDAR_CRON_MINUTE
SYNC_INCREMENTAL_CRON_HOUR
SYNC_INCREMENTAL_CRON_MINUTE
SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE
SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS
SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS
```

## Management Commands

Full sync:

```bash
./venv/bin/python manage.py full_sync
```

Single subject sync:

```bash
./venv/bin/python manage.py sync_subject --uuid "$SUBJECT_ID"
./venv/bin/python manage.py sync_subject --bangumi-id 123
```

Incremental sync:

```bash
./venv/bin/python manage.py incremental_sync --status
./venv/bin/python manage.py incremental_sync --batch-size 10
./venv/bin/python manage.py incremental_sync --task incremental_subject --batch-size 10
```

Calendar sync:

```bash
./venv/bin/python manage.py sync_calendar
./venv/bin/python manage.py sync_calendar --skip-subject-details
```

## Staff Sync APIs

Staff-only endpoints:

```text
GET  /api/sync/incremental/status/
POST /api/sync/incremental/run/
POST /api/sync/calendar/run/
POST /api/sync/subjects/{subject_id}/resync/
```

Most sync API writes default to async Celery dispatch. Use `run_async=false` only for local debugging.

## Verification

Run before committing:

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py makemigrations --check --dry-run
```

Compile changed apps when useful:

```bash
./venv/bin/python -m compileall apps
```
