# API Authentication

The API uses DRF token authentication. Email verification is currently disabled; signup activates the account and returns a token immediately.

## Signup Profiles

`POST /api/v1/accounts/signup/` accepts `account_type`, username, email, password, and `password_confirm`. The passwords must match and pass Django's configured password validators.

Owner signup must include `organization_name`. The API creates the organization and assigns the new account the `OWNER` membership.

Tenant signup may include `organization_id` from `GET /api/v1/accounts/organizations/`, or omit it to choose an organization later by calling `POST /api/v1/accounts/tenant-organization/` with an authenticated token. A tenant does not create an organization by selecting this profile.

Service-professional signup must include `professional_trade` (`ELECTRICIAN`, `CARPENTER`, `PLUMBER`, `PAINTER`, `MASON`, or `OTHER`).

Signup and login responses include `token`, `account_type`, `organization_id`, and `professional_trade` where applicable so a client can route by profile. Signup returns `201` and activates the account immediately.

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

Signup is limited to 5 requests per hour, login to 10 per minute, organization lookup to 60 per minute, password-reset requests to 3 per hour, and reset confirmations to 5 per hour. Production throttling requires a shared cache. Production startup also requires explicit secret and host settings, TLS-protected SMTP, and HTTPS CORS origins. See [backend/.env.example](../../backend/.env.example) for configuration names. Use HTTPS outside local development.
