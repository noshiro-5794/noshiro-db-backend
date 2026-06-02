# User Subjects API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

`UserSubject` is the current user's mark record for an anime or galgame subject.

## List My Subjects

```bash
curl -s -X GET "$BASE_URL/api/users/me/subjects/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Filters:

```text
status=doing|wish|done|on_hold|drop
subject_type=anime|galgame
keyword=...
ordering=-updated_at
```

## Create Or Update Subject Mark

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X POST "$BASE_URL/api/users/me/subjects/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "'"$SUBJECT_ID"'",
    "status": "doing",
    "simple_rating": 4,
    "rating": "8.0",
    "comment": "Watching.",
    "is_public": true
  }' | jq
```

The endpoint is idempotent for the same user and subject.

## Get Mark Detail

```bash
USER_SUBJECT_ID=1

curl -s -X GET "$BASE_URL/api/users/me/subjects/$USER_SUBJECT_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Update Mark Detail

```bash
curl -s -X PATCH "$BASE_URL/api/users/me/subjects/$USER_SUBJECT_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "done",
    "rating": "8.5",
    "comment": "Finished."
  }' | jq
```

## Delete Mark

```bash
curl -s -X DELETE "$BASE_URL/api/users/me/subjects/$USER_SUBJECT_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.

## Subject Context

Use this endpoint on authenticated subject detail pages:

```bash
curl -s -X GET "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/context/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

It returns:

```text
is_marked
user_subject
tags
rating_details
reviews
progress.finished_episode_ids
```

Frontend subject pages should prefer this subject UUID flow.
