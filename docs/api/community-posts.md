# Community Posts API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Posts are short community updates. A post can be general or attached to a subject.

## List Posts

```bash
curl -s -X GET "$BASE_URL/api/community/posts/?page=1&page_size=16" | jq
```

Supported query params:

```text
subject_id
keyword
ordering=-last_activity_at|last_activity_at|-created_at|created_at|-reaction_count|reaction_count|-reply_count|reply_count
```

Authenticated requests include `viewer_state` and hide content from blocked or muted users.

## Create Post

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X POST "$BASE_URL/api/community/posts/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "'"$SUBJECT_ID"'",
    "content": "Thoughts about this subject.",
    "visibility": "public",
    "is_spoiler": false,
    "is_nsfw": false
  }' | jq
```

## Post Detail

```bash
POST_ID=1

curl -s -X GET "$BASE_URL/api/community/posts/$POST_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Update My Post

```bash
curl -s -X PATCH "$BASE_URL/api/community/posts/$POST_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated post content.",
    "visibility": "public",
    "is_spoiler": false,
    "is_nsfw": false
  }' | jq
```

Only the author can update a post. Locked or hidden posts cannot be updated by the author.

## Delete My Post

```bash
curl -s -X DELETE "$BASE_URL/api/community/posts/$POST_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.

Locked or hidden posts cannot be deleted by the author.

## Post Comments

```bash
curl -s -X GET "$BASE_URL/api/community/posts/$POST_ID/comments/?page=1&page_size=16" | jq
```

```bash
curl -s -X POST "$BASE_URL/api/community/posts/$POST_ID/comments/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Comment content.",
    "visibility": "public",
    "is_spoiler": false
  }' | jq
```

Locked posts cannot receive new comments.

## Staff Moderate Post

Requires staff user.

```bash
curl -s -X PATCH "$BASE_URL/api/community/staff/posts/$POST_ID/moderation/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "hide",
    "reason": "Moderation reason."
  }' | jq
```

Supported action types:

```text
hide
lock
```

`hide` removes the post from public lists/detail and hides related post activity. `lock` prevents author edits and new comments.
