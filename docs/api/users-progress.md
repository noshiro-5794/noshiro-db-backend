# Episode Progress API

Use [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Progress APIs are subject-scoped and use the public `subject_id` UUID.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/users/me/subjects/{subject_id}/episodes/progress/` | Read progress summary. |
| `PUT` | `/api/users/me/subjects/{subject_id}/episodes/progress/` | Replace finished episode IDs. |
| `PUT` | `/api/users/me/subjects/{subject_id}/episodes/{episode_id}/progress/` | Set one episode progress. |

## Read Progress

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X GET "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/episodes/progress/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Response data:

```text
user_subject_id
finished_count
finished_episode_ids
```

`user_subject_id` can be `null` until the subject is marked.

## Replace Progress

```bash
curl -s -X PUT "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/episodes/progress/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "finished_episode_ids": [722044, 722045]
  }' | jq
```

Updating progress can create the user mark if needed.

## Set One Episode

```bash
EPISODE_ID=722044

curl -s -X PUT "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/episodes/$EPISODE_ID/progress/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_finished": true
  }' | jq
```
