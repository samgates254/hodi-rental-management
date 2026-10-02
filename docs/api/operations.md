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

Organization delete is rejected when properties or financial rows exist.
