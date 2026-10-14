# Rental payment reversal status

HODI implements an append-only reversal workflow for canonical rental ledger
payments. It preserves the original payment, allocations, and postings, and
records a linked reversal with compensating allocations and balanced postings.
Reversal requests are full-payment only; partial reversals are rejected.
An identical request with the same trimmed reason is idempotent. A conflicting
second request is rejected. Only an organization owner or accountant may
request a reversal.

For non-M-Pesa methods, the operation marks the payment reversed, restores
charge balances from still-allocated payments, removes any original tenant
credit from the live balance through compensating postings, and writes an
audit record. The original payment and correction history remain available to
statements and reporting.

For M-Pesa payments, HODI records a `REVIEW_REQUIRED` reversal request and an
audit event. It does not change payment status, allocations, charge or invoice
balances, or ledger postings. HODI verifies STK settlement, but does not verify
provider-side reversal events. An operator-entered reference or callback claim
cannot complete an external refund. There is no provider reversal or review
completion workflow in this operation.

## Remaining accounting and provider work

The current API does not support partial payment reversals, tenant refund
payables, or a verified external refund disbursement. Adding any of those
requires an approved accounting policy, an authorized approval role, evidence
requirements, and a provider reconciliation workflow. Until those decisions
exist, a review-required M-Pesa request remains unresolved and must not be
reported as money returned to the payer.
