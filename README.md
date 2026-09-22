# Rental Management OS

Django modular monolith for a secure, multi-tenant rental-management backend.

## Layout

- `src/apps/`: Django domain modules owned by backend engineers.
- `src/application/`: use-case orchestration and transaction boundaries.
- `src/api/v1/`: versioned API adapters and schemas.
- `src/common/`: shared authorization, errors, idempotency, and outbox utilities.
- `src/infrastructure/`: persistence and external-provider adapters.
- `src/workers/`: retryable background jobs.
- `engines/`: canonical mathematical engines owned independently of Django.
- `tests/`: unit, integration, API, security, and end-to-end tests.
- `frontend/`: UI team workspace; it consumes `/api/v1/` only.
- `docs/`: shared contracts and implementation decisions.

## Run locally

```bash
cp .env.example .env
env/bin/python manage.py migrate
env/bin/python manage.py runserver
```

Health check: `http://127.0.0.1:8000/api/v1/health/`
