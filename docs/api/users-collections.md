# Collections API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Collections are user-owned public or private lists of marked subjects.

## List My Collections

```bash
curl -s -X GET "$BASE_URL/api/users/me/collections/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Supported query params:

```text
keyword
ordering
```

## Create Collection

```bash
curl -s -X POST "$BASE_URL/api/users/me/collections/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Favorites",
    "simple_rating": 5,
    "note": "Personal favorites.",
    "is_public": true
  }' | jq
```

## Collection Detail

```bash
COLLECTION_ID=1

curl -s -X GET "$BASE_URL/api/users/me/collections/$COLLECTION_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Update Collection

```bash
curl -s -X PATCH "$BASE_URL/api/users/me/collections/$COLLECTION_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated favorites",
    "note": "Updated note.",
    "is_public": true
  }' | jq
```

## List Items

```bash
curl -s -X GET "$BASE_URL/api/users/me/collections/$COLLECTION_ID/items/?page=1&page_size=16" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Add Item By Subject

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X POST "$BASE_URL/api/users/me/collections/$COLLECTION_ID/items/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "'"$SUBJECT_ID"'",
    "order": 1,
    "relation": "favorite"
  }' | jq
```

The subject must already be marked by the current user.

## Replace Items

```bash
curl -s -X PUT "$BASE_URL/api/users/me/collections/$COLLECTION_ID/items/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "subject_id": "'"$SUBJECT_ID"'",
        "order": 1,
        "relation": "favorite"
      }
    ]
  }' | jq
```

## Update Item

```bash
ITEM_ID=1

curl -s -X PATCH "$BASE_URL/api/users/me/collections/$COLLECTION_ID/items/$ITEM_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order": 2,
    "relation": "recommended"
  }' | jq
```

## Delete Item

```bash
curl -s -X DELETE "$BASE_URL/api/users/me/collections/$COLLECTION_ID/items/$ITEM_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.

## Delete Collection

```bash
curl -s -X DELETE "$BASE_URL/api/users/me/collections/$COLLECTION_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `204 No Content`.
