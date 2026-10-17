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

- The app is deployed via `docker-compose.yml` (services: `caddy` on host
  ports 80/443; `backend` :8011 and `frontend` :8012 are bound to loopback
  only). Images are built from Dockerfiles; source is NOT bind-mounted, so
  code changes never take effect until the image is rebuilt and the container
  recreated.
- The `frontend` image bakes the built `dist/` bundle in at build time.
- After restarting the frontend, hard-refresh the browser (Ctrl+Shift+R).

## Git & GitHub accounts

All git and GitHub activity in this project must use the **xjojoramirez**
account — never `jojoxprimary`:

- Commits: the repo-local git config is
  `Jojo Ramirez <31147978+xjojoramirez@users.noreply.github.com>`.
- `gh` CLI: `gh auth switch --user xjojoramirez` and confirm the active
  account before any `gh` command (PRs, issues, API calls).
- `main` is protected by the repository ruleset `main-protection`
  (no force-pushes or deletion; changes land via pull requests) — push a
  branch and open a PR instead of committing to `main` directly.
- PR bodies: every pull request must end with a `Container restart` section
  stating the required rebuild(s) exactly as the changelog entry does, e.g.
  `Yes — backend only: docker compose up -d --build backend`; docs/tests-only
  PRs say `No restart required`.
