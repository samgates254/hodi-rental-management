# Work Assignments

## Backend platform

Owns authentication, organizations, permissions, tenant isolation, shared API behavior, migrations, audit, idempotency, outbox, deployment, and CI.

## Backend domain

Owns properties, units, tenants, leases, billing, maintenance, application services, and API endpoints.

## Mathematical engines

Owns deterministic proration, allocation, occupancy, and financial engines. Engines must remain independent of Django, HTTP, providers, and databases.

## UI

Consumes versioned API contracts from `docs/api/` and does not access database models directly.

## Integration rule

Every feature requires tests, migrations where applicable, authorization, organization isolation, API documentation, and a review from the owning team.
