# Daraja sandbox setup

HODI's integration uses Daraja OAuth, M-Pesa Express (STK Push), the STK callback, the STK Query endpoint, and the existing `reconcile_mpesa_attempts` management command. Provider credentials stay in the Django backend environment. The browser only receives an HODI attempt ID and its tenant-scoped status.

## Create a sandbox application

1. Register or sign in at the [Safaricom Daraja developer portal](https://developer.safaricom.co.ke/).
2. Create an application in the Sandbox environment and enable the M-Pesa Express product. Safaricom documents sandbox app credentials and test data in its [official FAQ](https://developer.safaricom.co.ke/faqs).
3. Copy the sandbox consumer key and consumer secret from the application page. Obtain the sandbox shortcode and Lipa na M-Pesa passkey from the product's sandbox/test credentials. Choose the transaction type matching the provisioned PayBill or Buy Goods flow.
4. Do not use production credentials for local development.

The backend uses the documented OAuth client-credentials route `GET /oauth/v1/generate?grant_type=client_credentials`, then Daraja's M-Pesa Express routes `POST /mpesa/stkpush/v1/processrequest` and `POST /mpesa/stkpushquery/v1/query`. The official [Authorization API documentation](https://developer.safaricom.co.ke/apis/Authorization) describes bearer-token use and token expiry; the [M-Pesa Express API page](https://developer.safaricom.co.ke/apis/MpesaExpressSimulate) is the provider's product reference. Sandbox requests use `https://sandbox.safaricom.co.ke`; production is an explicit separate environment at `https://api.safaricom.co.ke`.

## Configure local Django

Copy `backend/.env.example` to the ignored `backend/.env` and set the following values locally. Keep the file out of version control and do not paste credentials into chat, tickets or logs.

```dotenv
MPESA_ENVIRONMENT=sandbox
MPESA_CONSUMER_KEY=
MPESA_CONSUMER_SECRET=
MPESA_SHORTCODE=
MPESA_PASSKEY=
MPESA_TRANSACTION_TYPE=CustomerPayBillOnline
MPESA_CALLBACK_URL=https://<public-host>/api/v1/billing/mpesa/callback/<random-token>/
MPESA_CALLBACK_AUTH_TOKEN=<same-random-token>
MPESA_TIMEOUT_SECONDS=30
```

Generate the callback token locally with a cryptographically secure generator (for example, `openssl rand -hex 32`) and place it in both the backend setting and callback path. Do not reuse this value as an API consumer credential.

Development defaults to the sandbox host. If `MPESA_BASE_URL` is set, it must exactly match the host selected by `MPESA_ENVIRONMENT`; HODI rejects mismatched or non-HTTPS endpoints. Initiation also fails closed unless the callback token is configured and present as a path segment in the HTTPS URL. Production requires `MPESA_ENVIRONMENT=production`, complete live configuration and the required long callback token. Do not change the environment to production until Safaricom has approved the production application/product and shortcode and HODI's payment operations are ready. To disable Daraja, leave consumer credentials, shortcode, passkey, callback URL and callback token unset; initiation fails closed before an STK request.

The callback URL is public and HTTPS. Daraja cannot send HODI's custom authorization header, so HODI retains a high-entropy bearer token as one callback URL path segment. This is a defense-in-depth gate, not a Safaricom signature. Reverse proxies, load balancers, APM agents and web server access logs must redact that path segment. The repository cannot configure or verify those deployment logs; do not enable full callback URL logging. Rotate by configuring a new token and matching URL together, updating the Daraja callback URL, then retiring the old token after in-flight requests have drained.

For local callback testing, expose the Django listener through a temporary public HTTPS tunnel and use that HTTPS address as `MPESA_CALLBACK_URL`. Restrict tunnel access and remove it after the test. Never use real tenant credentials or production funds in sandbox testing.

## Request and settlement flow

The authenticated tenant submits an outstanding ledger invoice/amount, a Kenyan mobile number and a UUID idempotency key. HODI stores the attempt before making the STK POST. Amounts are represented internally as integer KES cents; Daraja's whole-KES amount is derived only when cents are divisible by 100. The browser retains the same idempotency key across a lost response so repeating a request cannot send a second prompt.

Daraja's accepted STK response means only that the prompt was accepted. HODI does not settle the ledger then. A callback must match the persisted checkout and merchant request IDs, pass the callback gate, match the provider STK Query transaction outcome and carry valid receipt, amount, phone and date metadata. The existing transaction-locked settlement path posts/allots the receipt-backed payment once. Conflicting or incomplete evidence stays unresolved; HODI does not fabricate a receipt from STK Query.

If a callback is lost, schedule `PYTHONPATH=src:. .venv/bin/python manage.py reconcile_mpesa_attempts --dry-run` first, then run the same command without `--dry-run` from the backend directory on an operational schedule. Start with the dry run and a small `--limit`; use `--stale-minutes` to tune eligibility. Query results that prove success but lack the receipt needed for HODI's ledger remain in `SUCCESS_NEEDS_RECEIPT` for operator review. Timeouts without provider request IDs are listed with `--review-required`; they cannot be queried automatically. Reconciliation is not active unless deployment schedules this command.

Reconciliation treats HTTP errors, malformed responses, mismatched request IDs, missing result fields and unrecognized result codes as unresolved. It only automatically closes an attempt for a matching terminal cancellation/timeout result code. A query HTTP 500 therefore cannot be interpreted as a payment failure. Safaricom's public Daraja pages describe the sandbox and simulator, but do not specify a unique cause for an STK Query HTTP 500; diagnose it from the exact sanitized request configuration and Safaricom's support-side request trace rather than assuming a malformed request or a sandbox defect.

For sandbox testing, create an app with the M-Pesa Express product and use the Daraja portal's sandbox simulator/test data. The portal's public documentation does not establish that every accepted sandbox STK Push will produce a handset prompt or callback. `ResponseCode: 0` remains request acceptance only. Test callback processing with captured, provider-generated sandbox callback data or the portal simulator; never synthesize a callback as proof of settlement. A public HTTPS callback endpoint is required for Daraja-to-local delivery.

The status endpoint is `GET /api/v1/billing/mpesa/attempts/<attempt-id>/` and only returns the authenticated tenant's own attempt. Payment history remains sourced from the ledger, not the legacy rent-payment table.

## Safe checks

Run mocked tests without provider credentials:

```bash
cd backend
PYTHONPATH=src:. .venv/bin/python manage.py test apps.billing.test_mpesa_client apps.billing.test_mpesa apps.billing.test_mpesa_callback apps.billing.test_mpesa_reconciliation
```

These tests do not contact Safaricom. Real sandbox connectivity is unverified until sandbox credentials and a public HTTPS callback have been configured and exercised.
