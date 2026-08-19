# Security Policy

## Reporting a Vulnerability

Do not open a public issue for security vulnerabilities. Report them directly to
the project maintainer at `hangyuan2005@gmail.com`.

Include:

- affected component and version
- steps to reproduce
- impact
- any proposed mitigation

## Supported Versions

Only the latest `main` branch receives security fixes until versioned releases
are introduced.

## Production Security Requirements

- `DJANGO_SECRET_KEY` must be unique and never committed.
- `DEBUG` must be `False`.
- `CORS_ALLOW_ALL_ORIGINS` must be `False`.
- `TRUSTED_PROXY_CIDRS` must contain only reverse proxy addresses.
- refresh cookies must use `Secure`, `HttpOnly`, and an explicit `SameSite`.
- Admin and interactive API docs must be disabled unless explicitly enabled.
- Celery messages must not contain email addresses, passwords, tokens, or
  verification codes; tasks receive durable record IDs.
