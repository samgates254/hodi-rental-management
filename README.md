# Rental Management OS

Django modular monolith for a secure, multi-tenant rental-management backend.

## Layout

- `backend/src/apps/`: Django domain modules owned by backend engineers.
- `backend/src/application/`: use-case orchestration and transaction boundaries.
- `backend/src/api/v1/`: versioned API adapters and schemas.
- `backend/src/common/`: shared authorization, errors, idempotency, and outbox utilities.
- `backend/src/infrastructure/`: persistence and external-provider adapters.
- `backend/src/workers/`: retryable background jobs.
- `backend/engines/`: canonical mathematical engines owned independently of Django.
- `backend/tests/`: unit, integration, API, security, and end-to-end tests.
- `frontend/`: UI team workspace; it consumes `/api/v1/` only.
- `docs/`: shared contracts and implementation decisions.

## Run locally

```bash
cd backend
cp .env.example .env
env/bin/python manage.py migrate
env/bin/python manage.py runserver
```

Health check: `http://127.0.0.1:8000/api/v1/health/`
