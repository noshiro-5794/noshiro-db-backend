# Rating Details API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

Rating details are per-subject custom rating dimensions owned by the current user.

## Get Rating Details

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X GET "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/rating-details/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Replace Rating Details

```bash
curl -s -X PUT "$BASE_URL/api/users/me/subjects/$SUBJECT_ID/rating-details/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "details": [
      {"key": "story", "value": "8.5"},
      {"key": "music", "value": "7.5"},
      {"key": "visual", "value": "8.0"}
    ]
  }' | jq
```

The request replaces the complete detail list. Use an empty list to clear all details.

Validation:

```text
key: non-empty string
value: decimal from 0 to 10
duplicate keys are not allowed
```
