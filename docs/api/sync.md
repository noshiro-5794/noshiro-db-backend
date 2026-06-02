# Sync API

Sync APIs are staff-only. Use [Auth](./users-auth.md) to set `ACCESS_TOKEN` for a staff user.

Most write APIs default to async Celery dispatch.

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

## Local Command Equivalents

```bash
./venv/bin/python manage.py incremental_sync --status
./venv/bin/python manage.py incremental_sync --batch-size 10
./venv/bin/python manage.py sync_calendar
./venv/bin/python manage.py sync_subject --uuid "$SUBJECT_ID"
```
