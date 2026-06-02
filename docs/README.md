# Noshiro DB Backend Documentation

This directory contains backend documentation for development, frontend integration, and operations.

## Contents

- [API Documentation](./api/README.md): response envelope, authentication, frontend API flows, and module-level curl examples.
- [Architecture](./architecture.md): app boundaries, layering conventions, and data ownership.
- [Operations](./operations.md): runtime processes, sync commands, scheduled jobs, and verification commands.

## Frontend Starting Points

Use these documents first when building the frontend:

```text
docs/api/README.md
docs/api/users-auth.md
docs/api/index.md
docs/api/users-subjects.md
docs/api/community-posts.md
```

The frontend should treat `index` as the public catalog surface, `users` as the authenticated account/library surface, and `community` as the social interaction surface.
