# Production deployment

## Next.js API routing

The frontend API client uses same-origin `/api/v1/` URLs by default. The Next.js configuration rewrites those requests to Django when `API_PROXY_TARGET` is set. Next.js generates its rewrite manifest during `next build`, so the target must be provided to the build environment and the resulting build artifact must be deployed unchanged. The Next.js server must be able to reach the configured backend origin.

For a server-rendered Next.js deployment, configure the backend's reachable HTTPS origin as a non-secret build variable:

```sh
cd frontend
API_PROXY_TARGET=https://api.example.com npm run build
npm run start
```

Replace `https://api.example.com` with the actual Django API origin. Do not use a localhost address in a production build. `API_PROXY_TARGET` is an origin, not a full endpoint: the rewrite forwards `/api/v1/...` and preserves the path and query string. The public pricing page obtains its active catalogue from `GET /api/v1/subscriptions/plans/`; it does not contain fallback plan prices.

If a platform terminates routing before the Next.js server (or the frontend is deployed as static files), configure its ingress/proxy to send `/api/v1/*` to the Django backend instead. In that topology, `API_PROXY_TARGET` may be omitted because the hosting layer owns this route. Ensure the backend's allowed-host and CORS settings match the deployment topology; do not put credentials in frontend build variables.

Without either the build-time rewrite or an upstream `/api/v1/` route, API calls reach Next.js and return 404. Pricing correctly shows its unavailable/retry state in that case instead of inventing prices.
