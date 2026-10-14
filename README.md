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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
python manage.py migrate
python manage.py runserver
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Health check: `http://127.0.0.1:8000/api/v1/health/`

Daraja sandbox configuration and callback testing are covered in [the sandbox setup guide](docs/payments/daraja-sandbox-setup.md). Do not use production credentials for local testing.
