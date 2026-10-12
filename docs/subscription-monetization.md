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

## One-time setup fee policy

Plans have an explicit `setup_fee_minor` amount, stored in KES minor units.
The current migrated catalogue defaults every setup fee to zero: actual
onboarding prices have not been approved. To introduce a fee, an authorized
operator must retire the active plan version and create a new version with
the approved amount; plan terms cannot be edited in place. The public plan
endpoint exposes this configured amount. There is no fee inferred by the
frontend.

A newly created organization subscription is eligible for the setup fee on
its first paid-plan invoice only. The invoice snapshots the monthly amount,
setup amount and total. Issuing that invoice consumes the one-time billing
eligibility; `setup_fee_paid` tracks settlement separately and becomes true
only after staff verifies an invoice that contains a setup fee. Rejected
reports do not create a second invoice; the same issued invoice can receive a
new payment reference. Retries therefore keep their original itemized amount.
If a verified payment is later reversed, its invoice remains unchanged, the
settlement is no longer counted as paid, and its outstanding balance reopens.
The setup fee remains invoiced and is not added to later monthly invoices.
The backend does not support partial subscription payments: a verified
settlement is for the full immutable invoice amount.

All subscriptions that existed when this policy was introduced are
grandfathered. Their one-time setup-fee invoicing marker is migrated on,
while the settlement marker is reconciled against verified setup-fee invoice
payments. Existing invoice totals are preserved as monthly line items with a
zero setup line. No existing customer or issued invoice is retroactively
charged. Enterprise
quotes follow the same first-invoice setup-fee rule, with the negotiated
monthly amount entered by authorized HODI staff.

Invoice API responses include `monthly_fee_minor`, `setup_fee_minor`,
`amount_minor` (invoice total), `amount_paid_minor`, and `outstanding_minor`.
Only a verified, non-reversed settlement contributes to amount paid.

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
