# Community Comments API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Generic comments support these targets:

```text
post
review
collection
activity
```

## List Comments

```bash
curl -s -X GET "$BASE_URL/api/community/comments/?target_type=post&target_id=1&page=1&page_size=16" | jq
```

Authenticated responses include:

```json
{
  "viewer_state": {
    "has_liked": false,
    "is_following_author": false
  }
}
```

## Create Comment

```bash
curl -s -X POST "$BASE_URL/api/community/comments/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "review",
    "target_id": 1,
    "content": "I agree with this review.",
    "visibility": "public",
    "is_spoiler": false
  }' | jq
```

## Reply

```bash
curl -s -X POST "$BASE_URL/api/community/comments/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "post",
    "target_id": 1,
    "parent_id": 10,
    "content": "Reply content."
  }' | jq
```

`parent_id` must belong to the same target.
