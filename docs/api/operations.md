# Billing, maintenance, notifications, and audit

Money is integer KES cents. Allocation goes through `engines.allocation.allocate` with policy `CANONICAL_PRIORITY` version 2. Charge ids are UUIDs. Overpayment posts to account `2020`, never `2030`.

Legacy rent payments that the caretaker and tenant dashboards already call stay at `/api/v1/billing/payments/` (`amount_minor`, lease, due date, PENDING/PAID/OVERDUE).

Canonical invoices, charges, and engine allocation live beside that contract:

- `/api/v1/billing/invoices/` plus `POST .../post/` and `POST .../void/`
- `/api/v1/billing/charges/`
- `/api/v1/billing/ledger-payments/` plus `POST .../allocate/`
- `GET /api/v1/billing/delinquency/?tenant=&as_of=`

Maintenance requests (separate from the existing tenant issue inbox at `/maintenance/issues/`) are `/api/v1/maintenance/requests/` with `assign`, `complete`, `close`, and `comments`. Technicians only see work assigned to them. Priority is scored by `engines.maintenance.priority.score`.

`GET /api/v1/accounts/me/` returns the signed-in user, profile, and memberships.

Notifications are per user: `GET /api/v1/notifications/`, `POST /api/v1/notifications/{id}/read/`, `POST /api/v1/notifications/read-all/`.

Audit logs are append-only: `GET /api/v1/audit/logs/` for owners, property managers, and accountants in the organization.

Marketplace listings attach one-to-one to an existing unit. Public discovery is unauthenticated:

- `GET /api/v1/marketplace/listings/` with `location`, `min_rent`, `max_rent`, `bedrooms`, `bathrooms`, `furnished`, `amenity`, and `ordering` (`newest`, `rent`, `-rent`)
- `GET /api/v1/marketplace/listings/{id}/`
- `GET /api/v1/marketplace/listings/{id}/photos/{photo_id}/`
- `POST /api/v1/marketplace/inquiries/`

A listing is public only when it is `PUBLISHED`, the unit is `AVAILABLE`, and the unit has no `ACTIVE` lease. Drafts, occupied units, and actively leased units return 404 on public detail, photos, and inquiry. Photos are JPEG, PNG, WEBP, or GIF, at most 12 per listing and 8 MB each, served through the API with `X-Content-Type-Options: nosniff`. Django `MEDIA` is not a public route.

Owner and property-manager listing desk:

- `GET/POST /api/v1/marketplace/manage/listings/`
- `GET/PATCH/DELETE /api/v1/marketplace/manage/listings/{id}/`
- `POST .../publish/` and `POST .../unpublish/`
- photo upload, fetch, and delete on the managed listing
- `GET .../inquiries/`

Another organization’s listing returns 404. Accountants, caretakers, tenants, technicians, and anonymous users cannot manage listings. An inquiry does not reserve a unit.

Organization delete is rejected when properties or financial rows exist.
