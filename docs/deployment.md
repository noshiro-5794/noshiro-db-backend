# Deployment

Production uses two Compose projects:

```text
noshiro-infra  postgres, redis-broker, redis-cache, minio
noshiro-app    web, worker-realtime, worker-ai, worker-sync, beat, mcp
```

They share the `noshiro_net` Docker network. Application containers reach
infrastructure by service name instead of `host.docker.internal`.

## Configure

```bash
cp .env.production.example .env.production
```

Replace every placeholder. Validate allowed hosts, CORS and CSRF origins, secure
refresh cookies, PostgreSQL, Redis, MinIO, email, captcha, provider settings, and
timeouts. Never commit `.env.production` or put secrets in an image or Compose file.

Infrastructure images are pinned to avoid surprise minor-version drift:

- PostgreSQL `15.18-bookworm`
- Redis `7.4.10-alpine`
- MinIO `RELEASE.2025-09-07T16-13-09Z`

Persistent data is rooted at `NOSHIRO_DATA_ROOT`, for example
`/vol1/1000/noshiro-data`, with `postgres`, `redis-broker`, `redis-cache`, and `minio`
subdirectories. Backups use `NOSHIRO_BACKUP_ROOT`, for example
`/vol1/1000/noshiro-backup`.

## Operations Scripts

- `scripts/backup_postgres.sh` writes a custom-format PostgreSQL dump and checksum.
- `scripts/restore_postgres.sh` restores a custom-format dump into a target container.
- `scripts/backup_minio.sh` mirrors MinIO data and writes file checksums.
- `scripts/restore_minio.sh` mirrors a previous MinIO backup back into the data root.
- `scripts/rehearse_migrations.sh` restores a dump into a temporary PostgreSQL and runs migrations.
- `scripts/preflight.sh` validates Compose files, Django checks, migration drift, and readiness.

Before any database change, create backups and run the rehearsal script. The
production database is never the first environment to apply new migrations.

## Build And Start

Start infrastructure first:

```bash
ENV_FILE=.env.production docker compose \
  -f docker-compose.infra.yml \
  --env-file .env.production \
  up -d --build
```

Then start the application:

```bash
ENV_FILE=.env.production docker compose \
  -f docker-compose.app.yml \
  --env-file .env.production \
  up -d --build
```

The web container may collect static files but never runs migrations automatically.
Schema changes use an explicit one-off command after the migration rehearsal below.

## Verify

```bash
ENV_FILE=.env.production docker compose \
  -f docker-compose.app.yml \
  --env-file .env.production \
  ps

ENV_FILE=.env.production docker compose \
  -f docker-compose.app.yml \
  --env-file .env.production \
  exec web python /app/src/manage.py check

curl --fail --silent https://api.noshiro.moe/api/v1/openapi/ >/dev/null
```

Inspect web, queue-specific workers, and Beat logs. Verify authentication, one public
entity read, the OpenAPI contract, and one Celery job per queue.

## Database Changes

Use expand-contract migrations. Never use production as the first migration or
backfill environment.

Before a production database change:

1. Inspect `showmigrations index users community sync ai`.
2. Create a custom-format `pg_dump` and restore it to a temporary PostgreSQL database.
3. Apply migrations and run each backfill twice to verify idempotency.
4. Interrupt and resume large backfills from their stored checkpoints.
5. Reconcile entity, relation, and user-data counts against the source database.
6. Run the full PostgreSQL test suite and OpenAPI contract checks.

For a new empty database, install required extensions before the first migration:

```bash
python /app/src/manage.py bootstrap_database
python /app/src/manage.py migrate --noinput
```

After a successful rehearsal, stop Beat, workers, and other database writers. Take a
fresh backup, deploy the reviewed image, then run the one-off migration:

```bash
ENV_FILE=.env.production docker compose \
  -f docker-compose.app.yml \
  --env-file .env.production \
  run --rm web python /app/src/manage.py migrate --noinput
```

Run the rehearsed backfill and reconciliation before restarting services. Remove old
tables only in a later release after another restore rehearsal passes.

## Rollback

Application-only rollback uses the previous image. Never reverse a data migration
blindly; stop all writers before restoring a verified backup.
