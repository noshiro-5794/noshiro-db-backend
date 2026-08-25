# Development

## Prerequisites

- uv `0.11.x`
- Python `3.13.14`
- PostgreSQL
- Redis when running Celery or shared-cache workflows
- MinIO when testing avatar workflows

SQLite is unsupported. Development and tests rely on PostgreSQL behavior.

## Setup

```bash
uv python install 3.13.14
uv sync --frozen
cp .env.example .env
uv run python src/manage.py bootstrap_database
uv run python src/manage.py migrate
uv run python src/manage.py check
uv run python src/manage.py runserver 0.0.0.0:8008
```

Create the databases configured in `.env` first. `TEST_DATABASE_URL` must point to a
dedicated database whose name ends in `_test`. `bootstrap_database` installs required
PostgreSQL extensions and must run before the first migration of a new database.

Run background processes only when the workflow needs them:

```bash
uv run celery --workdir src -A config.celery:app worker -l info
uv run celery --workdir src -A config.celery:app beat -l info
```

## Dependencies

`pyproject.toml` declares direct dependencies and `uv.lock` pins the complete graph.

```bash
uv add package-name
uv add --dev tool-name
uv lock --upgrade
uv sync --frozen
```

Commit `pyproject.toml` and `uv.lock` together. Do not add `requirements.txt` or a
second package manager.

## Provider Imports

```bash
uv run python src/manage.py full_sync
uv run python src/manage.py incremental_sync --status
uv run python src/manage.py sync_calendar
uv run python src/manage.py sync_subject --bangumi-id 123
uv run python src/manage.py sync_vndb v17
uv run python src/manage.py sync_vndb v17 --without-related
# Durable provider-wide sync; defaults to evidence-only AI shadow mode.
uv run python src/manage.py sync_campaign vndb --ai-mode shadow
uv run python src/manage.py sync_campaign anilist --ai-mode shadow --page-size 50
# Limit a rehearsal to a bounded number of imported records.
uv run python src/manage.py sync_campaign vndb --max-items 20 --ai-sample-size 20
```

`sync_campaign` is resumable and idempotent for the same provider, campaign type,
and parameters. Provider discovery and canonical imports remain deterministic;
`--ai-mode assisted` records reviewable claims, while `required` fails the campaign
when the configured AI contract cannot produce a usable result. AI never writes a
canonical field directly.

## API Contract

The only REST root is `/api/v1/`. OpenAPI is available at `/api/v1/openapi/` and its
interactive UI at `/api/docs/`. OpenAPI is the source of truth for endpoints and
schemas.

## Quality Gates

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
uv run python src/manage.py check
uv run python src/manage.py makemigrations --check --dry-run
uv run python src/manage.py spectacular --validate --fail-on-warn
```

Full tests require the dedicated PostgreSQL test database. All tests live in the
root `tests/` package, organized by app ownership, cross-app contracts, and
integrations; production `src/` contains runtime code only.

Regenerate the OpenAPI snapshot only for an intentional contract change:

```bash
uv run python src/manage.py spectacular \
  --format openapi-json \
  --validate \
  --fail-on-warn \
  --file tests/snapshots/openapi.json
```
