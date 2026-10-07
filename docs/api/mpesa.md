# HODI M-Pesa (Daraja) — Phase 1

M-Pesa is a payment **provider**. It initiates an asynchronous STK Push. It does not replace the canonical accounting flow:

```text
Tenant
  → Payment
    → PaymentAllocation
      → LedgerPosting
        → Charge / Invoice
          → Statement
```

`MpesaAttempt` records the Daraja lifecycle. A later callback phase will create the canonical `Payment` and settle the ledger. Phase 1 never writes `Payment`, `PaymentAllocation`, or `LedgerPosting`.

## Endpoint

`POST /api/v1/billing/mpesa/initiate/`

The path follows existing billing URLs under `/api/v1/billing/` rather than a new `/api/v1/payments/` prefix.

Authentication: DRF token. The payer is the active `Tenant` linked to the signed-in user. Client-supplied `tenant`, `tenant_id`, `organization`, and `organization_id` are ignored.

Request:

```json
{
  "amount_cents": 150000,
  "phone_number": "0711111111",
  "invoice": 12
}
```

- `amount_cents` is required. Positive integer KES cents, divisible by 100 (Daraja accepts whole shillings only).
- `phone_number` is optional. When omitted, the tenant record phone is used. Kenyan mobiles are normalized to `2547XXXXXXXX` or `2541XXXXXXXX`.
- `invoice` is optional. When present it must be a **posted** invoice owned by the authenticated tenant.

`202 Accepted` means Daraja accepted the STK request (`status: STK_SENT`). `accepted: true` and `payment_settled: false` in that response. The tenant has not paid yet.

## Status lifecycle

| Status | Meaning |
| --- | --- |
| `INITIATED` | Attempt row saved. STK has not been accepted. |
| `STK_SENT` | Daraja `ResponseCode=0`. The prompt was accepted for processing. **Not payment success.** |
| `SUCCESS` | Reserved for a later callback with `ResultCode=0`. Unused in this phase. |
| `FAILED` | Daraja rejected the STK request, credentials/config failed, or the HTTP call failed. |
| `CANCELLED` | Reserved for a later callback (user cancelled the prompt). |
| `TIMEOUT` | Reserved for a later callback (prompt expired). |

`STK_SENT` ≠ `SUCCESS`. Daraja accepting the API request is not a paid invoice, not an allocated payment, and not a statement credit.

## Environment variables

Set these in `backend/.env`. Copy names from `backend/.env.example`. Do not commit real values.

| Variable | Development default | Purpose |
| --- | --- | --- |
| `MPESA_BASE_URL` | `https://sandbox.safaricom.co.ke` | Daraja host. HTTPS required. |
| `MPESA_CONSUMER_KEY` | empty | OAuth client key. |
| `MPESA_CONSUMER_SECRET` | empty | OAuth client secret. |
| `MPESA_SHORTCODE` | empty | Paybill / business shortcode. |
| `MPESA_PASSKEY` | empty | STK Lipa Na M-Pesa passkey. |
| `MPESA_CALLBACK_URL` | empty | HTTPS URL Daraja will call later. Callback handling is not implemented in this phase. |
| `MPESA_TIMEOUT_SECONDS` | `30` | HTTP timeout. |
| `MPESA_TRANSACTION_TYPE` | `CustomerPayBillOnline` | STK `TransactionType`. |

Sandbox credentials will be supplied from a Safaricom developer app: create a sandbox app, copy the consumer key/secret, shortcode, and passkey into local `backend/.env`, and point `MPESA_CALLBACK_URL` at a public HTTPS URL. Production uses `https://api.safaricom.co.ke` and live credentials stored only in the runtime environment.

## OAuth

`GET {MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials`

HTTP Basic auth with consumer key and secret. The access token is used as `Authorization: Bearer` on STK calls. Tokens, secrets, and passkeys are not logged.

## STK Push

`POST {MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest`

Password is Base64(`ShortCode + Passkey + Timestamp`). Timestamp is `YYYYMMDDHHmmss` in `Africa/Nairobi`. Amount is whole KES (`amount_cents / 100`). `CallBackURL` is `MPESA_CALLBACK_URL`.

`ResponseCode=0` is persisted as `STK_SENT` together with `MerchantRequestID` and `CheckoutRequestID`.

## Architecture

- `infrastructure.payments.mpesa.MpesaClient` — Daraja HTTP (`get_access_token`, `stk_push`).
- `application.services.mpesa.initiate_mpesa_stk` — tenant resolution, amount/phone/invoice checks, `MpesaAttempt` persistence.
- `apps.billing.models.MpesaAttempt` — provider attempt. Optional `invoice` FK is the payment target, not a settlement.

## Not in this phase

- M-Pesa callback settlement
- Creating or allocating `Payment`
- Ledger postings and statement credits
- STK Query
- Transaction Status API
- Paystack
- Frontend Pay Rent UI
- Production deployment and live credentials
- Sandbox callback testing

## Tests

From `backend/`:

```bash
python manage.py test apps.billing.test_mpesa apps.billing.test_mpesa_client
python manage.py test apps common tests
```
