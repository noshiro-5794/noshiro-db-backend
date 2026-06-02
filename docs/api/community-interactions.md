# Community Interactions API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

## Target Shape

```json
{
  "target_type": "post",
  "target_id": 1
}
```

Reaction targets:

```text
post
comment
review
collection
activity
```

Bookmark targets:

```text
post
review
collection
```

## React

```bash
curl -s -X POST "$BASE_URL/api/community/reactions/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "post",
    "target_id": 1,
    "reaction_type": "like"
  }' | jq
```

Supported `reaction_type` values:

```text
like
useful
agree
```

## Unreact

```bash
curl -s -X DELETE "$BASE_URL/api/community/reactions/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "post",
    "target_id": 1,
    "reaction_type": "like"
  }'
```

Returns `204 No Content`.

## Bookmark

```bash
curl -s -X POST "$BASE_URL/api/community/bookmarks/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "post",
    "target_id": 1
  }' | jq
```

## List My Bookmarks

```bash
curl -s -X GET "$BASE_URL/api/community/bookmarks/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Optional filter:

```text
target_type=post|review|collection
```

## Unbookmark

```bash
curl -s -X DELETE "$BASE_URL/api/community/bookmarks/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "post",
    "target_id": 1
  }'
```

Returns `204 No Content`.
