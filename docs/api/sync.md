# Sync API

Sync APIs are staff-only. Use [Auth](./users-auth.md) to set `ACCESS_TOKEN` for a staff user.

Most write APIs default to async Celery dispatch. Async responses include both a Celery `task_id` and a backend `job_id`.

Use `job_id` for frontend progress polling. `task_id` is mainly an internal Celery identifier.

## Incremental Status

```bash
curl -s -X GET "$BASE_URL/api/sync/incremental/status/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

This returns cursor and task status data for incremental sync tasks.

## Run Incremental Sync

```bash
curl -s -X POST "$BASE_URL/api/sync/incremental/run/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "run_async": true,
    "task_name": "incremental_subject",
    "batch_size": 10
  }' | jq
```

Supported task names:

```text
incremental_subject
incremental_episode
incremental_subject_subject_relation
incremental_subject_staff_relation
incremental_subject_character_relation
incremental_character
incremental_staff
```

Omit `task_name` to run all configured incremental tasks.

Async response shape:

```json
{
  "task_id": "celery-task-id",
  "job_id": "sync-job-uuid",
  "status": "queued"
}
```

## Run Calendar Sync

```bash
curl -s -X POST "$BASE_URL/api/sync/calendar/run/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "run_async": true,
    "sync_subject_details": true
  }' | jq
```

Calendar sync refreshes daily broadcast data. When `sync_subject_details=true`, related calendar subjects are also synchronized.

Synchronous result fields include `weekday_count`, `item_count`,
`synced_subject_count`, `failed_subject_count`, `detail_synced_count`, and
`detail_failed_count`.

## Resync One Subject

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X POST "$BASE_URL/api/sync/subjects/$SUBJECT_ID/resync/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "run_async": true
  }' | jq
```

Single-subject sync refreshes the subject, episodes, staff, characters, and direct relations. It does not recursively sync relation trees.

## Sync Jobs

List recent jobs:

```bash
curl -s -X GET "$BASE_URL/api/sync/jobs/?page=1&page_size=20" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Optional filters:

```text
status=queued|running|succeeded|failed
job_type=subject_bangumi|subject_resync|calendar|incremental
page=1..
page_size=1..64
```

Get one job:

```bash
JOB_ID="sync-job-uuid"

curl -s -X GET "$BASE_URL/api/sync/jobs/$JOB_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Job fields:

```text
status           queued / running / succeeded / failed
celery_task_id   Celery task identifier, useful for logs
parameters       request snapshot
result           final result when completed
error            failure message
current_label    current progress label
total_count      planned work count when known
processed_count  completed work count
synced_count     successful sync count
skipped_count    skipped count
failed_count     failed count
```

Celery workers do not scan the `sync_job` table. A job runs only when the API dispatches the corresponding Celery task.

## Local Command Equivalents

```bash
uv run python src/manage.py incremental_sync --status
uv run python src/manage.py incremental_sync --batch-size 10
uv run python src/manage.py sync_calendar
uv run python src/manage.py sync_subject --uuid "$SUBJECT_ID"
```
