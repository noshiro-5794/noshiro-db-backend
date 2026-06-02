# Community Follows API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

## Follow User

```bash
TARGET_USER_ID=2

curl -s -X POST "$BASE_URL/api/community/me/following/$TARGET_USER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Following creates a community activity and a notification for the target user.

## Unfollow User

```bash
curl -s -X DELETE "$BASE_URL/api/community/me/following/$TARGET_USER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.

## My Following

```bash
curl -s -X GET "$BASE_URL/api/community/me/following/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## My Followers

```bash
curl -s -X GET "$BASE_URL/api/community/me/followers/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Public User Following

```bash
USER_ID=1

curl -s -X GET "$BASE_URL/api/community/users/$USER_ID/following/?page=1&page_size=16" | jq
```

## Public User Followers

```bash
curl -s -X GET "$BASE_URL/api/community/users/$USER_ID/followers/?page=1&page_size=16" | jq
```

Blocked users cannot follow each other.
