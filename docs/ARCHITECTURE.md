# Architecture and Ownership

```text
Frontend -> API v1 -> application services -> domain apps -> canonical engines
                                      -> database transaction
                                      -> audit/outbox -> workers/integrations
```

## Team boundaries

- Backend platform: `backend/src/config`, `backend/src/common`, `backend/src/infrastructure`, migrations, security, tenancy, and deployment.
- Backend domain: `backend/src/apps`, `backend/src/application`, and API endpoints.
- Mathematical engines: `backend/engines/`. Keep them deterministic and independent of HTTP, Django, databases, and payment providers.
- UI: `frontend/`. Use API contracts from `docs/api/` and never import backend models.

Financial logic must use integer KES minor units. Payment and ledger work begins only after engine contracts are agreed.
