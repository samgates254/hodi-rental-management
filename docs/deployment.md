# HODI deployment on Render

This guide configures the existing Django API and Next.js frontend as separate Render web services backed by Render PostgreSQL. Keep the frontend and API in the same Render region where possible. The backend serves Django static assets with WhiteNoise; the frontend proxies `/api/v1/` to the Django HTTPS origin.

Render's [Django deployment guide](https://render.com/docs/deploy-django), [web service settings](https://render.com/docs/web-services), and [deploy pipeline](https://render.com/docs/deploys) describe the platform settings referenced below.

## Django API service

Create a Render **Web Service**, runtime **Python**, using this repository and configure:

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt && python manage.py collectstatic --no-input` |
| Pre-Deploy Command | `python manage.py migrate && python manage.py createcachetable hodi_cache` |
| Start Command | `gunicorn config.wsgi:application --chdir src --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Health Check Path | `/api/v1/health/` |

The pre-deploy command runs against the connected database before the new instance receives traffic. Render currently offers pre-deploy commands on eligible service plans. If unavailable, run the same migration/cache-table command once from the service shell before routing traffic to the new release. Do not run migrations in the image build, where the database should not be needed.

### PostgreSQL

Create a Render PostgreSQL database in the API service's region. Link its **internal connection string** to the web service as `DATABASE_URL` using Render's database environment-variable integration; do not paste or print the URL in source control, logs, or this document. The app uses `dj-database-url` with a 600-second persistent connection age and connection health checks when `DATABASE_URL` is present.

Production settings explicitly reject any configured database backend other than Django's PostgreSQL backend. This also rejects production startup when `DATABASE_URL` is absent and the fallback would select SQLite. The `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` fallback remains available; it can be used with a PostgreSQL `DB_ENGINE` where an operator-managed connection is appropriate. SQLite remains the default for local development and tests only. For Render, configure the linked PostgreSQL `DATABASE_URL`.

Set `DJANGO_ENV=production` explicitly. If that variable is omitted, settings reject common deployment markers such as a non-local host, PostgreSQL connection, `DEBUG=False`, production SMTP, or live Daraja mode instead of silently using development protections. Local settings remain convenient when those markers are absent.

Before switching production traffic to a release, provision the PostgreSQL database, configure a reachable PostgreSQL connection and credentials, and run the reviewed migrations against that database from the pre-deploy step. Confirm the API health check returns HTTP 200 before routing customer traffic. Do not use SQLite as a production fallback.

The compatible `/api/v1/health/` endpoint checks database connectivity with Django's connection API. HTTP 200 with `{"status":"ok"}` means the application can connect to its database. HTTP 503 with a generic database-unavailable response means the application answered the health request but its database connection check failed; inspect application startup and database-provider availability through secured operator tooling. A timeout, connection refusal, or proxy error means the application did not return a health response and should be investigated as an application startup, process, or routing failure. The response intentionally contains no exception, SQL, URL, or credential details.

### Required API environment variables

Set these in the Render service's Environment page. Values shown in angle brackets are instructions to supply real deployment-specific values, not literal credentials.

| Name | Initial value / guidance |
| --- | --- |
| `DJANGO_ENV` | `production` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | Generate a unique secret of at least 50 characters in Render. Never put it in the repository. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated backend hostnames only, without schemes, e.g. `<api-service>.onrender.com,<api-custom-domain>` |
| `DATABASE_URL` | Link the Render PostgreSQL internal connection string. |
| `CORS_ALLOWED_ORIGINS` | HTTPS origins for browser clients, e.g. `https://<frontend-service>.onrender.com`; no trailing paths. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS frontend and backend origins, e.g. `https://<frontend-service>.onrender.com,https://<api-service>.onrender.com`. |
| `DJANGO_TRUSTED_PROXY_SSL_HEADER` | `HTTP_X_FORWARDED_PROTO,https`. Render terminates TLS and forwards the original scheme; trust this header only while the app is behind Render's proxy. |
| `DJANGO_EMAIL_HOST` | SMTP hostname from the chosen email provider. Required by production settings. |
| `DJANGO_DEFAULT_FROM_EMAIL` | A sender address authorized by the email provider. Required by production settings. |
| `ACCOUNT_FRONTEND_URL` | HTTPS public frontend origin used in agent email-verification and password-reset links. |
| `DJANGO_CACHE_BACKEND` | `django.core.cache.backends.db.DatabaseCache` for the shared database-backed cache. |
| `DJANGO_CACHE_LOCATION` | `hodi_cache` (must match the `createcachetable` pre-deploy command). |
| `MPESA_ENVIRONMENT` | Explicitly set to `sandbox` for initial deployment. Do not switch to `production` until live credentials and callback verification have been reviewed. |
| `MPESA_CALLBACK_AUTH_TOKEN` | Generate a unique random value of at least 32 characters; store as a secret. |
| `MPESA_CALLBACK_URL` | HTTPS callback URL whose path contains the exact callback token, e.g. `https://<api-service>.onrender.com/api/v1/billing/mpesa/callback/<token>/`. Follow the existing callback log-redaction guidance. |

Production settings continue to enforce `DEBUG=False`, a strong secret key, explicit non-wildcard hosts, HTTPS-only CORS origins, SMTP host/from configuration, a shared cache, and M-Pesa callback requirements. Do not remove or weaken those checks to make deployment start.

### Email, cache and M-Pesa values

The following settings have safe code defaults but should be explicitly reviewed in Render:

