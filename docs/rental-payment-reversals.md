# Rental payment reversals

Rental ledger payments can be reversed with:

```http
POST /api/v1/billing/ledger-payments/{payment_id}/reverse/
Content-Type: application/json

{"reason": "Bank transfer returned"}
```

The request requires a non-empty reason. The optional `amount_cents` must equal the full original payment; partial reversals are not supported. An identical request (same trimmed reason) returns the existing reversal outcome. A request with a different reason after a reversal request exists is rejected.

Only users with billing write access for the payment's organization can request a reversal. Under the current role policy, that is an organization owner or accountant. Tenants, property managers, caretakers, and users outside the organization cannot initiate one.

A completed reversal is full-payment only. It preserves the original payment, allocations, and postings; records the author, reason, amount, timestamp, and resulting state; writes linked compensating ledger postings; and records compensating rows for every original charge allocation. Each affected charge balance is recomputed from its face amount and allocations belonging to payments that remain allocated. Invoice totals remain unchanged while paid amounts and outstanding balances reflect the restored charge balances. Any unallocated overpayment is reversed through inverse postings to the existing prepaid-rent account and is removed from the tenant's live credit balance.

The response includes the original payment and its reversal state, compensating allocations, and linked postings. The tenant statement retains the payment and reversal history while reporting balances from active allocations and credits.

## M-Pesa requests

The current Daraja integration verifies STK settlements and reconciles ambiguous attempts; it does not independently verify provider-side reversal events. An authorised request to reverse an M-Pesa ledger payment therefore returns `202 Accepted` with reversal state `REVIEW_REQUIRED`. It creates an audit record but does not change payment status, charge balances, invoice balances, or ledger postings. A callback or user-entered reference alone does not complete a provider reversal. No automated provider reversal or review-completion workflow is provided by this operation; the request remains unresolved for authorised review.
