# Reviews API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Reviews are attached to the current user's marked subject.

## List My Reviews

```bash
curl -s -X GET "$BASE_URL/api/users/me/reviews/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Supported query params:

```text
keyword
ordering=created_at|-created_at|id|-id
```

## Create Review By Subject

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X POST "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/reviews/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Review title",
    "content": "Review content.",
    "is_public": true,
    "is_spoiler": false
  }' | jq
```

The subject must already be marked by the current user.

## Public Subject Reviews

```bash
curl -s -X GET "$BASE_URL/api/users/subjects/$SUBJECT_ID/reviews/?page=1&page_size=16" | jq
```

## Review Detail

```bash
REVIEW_ID=1

curl -s -X GET "$BASE_URL/api/users/reviews/$REVIEW_ID/" | jq
```

## Update My Review

```bash
curl -s -X PATCH "$BASE_URL/api/users/me/reviews/$REVIEW_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated review title",
    "content": "Updated review content.",
    "is_public": true,
    "is_spoiler": false
  }' | jq
```

## Delete My Review

```bash
curl -s -X DELETE "$BASE_URL/api/users/me/reviews/$REVIEW_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.
