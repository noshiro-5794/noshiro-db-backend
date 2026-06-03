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

## Update My Comment

```bash
COMMENT_ID=1

curl -s -X PATCH "$BASE_URL/api/community/comments/$COMMENT_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated comment.",
    "visibility": "public",
    "is_spoiler": false
  }' | jq
```

Only the author can update a comment. Locked or hidden comments cannot be updated by the author.

## Delete My Comment

```bash
curl -s -X DELETE "$BASE_URL/api/community/comments/$COMMENT_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.

Locked or hidden comments cannot be deleted by the author.

## Staff Moderate Comment

Requires staff user.

```bash
curl -s -X PATCH "$BASE_URL/api/community/staff/comments/$COMMENT_ID/moderation/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "lock",
    "reason": "Moderation reason."
  }' | jq
```

Supported action types:

```text
hide
lock
```

`hide` removes the comment from public lists and hides related comment activity. `lock` prevents edits and replies.
