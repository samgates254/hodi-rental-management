# Tenant statement

`GET /api/v1/billing/statements/me/`

`GET /api/v1/billing/statements/me/pdf/`

The signed-in user receives the statement for the active tenant record linked to that user. The server ignores `tenant` and `tenant_id`. There is no statement-by-id route.

Anonymous and invalid tokens are `401`. A user with no active tenant link, including an owner or accountant, is `404`.

Query:

- `period=current_month` (default), `previous_month`, or `lease`
- or `from` and `to` as `YYYY-MM-DD`, both required, end on or after start, span at most 24 months

Money is integer cents. The statement includes posted charges and recorded payments (`ALLOCATED` or `PENDING`). Draft charges and voided or failed payments are omitted. Outstanding and overdue balances come from posted charge balances. Unapplied credit is the sum of `overpayment_cents`. Current balance is outstanding minus that credit. National ID is not included.

The PDF response is `Content-Type: application/pdf` with `Content-Disposition: attachment`. It is generated in memory and not stored.
