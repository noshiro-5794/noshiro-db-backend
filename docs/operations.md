# Operations

## Processes

API server:

```bash
uv run python src/manage.py runserver 0.0.0.0:8008
```

Celery worker:

```bash
uv run celery --workdir src -A config.celery:app worker -l info
```

Celery Beat:

```bash
uv run celery --workdir src -A config.celery:app beat -l info
```

Beat is required for scheduled sync jobs. Stop Beat before a large manual full sync if overlap is not desired.

## Docker Deployment

Create the environment file:

```bash
cp .env.production.example .env.production
```

Update `.env.production`:

```text
# Required in production
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
CORS_ALLOWED_ORIGINS
CSRF_TRUSTED_ORIGINS
DATABASE_URL
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
CACHE_URL
MINIO_ENDPOINT
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
MINIO_BUCKET
MINIO_PUBLIC_URL
RESEND_API_KEY

# Optional provider credentials
BANGUMI_API_KEY
AI_AGENT_API_KEY
```

Production startup requires PostgreSQL and Redis cache, and rejects missing
Celery/Resend/MinIO configuration, `JWT_REFRESH_COOKIE_SECURE=False`, enabled
hCaptcha without a secret, and non-positive timeout or batch settings.

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
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python /app/src/manage.py check
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python /app/src/manage.py migrate
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python /app/src/manage.py sync_calendar
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production exec web python /app/src/manage.py sync_subject --bangumi-id 515759
```

The `web` service runs migrations and `collectstatic` on startup. The `worker` and `beat` services share the same image and environment.

Take the normal PostgreSQL backup before deploying migrations. Data-validation
migrations stop and report conflicting row IDs instead of deleting or guessing
how to repair existing records.

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
BANGUMI_RATE_LIMIT_INTERVAL
BANGUMI_IMAGE_ALLOWED_HOSTS
BANGUMI_IMAGE_MAX_BYTES
```

`BANGUMI_IMAGE_ALLOWED_HOSTS` is a comma-separated allowlist. Calendar cover
downloads reject other hosts, redirects, non-HTTP URLs, non-image responses,
and payloads larger than `BANGUMI_IMAGE_MAX_BYTES`.

## Management Commands

Full sync:

```bash
uv run python src/manage.py full_sync
```

Single subject sync:

```bash
uv run python src/manage.py sync_subject --uuid "$SUBJECT_ID"
uv run python src/manage.py sync_subject --bangumi-id 123
```

Incremental sync:

```bash
uv run python src/manage.py incremental_sync --status
uv run python src/manage.py incremental_sync --batch-size 10
uv run python src/manage.py incremental_sync --task incremental_subject --batch-size 10
```

Calendar sync:

```bash
uv run python src/manage.py sync_calendar
uv run python src/manage.py sync_calendar --skip-subject-details
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

Tests use the PostgreSQL database configured by `TEST_DATABASE_URL`. Its
database name must end with `_test`; never point it at a development or
production database.

Run before committing:

```bash
uv run ruff check .
uv run ruff format --check src tests
uv run pytest
uv run python src/manage.py check
uv run python src/manage.py makemigrations --check --dry-run
```

Compile changed apps when useful:

```bash
uv run python -m compileall src/apps src/config
```
