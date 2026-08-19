# Noshiro DB Backend

Noshiro DB Backend is the Django REST backend for a source-neutral anime and galgame
knowledge base, personal library, and community. Bangumi and VNDB are peer providers;
canonical knowledge uses stable Entity UUIDs and retains provider evidence.

## Stack

- Python 3.13 and uv
- Django 5.2 and Django REST Framework
- PostgreSQL
- Redis, Celery, and Celery Beat
- MinIO

The only public REST root is `/api/v1/`. OpenAPI is served at
`/api/v1/openapi/` and interactive documentation at `/api/docs/`.

## Repository

```text
src/
  apps/          domain applications
  config/        Django, URL, and Celery configuration
  integrations/  provider-neutral external adapters
  shared/        app-neutral framework utilities
docker/          container entrypoint
docs/            architecture, development, and deployment guides
tests/           cross-app contracts and integration tests
```

Every app uses the same API layers:

```text
api/urls.py
api/serializers/
api/views/
```

Domain complexity may change the number of resource modules, but not their layer
semantics.

## Local Development

```bash
uv python install 3.13.14
uv sync --frozen
cp .env.example .env
uv run python src/manage.py bootstrap_database
uv run python src/manage.py migrate
uv run python src/manage.py runserver 0.0.0.0:8008
```

PostgreSQL is required; SQLite is unsupported. `TEST_DATABASE_URL` must point to a
dedicated PostgreSQL database whose name ends in `_test`.

Run the release gates:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
uv run python src/manage.py check
uv run python src/manage.py makemigrations --check --dry-run
uv run python src/manage.py spectacular --validate --fail-on-warn
```

## Documentation

- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Production deployment](docs/deployment.md)

The knowledge migration is not approved for production until the backup restore,
checkpointed backfill, idempotency, and reconciliation gates pass. See the migration
section of the deployment guide before changing production schema or data.

## License

This project is licensed under the [MIT License](LICENSE).
