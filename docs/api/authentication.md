# API Authentication

The API uses DRF token authentication. Owner, tenant, and service-professional signup retains the existing immediate token flow. Property-agent signup creates an independent agent account but does not issue a session token until the agent proves email ownership.

## Signup Profiles

`POST /api/v1/accounts/signup/` accepts `account_type`, username, email, password, and `password_confirm`. The passwords must match and pass Django's configured password validators.

Owner signup must include `organization_name`. The API creates the organization and assigns the new account the `OWNER` membership.

Tenant signup may include `organization_id` from `GET /api/v1/accounts/organizations/`, or omit it to choose an organization later by calling `POST /api/v1/accounts/tenant-organization/` with an authenticated token. A tenant does not create an organization by selecting this profile.

Service-professional signup must include `professional_trade` (`ELECTRICIAN`, `CARPENTER`, `PLUMBER`, `PAINTER`, `MASON`, or `OTHER`).

Property-agent signup sends a single-use verification link to the submitted email and returns `email_verification_required: true` with no session token. The link expires after `EMAIL_VERIFICATION_TOKEN_MAX_AGE` seconds (default `86400`) and its token is carried in the URL fragment, so it is not sent to the web server in the initial request. Confirm it with `POST /api/v1/accounts/verify-email/`; the frontend confirmation page submits the token and establishes the agent session only after the backend accepts it. Unverified agents cannot sign in, manage protected agent information, or receive owner advertising authorization. Email confirmation does not itself verify an agent's professional status or authorize any listing.

To resend, call `POST /api/v1/accounts/email-verification/request/` with `{"email":"agent@example.com"}`. It always returns the same `202` response for eligible and unknown addresses and is limited per address and by the normal API throttle. Configure `ACCOUNT_FRONTEND_URL` as the public frontend origin (HTTPS in production), and configure SMTP (`DJANGO_EMAIL_HOST`, `DJANGO_DEFAULT_FROM_EMAIL`, plus provider credentials) before production signup. When local development has no SMTP, Django's console email backend prints the link only in the developer's local console; production email failures are logged without the token or address.

Signup and login responses include `token`, `account_type`, `organization_id`, and `professional_trade` where applicable so a client can route by profile. Signup returns `201`; owners, tenants, and service professionals receive a session token immediately, while property agents receive one only after email confirmation.

## Forgot Password

Request a reset email with `POST /api/v1/accounts/password-reset/`:

```json
{"email": "manager@example.com"}
```

The endpoint returns the same `202` response whether an active account exists or not. If it exists, the email includes `uid` and a time-limited token. Submit them with a new password and confirmation to `POST /api/v1/accounts/password-reset/confirm/`:

```json
{
  "uid": "<uid-from-email>",
  "token": "<token-from-email>",
  "password": "<new-password>",
  "password_confirm": "<same-new-password>"
}
```

The token expires according to Django's `PASSWORD_RESET_TIMEOUT` setting and becomes invalid after use. On success, all existing API tokens for the account are revoked and the user must log in again.

## Login And Logout

Login uses username/password:

```http
POST /api/v1/accounts/login/
Content-Type: application/json

{"username": "manager", "password": "password"}
```

Send the returned token on protected requests as `Authorization: Token <token>`. `POST /api/v1/accounts/logout/` revokes the current token and returns `204`.

The web sign-in form does not ask users to choose a role. After credentials are verified, it routes from the returned account type and active organization memberships: tenants go to the tenant workspace; owners and property managers to property management; accountants, caretakers, and technicians to their respective workspaces. If an account has access to multiple workspace types, the user chooses a workspace after signing in. Organization-specific dashboards then allow selection among the organizations for which that role is active. Staff access must come from an organization invitation; choosing a portal on the sign-in page does not grant access.

```json
{
  "token": "...",
  "memberships": [
    {
      "organization_id": 1,
      "organization_name": "Rongai Homes",
      "role": "CARETAKER"
    }
  ]
}
```

`memberships` contains active memberships in active organizations.

## Authenticated requests

Send the token on every protected request:

```http
Authorization: Token <token>
```

## Logout

```http
POST /api/v1/accounts/logout/
Authorization: Token <token>
```

A successful logout returns `204` and revokes the token. Use HTTPS outside local development and never commit real credentials or tokens.

In production, signup is limited to 5 requests per hour, login to 10 per minute, organization lookup to 60 per minute, password-reset requests to 3 per hour, reset confirmations to 5 per hour, email-verification resend requests to 5 per hour per source, and verification confirmations to 10 per hour per source. Resends are additionally limited to three deliveries per email per hour. Production throttling requires a shared cache. Production startup requires explicit environment, secret, and host settings, TLS-protected SMTP, and HTTPS CORS origins. See [backend/.env.example](../../backend/.env.example) for configuration names. Use HTTPS outside local development.
