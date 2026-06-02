# Users Profile API

Run the common setup in [README](./README.md), then login with [Auth](./users-auth.md) to set `ACCESS_TOKEN`.

## Get My Profile

```bash
curl -s -X GET "$BASE_URL/api/users/me/profile/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Important fields:

```text
user_id
email
is_staff
is_superuser
nickname
bio
avatar
language
appearance
theme_color
```

## Update My Profile

```bash
curl -s -X PATCH "$BASE_URL/api/users/me/profile/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "noshiro",
    "bio": "Anime and galgame notes.",
    "theme_color": "#66ccff"
  }' | jq
```

## Get Settings

```bash
curl -s -X GET "$BASE_URL/api/users/me/settings/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Update Settings

```bash
curl -s -X PATCH "$BASE_URL/api/users/me/settings/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "language": "zh-CN",
    "appearance": "auto",
    "theme_color": "#66ccff"
  }' | jq
```

Supported `language` values:

```text
auto
en-US
zh-CN
ja-JP
```

Supported `appearance` values:

```text
auto
light
dark
```

## Profile Stats

```bash
curl -s -X GET "$BASE_URL/api/users/me/profile/stats/?year=2026&timezone=Asia/Shanghai" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## Upload Avatar

```bash
curl -s -X POST "$BASE_URL/api/users/me/avatar/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "avatar=@avatar.jpg" | jq
```

The backend validates content type and max file size, then stores the original image in MinIO.
