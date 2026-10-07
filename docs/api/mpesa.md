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

## Callback

`POST /api/v1/billing/mpesa/callback/`

`POST /api/v1/billing/mpesa/callback/<token>/`

Daraja callbacks are **not signed**. HODI does not pretend they are. Gate:

1. HTTPS `MPESA_CALLBACK_URL` (the URL configured on the STK request).
2. Optional `MPESA_CALLBACK_AUTH_TOKEN`. When set, the request must use the path token or header `X-Hodi-Mpesa-Callback-Secret`. Put the token in the path of `MPESA_CALLBACK_URL`, not the query string. Safaricom cannot send custom headers.

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

Failure of those checks records the attempt as `FAILED` and creates no `Payment`.

### Unknown checkout

If Daraja accepted STK and HODI crashed before saving `checkout_request_id`, the callback will not match. HODI acknowledges the callback, writes `mpesa.stk.unmatched` audit, and **does not** create a `Payment`. Recovery via STK Query is a later phase.

### Settlement

On a valid success callback, inside `transaction.atomic()`:

1. `select_for_update(of=("self",))` on `MpesaAttempt` (no lock of the nullable invoice join).
2. `record_payment()` with `method=MPESA`, `external_id` and `reference` = receipt number.
3. Existing `allocate_payment()` with `CANONICAL_PRIORITY` v2.
4. Attempt `status=SUCCESS`, store `result_code`, `result_description`, `mpesa_receipt_number`.

Allocation uses the existing tenant-wide posted charges. An optional invoice on the attempt is context; it does not introduce a second allocation policy. Overpayment still posts to account `2020`, never `2030`.

Duplicate callbacks (same checkout or same receipt) produce no additional `Payment`, allocation, or ledger rows.

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
| `MPESA_CALLBACK_AUTH_TOKEN` | empty | Optional shared secret for the callback path/header. |
| `MPESA_TIMEOUT_SECONDS` | `30` | HTTP timeout. |
| `MPESA_TRANSACTION_TYPE` | `CustomerPayBillOnline` | STK `TransactionType`. |

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

- STK Query (needed to recover unmatched callbacks)
- Transaction Status API
- Paystack
- Frontend Pay Rent UI
- Production deployment and live credentials

## Tests

From `backend/`:

```bash
python manage.py test apps.billing.test_mpesa apps.billing.test_mpesa_client apps.billing.test_mpesa_callback
python manage.py test apps common tests
```
