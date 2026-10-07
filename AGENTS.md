# nakout-radio agent guide

## Documenting changes

Every time code or configuration is changed, add an entry to `docs/changelog.md`
(most recent first) containing:

1. Date and one-line summary of the change.
2. Files touched.
3. Whether a Docker container restart is required, and exactly which:
   - `frontend/src/**` changes -> container `frontend` only:
     `docker compose up -d --build frontend`
   - `backend/**` changes -> container `backend` only:
     `docker compose up -d --build backend`
   - `docker-compose.yml`, `Caddyfile` or compose env changes -> the affected
     service(s), plus `caddy` if proxying changed:
     `docker compose up -d --build <service>`
   - Only `docs/**`, tests, or non-served config -> no restart.
   - If both frontend and backend changed -> rebuild both:
     `docker compose up -d --build backend frontend`
4. Verification (tests/typecheck run and result).

## Runtime notes

- The app is deployed via `docker-compose.yml` (services: `caddy` :8010,
  `backend` :8011, `frontend` :8012). Images are built from Dockerfiles; source
  is NOT bind-mounted, so code changes never take effect until the image is
  rebuilt and the container recreated.
- The `frontend` image bakes the built `dist/` bundle in at build time.
- After restarting the frontend, hard-refresh the browser (Ctrl+Shift+R).
