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

Campaign execution is bounded. Discovery stores its provider cursor in
`parameters.discovery.next_cursor`; fetching and AI normalization process bounded
batches and the Celery task schedules the next step. Admin monitoring and controls
are exposed through:

```text
GET  /api/v1/operations/sync/
POST /api/v1/operations/sync/
GET  /api/v1/operations/sync/summary/
GET  /api/v1/operations/sync/{campaign_id}/
GET  /api/v1/operations/sync/{campaign_id}/items/
GET  /api/v1/operations/sync/{campaign_id}/claims/
POST /api/v1/operations/sync/{campaign_id}/pause/
POST /api/v1/operations/sync/{campaign_id}/resume/
POST /api/v1/operations/sync/{campaign_id}/cancel/
```

`GET /operations/sync/summary/` is the monitoring surface: campaign counts by
status and provider, stale worker leases (heartbeat expired), queued/failed work
items, and pending AI claims. `GET /operations/sync/{id}/claims/` paginates the
AI decision trail (claims with model/calibrated confidence, policy decision,
and linked observation/web evidence) for admin review.

`full` campaigns enumerate a provider catalog. `incremental` campaigns use the
AniList `updatedAt_greater` watermark when available. A provider without a
reliable delta feed must use periodic catalog reconciliation and compare stored
payload hashes; it must not guess an update frontier from numeric IDs.

VNDB and Bangumi expose no update-feed, so their incremental campaigns re-fetch
known active records and rely on payload-hash revisions to detect changes; new
records are discovered by periodic full campaigns. AniList uses a true
`updatedAt_greater` watermark walked in ascending `UPDATED_AT` order; the
watermark advances to the highest `updatedAt` observed, which closes the
moving-window gap instead of using wall-clock time. Incremental watermarks are
committed only after the campaign finishes successfully, and a truncated
discovery never advances the watermark.

Bangumi has no stable catalog enumeration endpoint: `GET /v0/subjects` requires
`type` and only sorts by `date` or `rank`, so its full campaign pages each
subject type and treats discovery as an approximate periodic reconciliation
that cannot be proven complete. Consequently Bangumi full campaigns do not mark
unseen records as `MISSING` by default; pass `reconcile_missing: true` in the
campaign parameters to opt in. VNDB/AniList full discoveries use stable ID
ordering plus the API's authoritative count/terminal page, so MISSING
reconciliation is enabled by default for them.

Production provider clients share a Redis-backed per-provider interval limiter.
429, 5xx, and transport failures carry retry metadata and use bounded exponential
backoff; validation and not-found errors are terminal. The in-process limiter is
only a local-development fallback when Redis is unavailable.

The default AI normalization mode processes every successful item in bounded
batches. `--ai-sample-size N` is an explicit shadow experiment cap. AI output is
an evidence-backed claim/proposal tied to an observation and cannot directly
overwrite canonical projections.

After normalization, campaigns run a bounded **enrichment** phase
(`AI_ENRICH_SAMPLE_SIZE`, default 200) that completes missing multilingual
titles/descriptions for sampled work entities. Enrichment is evidence-first:
`web.search`/`web.fetch` tools gather public pages, which are content-hashed
into `SourceArtifact` rows and linked through `ClaimEvidence`; every proposal is
persisted as an `AIClaim` with model confidence, evidence strength, and a
calibrated confidence. Title names are auto-applied only when
`AI_ENRICH_APPLY=true` (default false) and calibrated confidence clears
`AI_ENRICH_MIN_CONFIDENCE` (default 0.85); descriptions always remain
reviewable claims. Without a configured `WEB_SEARCH_API_KEY` the phase degrades
to model-only evidence instead of failing. `enrich_sample_size`,
`enrich_apply`, `enrich_min_confidence`, and `enrich_languages` can override the
settings per campaign in `parameters`.

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
