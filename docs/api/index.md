# Index Subjects API

Run the common setup in [README](./README.md). These APIs are public and do not require authentication.

The site currently treats only `anime` and `galgame` as primary browsable subjects. Other subject types may appear inside the `relations` field and can be opened by UUID for basic information, but they are not returned as top-level search/list subjects.

## List Subjects

This endpoint is paginated.

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?page=1&page_size=16" | jq
```

Expected response shape:

```json
{
  "code": 0,
  "message": "",
  "data": {
    "count": 0,
    "next": null,
    "previous": null,
    "results": []
  }
}
```

Each subject keeps the legacy flat fields and also includes display-friendly summary fields:

- `display_title`, `title_original`, `title_localized`
- `year`
- `images.poster`, `images.thumbnail`, `images.original`
- `display_meta`, `display_subtitle`
- `description_excerpt`
- `source.provider`, `source.id`
- `content.series`, `content.episodes`, `content.volumes`

External popularity values are intentionally not included in index subject summaries.
The daily calendar snapshot owns its own display metrics, such as `doing`.

## Search Subjects

Search by title or Chinese title. Keyword searches sort by relevance first.

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?keyword=葬送&page=1&page_size=16" | jq
```

English or original title:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?keyword=frieren&page=1&page_size=16" | jq
```

## Filter Subjects

Filter by subject type:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?subject_type=anime&page=1&page_size=16" | jq
```

Supported subject types:

```text
anime
galgame
```

Other subject types are intentionally rejected by this endpoint:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?subject_type=manga" | jq
```

Filter NSFW content:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?nsfw=false&page=1&page_size=16" | jq
```

Filter by release year, season, platform, date range, or episode count:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?year=2026&season=spring&page=1&page_size=16" | jq
curl -s -X GET "$BASE_URL/api/index/subjects/?platform=TV&episodes_min=13&episodes_max=24" | jq
curl -s -X GET "$BASE_URL/api/index/subjects/?date_from=2026-01-01&date_to=2026-12-31" | jq
```

Combine filters:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?keyword=test&subject_type=anime&nsfw=false&page=1&page_size=16" | jq
```

## Ordering

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?ordering=-date&page=1&page_size=16" | jq
```

Supported ordering values:

```text
date
-date
title
-title
updated_at
-updated_at
created_at
-created_at
```

Invalid ordering, expected to fail validation:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?ordering=invalid" | jq
```

## Get Subject Detail

Use a subject ID returned by the list/search endpoint, or a related subject UUID returned by the relations endpoint.

```bash
SUBJECT_ID="000212ed-b7b4-45c1-8d0d-7cd72906baa4"

curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/" | jq
```

The detail endpoint can return any subject type by UUID. This is intentional so relation links can open a basic page even when the related subject is not anime/galgame.

The detail response intentionally includes only base subject data and counters:

- Common subject fields.
- Section counters: `episode_count`, `staff_count`, `character_count`.
- Source infobox and tags.

Large sections are loaded through dedicated APIs:

```text
GET /api/index/subjects/{subject_id}/episodes/
GET /api/index/subjects/{subject_id}/staff/
GET /api/index/subjects/{subject_id}/characters/
GET /api/index/subjects/{subject_id}/relations/
```

Missing subject, expected to fail:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/00000000-0000-0000-0000-000000000000/" | jq
```

Expected business error:

```json
{
  "code": 21000,
  "message": "subject not found",
  "data": null
}
```

## List Subject Episodes

This endpoint is paginated. The default and maximum `page_size` is `96`.

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/episodes/?page=1&page_size=96" | jq
```

## List Subject Staff

This endpoint is paginated. Important roles such as `監督`, `导演`, `director`, `原作`, and `脚本` are ordered first.

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/staff/?page=1&page_size=16" | jq
```

## List Subject Characters

This endpoint is paginated. Important roles such as `主人公`, `主角`, and `main` are ordered first.

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/characters/?page=1&page_size=16" | jq
```

## List Subject Relations

This endpoint returns all direct relations. Related subjects may be any subject type.

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/relations/" | jq
```

## Frontend Flow

On a search page:

1. Call `GET /api/index/subjects/?keyword={query}&page=1&page_size=16`.
2. Render each result as a subject card using `image_thumbnail`, `title_cn || title`, `subject_type`, `date`, and `platform`.
3. Hide or warn on NSFW cards according to frontend policy.
4. Treat returned subjects as anime/galgame only.

On a subject detail page:

1. Call `GET /api/index/subjects/{subject_id}/`.
2. Render public catalog data from this response.
3. In parallel or lazily, call episodes, staff, characters, and relations APIs for the visible sections.
4. When switching an episodes/staff/characters page, refresh only that section API, not the whole subject detail.
5. If logged in and the subject is anime/galgame, call `GET /api/users/me/subjects/{subject_id}/context/` to render the current user's mark, tags, progress, rating details, and reviews.

## Anime Calendar

Returns active Bangumi daily broadcast calendar entries grouped by weekday.

```bash
curl -s -X GET "$BASE_URL/api/index/calendar/" | jq
```

Filter one weekday:

```bash
curl -s -X GET "$BASE_URL/api/index/calendar/?weekday_en=Mon" | jq
```
