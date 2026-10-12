# API Contracts

Versioned public endpoints live under `/api/v1/`. Add request/response examples and error schemas here before UI implementation.

See [authorization.md](authorization.md) for the organization role and resource access matrix.

See [statements.md](statements.md) for the authenticated tenant financial statement and PDF.

See [mpesa.md](mpesa.md) for M-Pesa Daraja STK initiation and callback settlement onto the canonical Payment ledger.

## Landlord dashboard

The landlord dashboard uses the authenticated organization-scoped endpoints below. Send the DRF token as `Authorization: Token <token>` on every request; see [authentication](./authentication.md).

In Next.js development, `/api/v1/` is proxied to `http://127.0.0.1:8000` by default. Set `API_PROXY_TARGET` to the backend origin when using a different host. For a production Next.js server, set `API_PROXY_TARGET` in the environment for `next build`; Next.js records that rewrite in the build output. If it is omitted in production, the frontend has no API rewrite and `/api/v1/` will return a Next.js 404 unless the hosting layer separately routes that path to Django. See [production deployment configuration](../deployment.md#nextjs-api-routing) for the exact setup.

- `GET /organizations/` — organizations the signed-in user belongs to.
- `POST /organizations/` with `{"name": "..."}` — create an organization; the creator becomes its owner.
- `GET /properties/`, `GET /properties/buildings/`, and `GET /properties/units/` — property structure.
- `POST /properties/` — create a property with `organization`, `name`, `address`, `city`, and `country`.
- `GET /tenants/` and `POST /tenants/` — tenant records. Creation accepts `organization`, `first_name`, `last_name`, and `phone_number`; `email` is optional.
- `GET /leases/` — leases. `monthly_rent_minor` is stored in minor currency units.

## Marketplace

Public discovery (no authentication):

- `GET /marketplace/listings/` — published available units with no active lease. Filters: `location`, `min_rent`, `max_rent`, `bedrooms`, `bathrooms`, `furnished`, `amenity`, `ordering`.
- `GET /marketplace/listings/{id}/` and `GET /marketplace/listings/{id}/photos/{photo_id}/` — public listing and photo bytes.
- `POST /marketplace/inquiries/` — send an inquiry. This does not reserve the unit.

Owner / property manager only:

- `GET/POST /marketplace/manage/listings/`
- `GET/PATCH/DELETE /marketplace/manage/listings/{id}/`
- `POST /marketplace/manage/listings/{id}/publish/` and `.../unpublish/`
- photo and inquiry endpoints under the managed listing

Public payloads include title, rent, rooms, amenities, area, city, property name, unit label, and photos. They do not include organization id, unit id, tenant, lease, landlord private contact, national ID, or internal financial rows.

## Caretaker dashboard

- `GET /maintenance/issues/` — list issues in active organizations where the user has an `OWNER`, `PROPERTY_MANAGER`, `CARETAKER`, or `TECHNICIAN` membership; a linked tenant may also read only their own issues. Staff with multiple memberships may select one using `?organization={id}`.
- `POST /maintenance/issues/` — create an issue for the authenticated user’s linked tenant record. Provide `title`, `category`, `description`, optional `priority`, and up to five `attachments` in a multipart request; supported media are JPEG, PNG, WebP, GIF, HEIC, HEIF, MP4, WebM, MOV, and 3GP (10 MB per photo, 50 MB per video). An active lease is required and its unit is selected automatically. Tenant-to-user links are maintained by administrators.
- `GET /maintenance/issues/{id}/attachments/{attachment_id}/` — stream an issue photo or video to an authenticated user who can access that issue.
- `POST /maintenance/issues/{id}/updates/` — add a note, update status (`OPEN`, `IN_PROGRESS`, or `RESOLVED`), or do both. Organization staff can update status; a linked tenant can add a note to their own issue. Every update is retained with its author and shown in both dashboards.
- `GET /billing/payments/` — list rent payments in active organizations for `OWNER`, `PROPERTY_MANAGER`, `ACCOUNTANT`, and `CARETAKER`; a linked tenant may also read only payments associated with their own leases. Staff with multiple memberships may select one using `?organization={id}`.
- `POST /billing/payments/`, `PUT/PATCH /billing/payments/{id}/`, and `DELETE /billing/payments/{id}/` — create, edit, and delete payment records for `OWNER`, `PROPERTY_MANAGER`, or `ACCOUNTANT` memberships only. Amounts use minor currency units.

All organization-backed results and mutations are scoped to the user’s active organization memberships.
