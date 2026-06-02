# Community Relationships API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Blocks and mutes are private user relationships.

## Blocks

```bash
curl -s -X GET "$BASE_URL/api/community/me/blocks/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

```bash
TARGET_USER_ID=2

curl -s -X POST "$BASE_URL/api/community/me/blocks/$TARGET_USER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

```bash
curl -s -X DELETE "$BASE_URL/api/community/me/blocks/$TARGET_USER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Blocking removes follow relations in both directions.

## Mutes

```bash
curl -s -X GET "$BASE_URL/api/community/me/mutes/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

```bash
curl -s -X POST "$BASE_URL/api/community/me/mutes/$TARGET_USER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

```bash
curl -s -X DELETE "$BASE_URL/api/community/me/mutes/$TARGET_USER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Muted users are hidden from the current user's feed.
