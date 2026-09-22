# Architecture and Ownership

```text
Frontend -> API v1 -> application services -> domain apps -> canonical engines
                                      -> database transaction
                                      -> audit/outbox -> workers/integrations
```

## Team boundaries

- Backend platform: `src/config`, `src/common`, `src/infrastructure`, migrations, security, tenancy, and deployment.
- Backend domain: `src/apps`, `src/application`, and API endpoints.
- Mathematical engines: `engines/`. Keep them deterministic and independent of HTTP, Django, databases, and payment providers.
- UI: `frontend/`. Use API contracts from `docs/api/` and never import backend models.

Financial logic must use integer KES minor units. Payment and ledger work begins only after engine contracts are agreed.
