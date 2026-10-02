# API Authentication

The API uses DRF token authentication.

## Login

```http
POST /api/v1/accounts/login/
Content-Type: application/json

{"username": "manager", "password": "password"}
```

Response:

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
