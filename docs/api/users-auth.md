# Users Auth API

Run the common setup in [README](./README.md).

## Send Verification Code

```bash
curl -s -X POST "$BASE_URL/api/users/send-code/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "'"$EMAIL"'",
    "purpose": "register"
  }' | jq
```

Supported `purpose` values:

```text
register
login
reset_password
```

## Register

```bash
curl -s -X POST "$BASE_URL/api/users/register/" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -d '{
    "email": "'"$EMAIL"'",
    "password": "'"$PASSWORD"'",
    "code": "123456",
    "nickname": "noshiro"
  }' | jq
```

Response:

```json
{
  "code": 0,
  "message": "",
  "data": {
    "access": "access_token"
  }
}
```

The refresh token is set as an HttpOnly cookie.

## Password Login

```bash
curl -s -X POST "$BASE_URL/api/users/login/password/" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -d '{
    "email": "'"$EMAIL"'",
    "password": "'"$PASSWORD"'"
  }' | jq
```

## Code Login

```bash
curl -s -X POST "$BASE_URL/api/users/login/code/" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -d '{
    "email": "'"$EMAIL"'",
    "code": "123456"
  }' | jq
```

## Refresh Access Token

```bash
curl -s -X POST "$BASE_URL/api/users/token/refresh/" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR" | jq
```

Frontend requests must use:

```js
credentials: "include"
```

## Logout

```bash
curl -s -X POST "$BASE_URL/api/users/logout/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR" | jq
```

## Reset Password

```bash
curl -s -X POST "$BASE_URL/api/users/password/reset/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "'"$EMAIL"'",
    "code": "123456",
    "new_password": "'"$NEW_PASSWORD"'"
  }' | jq
```

## Frontend Notes

- Keep the access token in app memory.
- Keep the refresh token in the HttpOnly cookie.
- On app boot, call refresh; if it fails, show logged-out UI.
- After login or refresh, call `GET /api/users/me/profile/`.
