# Public User Profiles API

Public user APIs do not require authentication. They only return public user content.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/users/{user_id}/profile/` | Public profile summary. |
| `GET` | `/api/users/{user_id}/subjects/` | Public marked subjects. |
| `GET` | `/api/users/{user_id}/reviews/` | Public reviews. |
| `GET` | `/api/users/{user_id}/collections/` | Public collections. |

## Public Profile

```bash
USER_ID=1

curl -s -X GET "$BASE_URL/api/users/$USER_ID/profile/" | jq
```

## Public Subjects

```bash
curl -s -X GET "$BASE_URL/api/users/$USER_ID/subjects/?page=1&page_size=16" | jq
```

Filters:

```text
status
subject_type
keyword
ordering
```

## Public Reviews

```bash
curl -s -X GET "$BASE_URL/api/users/$USER_ID/reviews/?page=1&page_size=16" | jq
```

## Public Collections

```bash
curl -s -X GET "$BASE_URL/api/users/$USER_ID/collections/?page=1&page_size=16" | jq
```

Use these endpoints for public user profile pages.
