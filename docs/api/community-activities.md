# Community Activities And Feed API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

`Activity` is displayable community feed content, not an audit log.

## My Activities

```bash
curl -s -X GET "$BASE_URL/api/community/me/activities/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Supported query params:

```text
activity_type
ordering=-created_at|created_at
```

## My Feed

```bash
curl -s -X GET "$BASE_URL/api/community/me/feed/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Include the current user's own activities:

```bash
curl -s -X GET "$BASE_URL/api/community/me/feed/?include_self=1&page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

The feed excludes muted users, blocked users, users who blocked the viewer, private activities, and hidden activities.

## Public User Activities

```bash
USER_ID=1

curl -s -X GET "$BASE_URL/api/community/users/$USER_ID/activities/?page=1&page_size=16" | jq
```

Public activity responses can include snapshots for subject, review, collection, post, comment, and target user.
