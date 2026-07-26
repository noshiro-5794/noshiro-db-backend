# Noshiro DB Backend

Noshiro DB Backend is a Django REST backend for an anime and galgame catalog and community product.

It provides catalog search and detail APIs, user account and library APIs, community interaction APIs, Bangumi synchronization, JWT cookie refresh authentication, avatar storage through MinIO, and staff-only sync controls.

## Status

The backend is ready for frontend integration.

Implemented modules:

- `users`: authentication, profile, settings, avatar upload, personal library, episode progress, tags, rating details, reviews, collections, and public user pages.
- `community`: posts, comments, follows, activities/feed, reactions, bookmarks, notifications, reports, blocks, and mutes.
- `index`: subject search, detail, episodes, staff, characters, relations, and daily anime calendar.
- `sync`: Bangumi provider integration, full sync commands, incremental sync, calendar sync, single-subject resync, Celery tasks, and staff sync APIs.

## Stack

- Python 3.13.14
- Django 5.2
- Django REST Framework
- PostgreSQL
- Redis
- Celery / Celery Beat
- MinIO
- SimpleJWT

## Structure

```text
src/
  manage.py   Django management entrypoint
  apps/
    users/      accounts, profiles, user library, reviews, collections
    community/  social graph, activities, posts, comments, interactions
    index/      public catalog models and APIs
    sync/       Bangumi providers, sync services, management commands, tasks
  config/
    settings/   base and environment-specific Django settings
  shared/
    api/        shared API responses, pagination, and exception handling
  integrations/
    storage/    shared object-storage adapters
docker/       container entrypoint
docs/
  api/          frontend-facing API documentation
```

Layering convention:

```text
api/views         HTTP boundary only
api/serializers   request validation and response shape
selectors         read/query logic
services          write/business logic
tasks             Celery task wrappers
providers         external service clients
```

## Local Setup

Install uv 0.11.31, then install the project Python version and create the
locked environment:

```bash
uv python install 3.13.14
uv sync --frozen
```

`pyproject.toml` declares direct dependencies and `uv.lock` pins the complete
dependency graph. Commit both files whenever dependencies change.

Dependency workflow:

```bash
uv add package-name
uv add --dev tool-name
uv lock --upgrade
uv sync --frozen
```

Application commands run through `uv run`; manually activating `.venv` is not
required.

Create `.env`:

```bash
cp .env.example .env
```

`TEST_DATABASE_URL` must point to a dedicated PostgreSQL database whose name
ends with `_test`. The configured role must be able to create and drop that
test database when pytest starts and finishes.

Run migrations:

```bash
uv run python src/manage.py migrate
```

The current migrations validate source identities, community target invariants,
sync counters, and legacy watch-date strings before changing constraints or
column types. A validation failure lists the affected row IDs and leaves the
data unchanged.

Start the API server:

```bash
uv run python src/manage.py runserver 0.0.0.0:8008
```

## Runtime Processes

For local development, run the processes you need in separate terminals or tmux panes.

API:

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

Beat enables scheduled jobs. Stop Beat before running large manual full sync operations if you want to avoid overlap with scheduled sync.

Default scheduled jobs:

```text
03:30 daily calendar sync
04:00 daily incremental sync
```

## Docker Deployment

This deployment mode assumes PostgreSQL, Redis, and MinIO are already running on the server.

Create a production environment file:

```bash
cp .env.production.example .env.production
```

Edit `.env.production` with real secrets, domains, MinIO credentials, and API
keys. Production settings fail fast when PostgreSQL, Redis cache, Celery,
Resend, secure refresh cookies, or MinIO are not configured. Then build and
start:

```bash
ENV_FILE=.env.production docker compose -f docker-compose.app.yml --env-file .env.production up -d --build
```

The compose stack starts:

```text
web      Django served by Gunicorn on WEB_PORT, default 8008
worker   Celery worker
beat     Celery Beat scheduled jobs
```

For production, put Nginx or Caddy in front of `web` and forward HTTPS requests with `X-Forwarded-Proto: https`.

## Verification

Run:

```bash
uv run ruff check .
uv run ruff format --check src tests
uv run pytest
uv run python src/manage.py check
uv run python src/manage.py makemigrations --check --dry-run
```

Compile changed apps when needed:

```bash
uv run python -m compileall src/apps src/config
```

## Documentation

Start with:

```text
docs/README.md
docs/api/README.md
```

The API documentation is written for frontend implementation and includes endpoint groups, response conventions, authentication behavior, and curl examples.

## Sync Commands

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

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE).
