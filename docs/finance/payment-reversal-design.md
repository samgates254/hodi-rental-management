# Payment correction and reversal design gate

HODI does not currently implement an auditable ledger payment reversal. The present `Payment` row, `PaymentAllocation` rows, charge balances, and `LedgerPosting` rows are committed together by allocation. Postings identify the payment but have no reversal/compensating-entry relationship, and there is no existing tenant refund payable or disbursement workflow.

Do not mark a settled payment `VOIDED`, delete allocations, or restore charge balances directly. That would remove or misstate the original financial history. Do not call a ledger correction an M-Pesa refund.

Before implementation, accounting must approve the meaning of each correction:

1. **Unapply/reallocate:** append a correction linked to the original payment and allocations; restore the affected charge balances; append balanced reversing postings and replacement postings; preserve original rows and add correction audit metadata.
2. **Retain funds as tenant credit:** distinguish unapplied/refundable tenant liability from rent prepayment and specify how it appears on statements and delinquency calculations.
3. **External refund:** record a separate provider payout/refund attempt and reconcile its provider reference. Do not infer that an internal correction returned money to the payer.

A future schema should use one immutable correction record per request with organization, original payment, reason, actor/approver, idempotency key, effective timestamp, and child correction-allocation/posting rows. Enforce a unique idempotency key per organization, lock the payment and its allocations/charges in a documented global order, and expose only organization-authorized approval actions. Tests must cover full and partial allocation, tenant credit, duplicate requests, conflicting concurrent corrections, balanced inverse entries, unchanged original history, and separation from external refunds.

This remains gated until the account treatment and approval authority are agreed. The M2.1 work does not alter historical payments or invent that policy.
