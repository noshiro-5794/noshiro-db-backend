# Community Notifications API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

## List Notifications

```bash
curl -s -X GET "$BASE_URL/api/community/notifications/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Supported query params:

```text
unread_only=1
```

## Unread Count

```bash
curl -s -X GET "$BASE_URL/api/community/notifications/unread-count/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Mark One As Read

```bash
NOTIFICATION_ID=1

curl -s -X PATCH "$BASE_URL/api/community/notifications/$NOTIFICATION_ID/read/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Mark All As Read

```bash
curl -s -X POST "$BASE_URL/api/community/notifications/read-all/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```
