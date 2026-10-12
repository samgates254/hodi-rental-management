# Development Commands

Run checks:

```bash
cd backend
env/bin/python manage.py check
```

Run the installed-app tests:

```bash
cd backend
env/bin/python manage.py test apps.accounts
```

As domain tests are added, include their app labels, for example:

```bash
cd backend
env/bin/python manage.py test apps.accounts apps.organizations apps.properties apps.tenants apps.leases
```

Run the complete repository suite from `backend/` (this explicitly includes
installed-app tests under `src/apps`, which are not discovered by a bare
`manage.py test` from this checkout):

```bash
.venv/bin/python manage.py test apps common tests engines rental_os.tests
```

Use the app labels above for focused runs, for example
`.venv/bin/python manage.py test apps.utilities apps.billing`.

Run authenticated browser integration tests from `frontend/`:

```bash
npm run test:e2e
```

This starts Django and Next.js on ports 8765 and 8766 against a newly created,
disposable SQLite database under `/tmp/hodi-e2e-*`, runs migrations and
consistency checks, and removes the database and generated temporary account
credentials afterward. It requires the repository's backend virtualenv,
Playwright, and Google Chrome at `/usr/bin/google-chrome` (override with
`CHROME_BIN`). It refuses to run when `DJANGO_ENV=production` and never seeds
the configured development database.

## HODI Integration Verification Milestone — 13 October 2026

These are automated local verification results. The authenticated browser
checks exercised the real Next.js frontend and Django API against a disposable
SQLite database; they are not manual exploratory tests or production
validation.

### Backend and framework checks

- Backend suite: 445 tests discovered, 443 passed, 2 skipped, 0 failed. Both
  skipped tests require PostgreSQL.
- Django system check passed.
- Migration consistency check passed.
- Frontend: `npx tsc --noEmit` passed; `npm run lint` reported 0 errors and
  15 warnings; `npm run build` passed.

### Authenticated Playwright workflows

All three browser tests passed against the real frontend and API:

1. **Tenant and seller:** A tenant submitted a service request; it remained
   after refresh. An authorised seller updated its status, which also remained
   after refresh. Another tenant could not see the request, and another
   organisation could not modify the seller's order or listing.
2. **Utilities:** Two tenants saw only bills for their respective leased
   units. Private landlord account references and provider details were not
   exposed, and tenants could not edit bills.
3. **Procurement:** A supplier-linked purchase was recorded against an
   approved quotation line for KES 200,000. Idempotent replay and stored price
   history were checked. The purchaser could not acknowledge their own
   purchase; an authorised caretaker could acknowledge receipt.
4. **Accountant access:** The intended accountant accepted an organisation
   owner's invitation and saw a recorded KES 25,000 invoice, but could not
   access another organisation's records. A different account could not
   accept the invitation. Acceptance was idempotent, and revocation removed
   subsequent access.

### Environment and verification limits

- Browser tests used a fresh temporary SQLite database. Generated test
  accounts and credentials were removed afterward; the existing development
  database was not modified. No migration files were added during this
  browser verification.
- Commerce orders remained unpaid. Marketplace M-Pesa checkout and live
  M-Pesa settlement were not tested.
- The two PostgreSQL-specific tests were skipped. SQLite browser tests do not
  verify PostgreSQL concurrency behavior.
- Durable production file storage was not verified. These checks do not
  establish production readiness or market traction.

### Repeat the checks

Run the complete backend suite as documented above:

```bash
cd backend
.venv/bin/python manage.py test apps common tests engines rental_os.tests
```

Run authenticated browser tests:

```bash
cd frontend
npm run test:e2e
```

Run the frontend checks:

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```
