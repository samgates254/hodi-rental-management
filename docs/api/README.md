# API Contracts

Versioned public endpoints live under `/api/v1/`. Add request/response examples and error schemas here before UI implementation.

See [authorization.md](authorization.md) for the organization role and resource access matrix.

## Landlord dashboard

The landlord dashboard uses the authenticated organization-scoped endpoints below. Send the DRF token as `Authorization: Token <token>` on every request; see [authentication](./authentication.md).

In Next.js development, `/api/v1/` is proxied to `http://127.0.0.1:8000` by default. Set `API_PROXY_TARGET` to the backend origin when using a different host; production deployments without this setting should route `/api/v1/` to the backend at the hosting layer.

- `GET /organizations/` — organizations the signed-in user belongs to.
- `POST /organizations/` with `{"name": "..."}` — create an organization; the creator becomes its owner.
- `GET /properties/`, `GET /properties/buildings/`, and `GET /properties/units/` — property structure.
- `POST /properties/` — create a property with `organization`, `name`, `address`, `city`, and `country`.
- `GET /tenants/` and `POST /tenants/` — tenant records. Creation accepts `organization`, `first_name`, `last_name`, and `phone_number`; `email` is optional.
- `GET /leases/` — leases. `monthly_rent_minor` is stored in minor currency units.

These endpoints are scoped to the user's active organization memberships. The current billing and maintenance API URL modules do not expose dashboard endpoints.