| Name | Initial value / guidance |
| --- | --- |
| `DJANGO_EMAIL_PORT` | `587` |
| `DJANGO_EMAIL_USER` | SMTP account username if the provider requires authentication; otherwise leave empty. |
| `DJANGO_EMAIL_PASSWORD` | SMTP password/app credential if required; store as a Render secret. |
| `DJANGO_EMAIL_USE_TLS` | `True` for submission on port 587. |
| `DJANGO_EMAIL_USE_SSL` | `False`; do not enable TLS and SSL together. |
| `DJANGO_EMAIL_TIMEOUT` | `10` seconds. |
| `MPESA_BASE_URL` | Leave unset to use the sandbox host selected by `MPESA_ENVIRONMENT=sandbox`, or set `https://sandbox.safaricom.co.ke`. |
| `MPESA_CONSUMER_KEY` | Leave empty to keep STK initiation disabled; if sandbox testing is later authorized, store the sandbox key as a secret. |
| `MPESA_CONSUMER_SECRET` | Leave empty to keep STK initiation disabled; otherwise store the sandbox secret as a Render secret. |
| `MPESA_SHORTCODE` | Leave empty to keep STK initiation disabled; otherwise use the authorized sandbox shortcode. |
| `MPESA_PASSKEY` | Leave empty to keep STK initiation disabled; otherwise store the sandbox passkey as a Render secret. |
| `MPESA_TIMEOUT_SECONDS` | `30` |
| `MPESA_TRANSACTION_TYPE` | `CustomerPayBillOnline` unless the configured sandbox product requires the supported `CustomerBuyGoodsOnline` value. |
| `EMAIL_VERIFICATION_TOKEN_MAX_AGE` | `86400` seconds. |
| `PASSWORD_RESET_TIMEOUT` | `3600` seconds. |

Production settings require a callback URL and long callback token even while the environment is sandbox. The provider consumer credentials, shortcode, and passkey can remain empty; the M-Pesa initiation flow then fails closed. Do not initiate payments during deployment checks. Application callback logs avoid request paths and callback contents. The configured Gunicorn command does not enable its access log, but hosting/platform request logs are outside this repository and have not been checked; the token in the callback path may still be recorded there. Verify platform log redaction before enabling live integration. See [Daraja deployment guidance](./payments/daraja-sandbox-setup.md) and the [M-Pesa API contract](./api/mpesa.md).

## Database migration and recovery

1. Before the first deploy, verify the linked database and take/confirm a recoverable database backup according to the selected Render PostgreSQL plan.
2. Use the pre-deploy command above for normal, backward-compatible migrations. Review `python manage.py showmigrations` and `python manage.py migrate --plan` before a planned schema change.
3. Avoid destructive migrations and deploy schema changes in an expand/contract sequence so the previous application release can still run during rollback.
4. If a deploy fails before switching traffic, Render keeps the previously successful release serving. Roll back the application release from Render's Deploys page; do not assume that application rollback reverses database changes.
5. If a migration has already changed persistent data, do not blindly restore an old database snapshot over newer customer writes. Pause writes if necessary, assess the migration and backup point, then use a reviewed forward-fix or a deliberate database recovery plan.

## Static files and uploaded media

`collectstatic` writes to `backend/staticfiles` (`STATIC_ROOT`). `STATIC_URL` is `/static/`; Django 5.2's `STORAGES` uses `whitenoise.storage.CompressedManifestStaticFilesStorage`, and WhiteNoise middleware follows `SecurityMiddleware`. The build command collects the versioned, compressed files and the running service serves them.

User-uploaded media is separate from static files. Render's service filesystem is not a durable customer-file store across deploys; configure durable object storage or an appropriately mounted persistent disk for `MEDIA_ROOT` before accepting customer uploads in production. Do not treat `collectstatic` as a media backup.

## Next.js frontend service

Create a separate Render **Web Service**, runtime **Node**, with:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Start Command | `npm start` |

Set `API_PROXY_TARGET` as a **build-time** environment variable to the deployed Django HTTPS origin, for example `https://<api-service>.onrender.com`. The Next.js rewrite manifest is produced during `next build`, and the Next.js server must be able to reach the API origin. The public plans request is `GET /api/v1/subscriptions/plans/`. Do not set a production localhost target or add credentials to frontend build variables. If hosting ingress routes `/api/v1/*` directly to Django instead, configure that route explicitly and verify it before launch.

The `/admin` frontend route redirects to Django admin. Set `DJANGO_ADMIN_URL` to the deployed Django `/admin/` URL when the backend origin is not available through `API_PROXY_TARGET`; in local development it defaults to `http://127.0.0.1:8000/admin/`. `/hodi-admin/revenue` is the separate HODI subscription operations workspace.

## First-deploy checks

1. After PostgreSQL is provisioned and migrations complete, confirm the API health check returns HTTP 200 at `https://<api-service>.onrender.com/api/v1/health/` before switching traffic.
2. Confirm the frontend's `/pricing` page can load the public plans through its configured API route.
3. Confirm `/static/` assets load and admin styles render after `collectstatic`.
4. Check Django logs for configuration errors without printing environment values or secret-bearing URLs.
5. Verify HTTPS redirects, secure cookies, HSTS, trusted hosts, CSRF and CORS with the actual Render domains.
6. Confirm database backups and media persistence before onboarding customers.
7. Keep M-Pesa sandbox-only until the live Safaricom application, credentials, callback verification, token handling and redacted logging have each been independently approved.

These instructions document deployment requirements; they do not mean production hosting, backup restoration, or live external connectivity has been tested.
