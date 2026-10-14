# HODI M-Pesa (Daraja)

M-Pesa is a payment **provider**. Canonical accounting stays:

```text
Tenant
  → Payment
    → PaymentAllocation
      → LedgerPosting
        → Charge / Invoice
          → Statement
```

`MpesaAttempt` is the Daraja lifecycle. A successful STK callback creates the existing `Payment` and calls `allocate_payment()`. It does not replace that path.

## Initiate

`POST /api/v1/billing/mpesa/initiate/`

Authentication: DRF token. The payer is the active `Tenant` linked to the signed-in user. Client-supplied `tenant` / `organization` IDs are ignored.

`202 Accepted` with `status: STK_SENT` means Daraja accepted the prompt. `payment_settled: false`. The tenant has not paid yet.

`amount_cents` is a requested partial amount, not an authority to overcharge. Before creating an attempt, HODI calculates the tenant's outstanding posted KES charges under the existing tenant-wide `CANONICAL_PRIORITY` allocation policy, excluding deposit charge types, then subtracts the amount reserved by other open STK attempts. The request is rejected if the amount exceeds that available rent balance. A tenant row lock serializes concurrent initiations on PostgreSQL; unresolved prompts continue reserving their amount until reconciled or closed. An optional invoice ID is descriptive: it does not scope the existing tenant-wide allocation order. M-Pesa cannot collect a security deposit through this endpoint. The existing generic ledger overpayment rule still posts verified excess to tenant credit account `2020` if another payment settles the rent while an STK prompt is already in flight; it never posts rent overpayment to deposit liability account `2030`.

HODI currently exposes the lease's security-deposit amount as a lease term but does not provide a separate deposit collection, liability ledger, or refund workflow. Deposit collection must not be represented as rent or initiated through this M-Pesa route until that separate accounting workflow exists.

`GET /api/v1/billing/mpesa/attempts/<uuid>/` returns only an attempt linked to the authenticated tenant. Its stable public status is `PENDING`, `SUCCESSFUL`, `FAILED`, `EXPIRED`, or `UNRESOLVED`; provider references and phone numbers are not returned. An old initiated/STK-sent attempt is `UNRESOLVED`, not presumed successful or failed.

## Callback

`POST /api/v1/billing/mpesa/callback/`

`POST /api/v1/billing/mpesa/callback/<token>/`

Daraja callbacks are **not signed**. HODI does not pretend they are. Gate:

1. HTTPS `MPESA_CALLBACK_URL` (the URL configured on the STK request).
2. Required `MPESA_CALLBACK_AUTH_TOKEN`. The callback path must contain this bearer token because Safaricom does not send HODI custom headers. The optional header is supported for controlled provider proxies. The token limits unsolicited callback traffic; it is not a cryptographic signature or proof that the request came from Safaricom. Production settings and callback handling fail closed when it is absent.

For every terminal callback, HODI queries Daraja STK Query using the stored checkout reference and requires both stored request references to match. `ResponseCode` is treated as query-operation acceptance; only a present `ResultCode` tied to the same checkout and merchant references is treated as the transaction outcome. A callback/query outcome conflict, timeout, missing field, or mismatched reference leaves the attempt open and records a discrepancy. A query-confirmed failure may close the attempt; a query-confirmed success is settled only when the callback supplies valid amount, phone, date, and receipt metadata. STK Query does not provide HODI's receipt metadata, so reconciliation never fabricates a payment or receipt.

The callback token is a bearer credential used to limit unsolicited requests, not proof of sender identity. It remains in the URL path because Daraja does not send custom headers. Rotate it by generating a new high-entropy token, updating `MPESA_CALLBACK_AUTH_TOKEN` and the HTTPS callback path together, updating the callback URL in the Daraja application, and deploying the matching configuration. Treat the old token as compromised if it may have been logged. The repository's callback application log messages do not include request paths, bodies, phone numbers, or receipts. It has no reverse-proxy or hosting access-log configuration: deployment owners must verify redaction of the callback path segment in platform access logs, APM traces, exception reports and support tooling. Do not assume hosting access logs are redacted.

### Reconciliation command

Schedule `python manage.py reconcile_mpesa_attempts` from the backend project at a modest interval (for example every 5 minutes). The command queries only stale, open attempts with stored provider references, processes at most 100 per run, and uses exponential retry spacing with a maximum of five queries. Preview eligibility with `python manage.py reconcile_mpesa_attempts --dry-run`. A matching STK Query `ResultCode=0` proves the query outcome but does not return the receipt needed by HODI's payment identity; it marks the attempt `SUCCESS_NEEDS_RECEIPT` and creates no payment. Review unresolved/exhausted attempts with `python manage.py reconcile_mpesa_attempts --review-required`.

An authorized organization owner or accountant can resolve an attempt in `SUCCESS_NEEDS_RECEIPT` using `POST /api/v1/billing/mpesa/attempts/<attempt-id>/resolve/`. The reviewer must independently inspect the Safaricom portal/statement or bank statement and submit its source and evidence reference, receipt, amount, checkout and merchant request IDs, account reference when present, phone number and transaction date. HODI compares these transaction details with the locked attempt and requires the append-only successful STK Query audit. A customer cannot review their own attempt. The endpoint records the reviewer and evidence reference, then posts through the normal rental payment and allocation services. Identical retries return the original payment; conflicting evidence and receipts already used by another attempt/payment are rejected. This is a human evidence check: the endpoint cannot fetch or independently authenticate a Safaricom portal/statement entry. Never settle based on a customer-reported receipt alone and never manually edit payment rows.

