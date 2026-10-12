# HODI software subscriptions

## Architecture

`apps.subscriptions` is the system of record for HODI's B2B software plans,
organization subscription state, subscription invoices, payment reports, and
verified subscription settlements. It is deliberately separate from
`apps.billing.Invoice`, `Payment`, and the tenant rent ledger. A subscription
settlement never allocates against tenant charges.

The current catalogue is seeded by a migration and is administered in Django
Admin. Plan terms are versioned: existing terms cannot be edited in place;
retire the active version and add a new version to change price or entitlements.
Existing subscriptions and issued invoices retain their referenced plan
version and amount snapshot. Initial prices are evaluation proposals, not
validated market prices:

| Plan | Monthly proposal | Rentable unit limit |
| --- | ---: | ---: |
| Free | KSh 0 | 5 |
| Starter | KSh 999 | 20 |
| Growth | KSh 2,499 | 75 |
| Professional | KSh 4,999 | 200 |
| Enterprise | Negotiated | Negotiated per organization |

Prices are stored in integer KES minor units (100 minor units per KSh).
Entitlements use a small feature map for reporting, billing, maintenance, and
staff management. Those supported workflows remain enabled on the launch
plans. The enforced initial restriction is rentable inventory.

## Rentable unit definition and enforcement

One `properties.Unit` is one rentable unit, counted once through its
Building → Property → Organization relationship. Units with status `INACTIVE`
are excluded; `AVAILABLE`, `OCCUPIED`, and `MAINTENANCE` count. Lease rows,
tenants, staff, buildings, and properties are not counted as units. The API
checks capacity within a transaction while locking the organization and
subscription. It blocks creating or activating units beyond the plan limit,
but does not remove or hide existing records.

## Payment and invoice lifecycle

An owner or property manager requests a plan and receives an immutable HODI
subscription invoice. A customer may report a payment reference; that creates
only a pending review record. A HODI Django staff user must independently
verify the payment and provide a reason before a separate verified settlement
is recorded and entitlements change. Rejection and reversal are audited.
Reversed payments are excluded from retained/net collected revenue.

The current Daraja STK flow is tenant/rent-specific and is not used for these
invoices. This release does not initiate, reconcile, or verify subscription
payments automatically. HODI must communicate payment instructions outside
the application and verify records against an authoritative statement before
activation. The admin revenue page is at `/hodi-admin/revenue`; its APIs enforce
`is_staff` regardless of whether the page is linked or opened directly.

There is no automatic renewal, grace-period, proration, or annual-discount
policy in this implementation. Organizations retain access to existing data;
past-due, grace, cancelled, or expired subscriptions cannot add new rentable
units. Subscription invoices remain payable after their due date.

## Extension path

If HODI later sells one-time onboarding or migration, add an explicit invoice
purpose and line-item/service record in this subscription revenue domain, or a
small adjacent HODI revenue module. Keep its receivable and settlement records
out of landlord rent invoices and tenant allocations. Provider collection can
be added only with a subscription-specific provider reference, verified
callback/reconciliation lifecycle, and idempotent settlement tests; do not
reuse rent callbacks by trusting invoice identifiers alone.
