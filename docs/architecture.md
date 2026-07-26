# Architecture

Noshiro DB is organized by product boundary instead of technical layer.

## Apps

```text
src/apps/users
src/apps/community
src/apps/index
src/apps/sync
```

`src` is the Python import root, not a Python package, so it intentionally has
no `__init__.py`. Physical paths use `src/apps/...`, while Django app names
remain `apps.users`, `apps.community`, `apps.index`, and `apps.sync`. Package
directories keep explicit `__init__.py` files for predictable Django discovery.

## Boundaries

`src/apps/users` owns account and personal library data:

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

`src/apps/community` owns social interaction data:

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

`src/apps/index` owns public catalog data synchronized from Bangumi. The `index`
name is intentional product terminology and should not be renamed.

`src/apps/sync` owns synchronization state, external providers, Celery tasks, management commands, and staff-only sync APIs.

## Shared Code

`src/shared` contains stable, app-neutral code used by multiple apps. Shared API
responses, pagination, exception handling, and application errors live here.
It must not contain models, app-specific business rules, or external SDK clients.
Application errors are plain Python exceptions; the API exception handler owns
their HTTP status and response-envelope mapping.

## Integrations

`src/integrations` contains external adapters shared by multiple apps. MinIO
storage lives here because both user profiles and synchronization workflows use it.
An adapter owned by one business app remains inside that app's `providers` package.

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

Small apps may keep a single `models.py`. When it becomes difficult to navigate,
models are split by domain under `models/`, with `models/__init__.py` preserving
the app's stable public imports. `community` and `users` follow this pattern.

## Settings

`src/config/settings/base.py` contains shared Django configuration. `local.py`,
`production.py`, and `test.py` contain environment-specific behavior. Only local
settings load `.env`; production configuration comes from the process environment.

## Providers

External adapters stay with the app that owns their workflow. Bangumi and AI
normalization therefore live under `src/apps/sync/providers`. AI should move to
`src/integrations/ai` only when it becomes a cross-app capability.

Bangumi request throttling is enforced inside its provider, so pagination and
multi-request relation syncs cannot bypass the rate limit. Provider-specific
HTTP failures retain structured status information; services do not infer 404s
by parsing exception text.

A common catalog-provider protocol and normalized data objects should be added
when a second catalog source is implemented. Source-specific response formats
should not leak beyond provider adapters at that point.

## Tests

Cross-application configuration and architecture contracts live in `tests/`.
App-specific tests should stay inside the owning app's `tests/` package.
Tests use PostgreSQL so PostgreSQL-specific fields, indexes, constraints, and
query behavior match production.

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