The attempt identified by `CheckoutRequestID` is the source of truth for organization, tenant, amount, phone, and invoice. Callback body fields named `tenant` / `organization` are ignored.

### ResultCode mapping

| Daraja `ResultCode` | `MpesaAttempt.status` |
| --- | --- |
| `0` | `SUCCESS` only after metadata validation and ledger settlement |
| `1031`, `1032` | `CANCELLED` |
| `1019`, `1025`, `1037` | `TIMEOUT` |
| any other non-zero | `FAILED` |

`ResponseCode=0` on STK Push is still only `STK_SENT`. Payment success is callback `ResultCode=0` plus validation.

### Success validation

Before creating a `Payment`:

- `CheckoutRequestID` matches a stored attempt
- tenant and organization come from that attempt
- attempt is not already `SUCCESS`
- currency is `KES`
- callback `Amount` (whole KES) equals `MpesaAttempt.amount_cents`
- callback phone, when present, matches the normalized attempt phone
- `MpesaReceiptNumber` is present
- payload structure is valid

Failure of those checks leaves the attempt unresolved, records a discrepancy, and creates no `Payment`.

### Unknown checkout

If Daraja accepted STK and HODI crashed before saving `checkout_request_id`, the callback will not match. HODI acknowledges the callback, writes `mpesa.stk.unmatched` audit, and **does not** create a `Payment`. The attempt requires operator review; it cannot be queried by checkout until the missing provider reference is recovered from authoritative records.

### Settlement

On a valid success callback, inside `transaction.atomic()`:

1. `select_for_update(of=("self",))` on `MpesaAttempt` (no lock of the nullable invoice join).
2. `record_payment()` with `method=MPESA`, `external_id` and `reference` = receipt number.
3. Existing `allocate_payment()` with `CANONICAL_PRIORITY` v2.
4. Attempt `status=SUCCESS`, store `result_code`, `result_description`, `mpesa_receipt_number`.

Allocation uses the existing tenant-wide posted charges. An optional invoice on the attempt is context; it does not introduce a second allocation policy. Overpayment still posts to account `2020`, never `2030`.

Duplicate callbacks (same checkout or same receipt) produce no additional `Payment`, allocation, or ledger rows. A late callback after operator resolution is accepted only as a duplicate when its validated receipt matches the stored receipt; conflicting callback metadata is recorded as a discrepancy and does not post another payment.

`allocate_payment()` already writes `payment.record` / `payment.allocate` audit and `PAYMENT_RECEIVED` notification.

## Environment variables

| Variable | Development default | Purpose |
| --- | --- | --- |
| `MPESA_BASE_URL` | `https://sandbox.safaricom.co.ke` | Daraja host. HTTPS required. |
| `MPESA_CONSUMER_KEY` | empty | OAuth client key. |
| `MPESA_CONSUMER_SECRET` | empty | OAuth client secret. |
| `MPESA_SHORTCODE` | empty | Paybill / business shortcode. |
| `MPESA_PASSKEY` | empty | STK Lipa Na M-Pesa passkey. |
| `MPESA_CALLBACK_URL` | empty | HTTPS URL Daraja calls. Include the auth token in the path when used. |
| `MPESA_CALLBACK_AUTH_TOKEN` | empty in development; required in production | Random callback bearer token, at least 32 characters in production. |
| `MPESA_TIMEOUT_SECONDS` | `30` | HTTP timeout. |
| `MPESA_TRANSACTION_TYPE` | `CustomerPayBillOnline` | STK `TransactionType`. |

The account-verification frontend uses `ACCOUNT_FRONTEND_URL` (defaults to `http://localhost:3000` locally; production requires HTTPS) to build links for email confirmation and password reset.

## Status lifecycle

| Status | Meaning |
| --- | --- |
| `INITIATED` | Row saved. STK has not been accepted. |
| `STK_SENT` | Daraja `ResponseCode=0`. Prompt accepted. **Not payment success.** |
| `SUCCESS` | Valid success callback settled onto `Payment` + ledger. |
| `FAILED` | STK rejected, validation failed, or other non-zero result. |
| `CANCELLED` | User cancelled the prompt (`1031` / `1032`). |
| `TIMEOUT` | Prompt expired (`1019` / `1025` / `1037`). |

## Architecture

- `infrastructure.payments.mpesa.MpesaClient` — Daraja HTTP.
- `application.services.mpesa.initiate_mpesa_stk` — STK initiation.
- `application.services.mpesa_callback.settle_stk_callback` — callback settlement.
- `application.services.billing.record_payment` / `allocate_payment` — canonical money path.

## Not implemented yet

- Automatic ledger settlement for query-confirmed success without callback receipt metadata
- Transaction Status API
- Paystack
- Production deployment and live credentials

## Tests

From `backend/`:

```bash
python manage.py test apps.billing.test_mpesa apps.billing.test_mpesa_client apps.billing.test_mpesa_callback
python manage.py test apps common tests
```
