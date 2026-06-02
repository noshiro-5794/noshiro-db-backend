# API Documentation

This directory is the frontend-facing API reference for Noshiro DB Backend.

## Base URL

Local development:

```bash
BASE_URL="http://127.0.0.1:8008"
COOKIE_JAR="./noshiro_api_cookies.txt"
EMAIL="user@example.com"
PASSWORD="TestPass123!"
```

## Response Envelope

Successful responses:

```json
{
  "code": 0,
  "message": "",
  "data": {}
}
```

Business errors use the same envelope with a non-zero `code`.

Paginated responses put pagination inside `data`:

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

Supported pagination query params:

```text
page=1
page_size=16
```

`page_size` is capped at `64`.

`DELETE` endpoints can return `204 No Content`.

## Authentication

Password login and registration return a short-lived access token:

```json
{
  "access": "access_token_here"
}
```

Authenticated requests use:

```bash
-H "Authorization: Bearer $ACCESS_TOKEN"
```

The refresh token is stored in an HttpOnly cookie named `noshiro_refresh`.

Browser refresh/logout requests must include credentials:

```js
await fetch(`${baseUrl}/api/users/token/refresh/`, {
  method: "POST",
  credentials: "include",
});
```

Frontend storage recommendation:

- Keep the access token in app memory.
- Do not store the refresh token in localStorage.
- On page reload, call refresh with `credentials: "include"` to recover a new access token.
- If refresh fails, treat the user as logged out.

Use `GET /api/users/me/profile/` after login or refresh. It returns `is_staff` and `is_superuser`, which the frontend can use to hide staff-only sync controls.

## Product Flows

### Catalog Search

Search/list pages use:

```text
GET /api/index/subjects/?keyword={query}&subject_type=anime&page=1&page_size=16
GET /api/index/subjects/?keyword={query}&subject_type=galgame&page=1&page_size=16
```

The list endpoint is limited to primary site content:

```text
anime
galgame
```

Subject detail lookup accepts any subject UUID, including related non-primary entries:

```text
GET /api/index/subjects/{subject_id}/
```

Heavy sections are loaded separately:

```text
GET /api/index/subjects/{subject_id}/episodes/?page=1&page_size=96
GET /api/index/subjects/{subject_id}/staff/?page=1&page_size=16
GET /api/index/subjects/{subject_id}/characters/?page=1&page_size=16
GET /api/index/subjects/{subject_id}/relations/?page=1&page_size=16
```

### Authenticated Subject Detail

On a logged-in subject detail page, call:

```text
GET /api/users/me/subjects/{subject_id}/context/
```

This returns whether the subject is marked, the user's mark record, tags, rating details, reviews, and finished episode IDs.

Use subject UUID APIs for the main detail workflow so the frontend does not need to expose `UserSubject.id`.

### Community

Community surfaces are centered on posts, comments, activities, reviews, collections, and users:

```text
GET  /api/community/posts/
POST /api/community/posts/
GET  /api/community/comments/?target_type=post&target_id=1
POST /api/community/comments/
POST /api/community/reactions/
POST /api/community/bookmarks/
GET  /api/community/me/feed/
GET  /api/community/notifications/
```

Post and comment responses include `viewer_state` for active reaction/bookmark/follow UI state.

### Staff Sync

Staff-only endpoints:

```text
GET  /api/sync/incremental/status/
POST /api/sync/incremental/run/
POST /api/sync/calendar/run/
POST /api/sync/subjects/{subject_id}/resync/
```

The frontend should not show sync controls to non-staff users. The backend still enforces staff permissions.

## Modules

### Users

- [Auth](./users-auth.md): register, login, refresh, logout, and reset password.
- [Profile](./users-profile.md): profile read/update, settings, stats, and avatar upload.
- [User Subjects](./users-subjects.md): list, create, update, delete, and context for marked subjects.
- [Episode Progress](./users-progress.md): read and update per-episode progress.
- [Tags](./users-tags.md): manage tags and bind them to marked subjects.
- [Rating Details](./users-rating-details.md): replace and read detailed rating dimensions.
- [Reviews](./users-reviews.md): create, list, update, and delete reviews.
- [Collections](./users-collections.md): create collections and manage collection items.
- [Public User Profiles](./users-public-profiles.md): public profile, subjects, reviews, and collections.

### Community

- [Community Posts](./community-posts.md): create and list community status or subject posts.
- [Community Comments](./community-comments.md): comment on posts, reviews, collections, and activities.
- [Community Interactions](./community-interactions.md): react to and bookmark public targets.
- [Community Activities And Feed](./community-activities.md): user activities, public activities, and following feed.
- [Community Follows](./community-follows.md): follow users and list following/follower relations.
- [Community Relationships](./community-relationships.md): block and mute users.
- [Community Notifications](./community-notifications.md): list notifications and mark them as read.
- [Community Reports](./community-reports.md): report community content and staff moderation handling.

### Index

- [Index Subjects](./index.md): public subject search, filtering, detail, sections, relations, and calendar.

### Sync

- [Sync](./sync.md): staff-only calendar sync, incremental sync, and manual subject resync.
