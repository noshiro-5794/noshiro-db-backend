# Community Reports API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

## Report Target

Supported targets:

```text
post
comment
review
collection
activity
```

```bash
curl -s -X POST "$BASE_URL/api/community/reports/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "post",
    "target_id": 1,
    "reason": "spam",
    "description": "Report description."
  }' | jq
```

Supported reasons:

```text
spam
harassment
spoiler
illegal
other
```

## My Reports

```bash
curl -s -X GET "$BASE_URL/api/community/me/reports/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Staff Reports

Requires staff user.

```bash
curl -s -X GET "$BASE_URL/api/community/staff/reports/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Optional filter:

```text
status=pending|accepted|rejected
```

## Resolve Report

```bash
REPORT_ID=1

curl -s -X PATCH "$BASE_URL/api/community/staff/reports/$REPORT_ID/resolve/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "accepted",
    "action_type": "hide",
    "moderation_reason": "Reviewed by staff."
  }' | jq
```

Supported action types:

```text
hide
lock
delete
warn
mute
ban
```

For `post` and `comment` reports, `hide` and `lock` are executed immediately on the target content. Other action types are recorded as moderation actions for future handling.
