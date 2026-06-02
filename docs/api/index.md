# Index API

Public catalog APIs do not require authentication.

The site search surface is limited to:

```text
anime
galgame
```

Subject detail lookup accepts any subject UUID, including related non-primary subjects reached from relations.

## Calendar

```bash
curl -s -X GET "$BASE_URL/api/index/calendar/" | jq
```

Filter by weekday:

```bash
curl -s -X GET "$BASE_URL/api/index/calendar/?weekday_en=Mon" | jq
```

Supported weekdays:

```text
Mon
Tue
Wed
Thu
Fri
Sat
Sun
```

## Subject List

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?page=1&page_size=16" | jq
```

Filters:

```text
keyword
subject_type=anime|galgame
date_from
date_to
min_rating
ordering
```

Example:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/?keyword=サラダ&subject_type=anime&page=1&page_size=16" | jq
```

## Subject Detail

```bash
SUBJECT_ID="2241e7a8-f492-4337-b601-507a09cc5eee"

curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/" | jq
```

The detail response is intentionally lightweight. Heavy sections are separate endpoints.

## Episodes

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/episodes/?page=1&page_size=96" | jq
```

Episode detail:

```bash
EPISODE_ID=1

curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/episodes/$EPISODE_ID/" | jq
```

## Staff

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/staff/?page=1&page_size=16" | jq
```

Roles:

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/staff/roles/" | jq
```

Important roles such as director are prioritized by selectors.

## Characters

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/characters/?page=1&page_size=16" | jq
```

Main characters are prioritized by selectors.

## Relations

```bash
curl -s -X GET "$BASE_URL/api/index/subjects/$SUBJECT_ID/relations/?page=1&page_size=16" | jq
```

Relations can include non-primary subject types for context, while search and user marking remain focused on anime and galgame.
