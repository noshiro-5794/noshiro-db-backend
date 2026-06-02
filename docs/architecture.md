# Architecture

Noshiro DB is organized by product boundary instead of technical layer.

## Apps

```text
apps/core
apps/users
apps/community
apps/index
apps/sync
```

## Boundaries

`apps/users` owns account and personal library data:

```text
User
UserProfile
EmailVerification
UserSubject
UserEpisodeProgress
UserTag
UserSubjectTag
UserSubjectRatingDetail
Review
Collection
CollectionItem
```

`apps/community` owns social interaction data:

```text
UserFollow
Activity
CommunityPost
CommunityComment
CommunityReaction
CommunityBookmark
Notification
CommunityReport
UserBlock
UserMute
ModerationAction
```

`apps/index` owns public catalog data synchronized from Bangumi.

`apps/sync` owns synchronization state, external providers, Celery tasks, management commands, and staff-only sync APIs.

## Layering

```text
api/views         request/response boundary
api/serializers   input validation and output shape
selectors         read/query logic
services          write/business logic
tasks             Celery wrappers
providers         external API clients
```

Views should stay thin. Business rules belong in services. Query composition belongs in selectors. Serializers should not perform database writes.

## API Response

All API responses use the shared response envelope:

```json
{
  "code": 0,
  "message": "",
  "data": {}
}
```

Paginated data is placed inside `data`.

## Community Activity

`Activity` is not a full audit log. It is a displayable feed item for community surfaces. It supports visibility, feed policy, metadata snapshots, grouping, and deduplication.

Audit-style tracking should be implemented separately if needed.
