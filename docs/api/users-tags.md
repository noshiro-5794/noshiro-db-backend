# Tags API

Use [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Tags are user-owned labels. Adding a tag by name creates it automatically or reuses the existing tag with the same name.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/users/me/tags/` | List my tags. |
| `POST` | `/api/users/me/tags/` | Create or reuse a tag. |
| `PATCH` | `/api/users/me/tags/{tag_id}/` | Rename a tag. |
| `DELETE` | `/api/users/me/tags/{tag_id}/` | Delete a tag and its bindings. |
| `GET` | `/api/users/me/subjects/{subject_id}/tags/` | Read tags for a marked subject. |
| `PUT` | `/api/users/me/subjects/{subject_id}/tags/` | Replace tags for a marked subject. |

## List Tags

```bash
curl -s -X GET "$BASE_URL/api/users/me/tags/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Create Or Reuse Tag

```bash
curl -s -X POST "$BASE_URL/api/users/me/tags/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "favorite"
  }' | jq
```

## Replace Subject Tags

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X PUT "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/tags/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tag_names": ["favorite", "rewatch"]
  }' | jq
```

You can also use `tag_ids` when the frontend already has tag IDs:

```json
{
  "tag_ids": [1, 2]
}
```

## Rename Tag

```bash
TAG_ID=1

curl -s -X PATCH "$BASE_URL/api/users/me/tags/$TAG_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "favorites"
  }' | jq
```

## Delete Tag

```bash
curl -s -X DELETE "$BASE_URL/api/users/me/tags/$TAG_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```
