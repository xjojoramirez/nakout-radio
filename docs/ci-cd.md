# CI/CD pipeline

How a commit gets from a branch to production, what each stage checks, and how
to operate it. The authoritative definitions are `.github/workflows/ci.yml` and
`.github/workflows/load.yml`; this page explains the intent behind them.

## In one sentence

Every push is verified by staged quality gates, green `main` commits are
published once as SHA-tagged container images, and production runs exactly the
published artifact.

## Flow

```
 pull request / push to main
              |
              +-- Frontend job --- lint, typecheck, unit tests,
              |                    production build, bundle budget, npm audit
              +-- Backend job ---- ruff, pip-audit, pytest
              |
              +-- Image build ---- Dockerfiles build; on main: push :<sha>
              +-- Integration ---- real compose stack: migrations, nginx,
              |                    admin login, WebSocket, public endpoints
              +-- E2E ------------ Chromium: real browser against the stack
              |
              +-- Promote -------- main only, only if every job passed:
                                   retag :latest to the identical :<sha> digest
```

Pull requests stop at the checks. Pushes to `main` continue through publish and
promotion, but **deployment is still manual** - nothing reaches the server on
its own.

## Stages

| Stage | Question it answers | Details |
| --- | --- | --- |
| Frontend | Does the UI logic work and still fit its budget? | Node 24, `npm ci`, oxlint, `tsc`, Vitest, Vite build, gzip bundle budget, `npm audit --audit-level=high` |
| Backend | Is the API correct and free of known vulnerable dependencies? | Python 3.12, Ruff, `pip-audit`, pytest against SQLite |
| Image build | Do the Dockerfiles produce runnable images? | Buildx matrix for both services; pushed as `ghcr.io/...:<full-sha>` on `main`, loaded locally on pull requests |
| Integration | Does the assembled system work? | Throwaway `nakout-ci` compose project: health, genres, schedule, frontend through nginx, `/api` proxy, admin login/session, `alembic current` at head plus `alembic check`, listener WebSocket |
| E2E | Can a person actually use it? | Playwright + Chromium: log in, create a genre, schedule it, see it on the public page, log out; external requests aborted |
| Bundle budget | Did the frontend get fat? | 95 kB JS / 13 kB CSS gzip, checked from `dist/` by `frontend/scripts/check-bundle-size.mjs` |
| Publish / promote | Can we deploy exactly what was tested? | `:<sha>` is pushed once; on green `main`, `latest` is retagged to that same digest with `docker buildx imagetools create` (no rebuild) |

Ordering is deliberate: cheapest and most deterministic checks first. A typo
fails in seconds; the browser suite only runs once the cheap stages pass. The
browser suite is a single serial test with `workers: 1` and `retries: 0` so a
failure means a real failure, not runner noise.

## Build once, promote the same artifact

The server used to rebuild images from source, which meant the deployed code
could drift from the tested code. Now:

1. CI builds each image once per commit and, on `main`, pushes it as `:<sha>`.
2. Integration and E2E build and exercise the same commit in a throwaway
   compose stack.
3. `latest` moves only after every job passes, by retagging the existing
   registry digest - not by rebuilding.
4. The server pulls the image and starts it with `--no-build`.

Consequences:

- Production runs an image CI built from the commit that passed every check,
  never one rebuilt on the server.
- Rolling back is a tag change, with no rebuild and no toolchain on the server.
- The VPS no longer needs Node, Python or build layers to deploy.

Both images target `linux/amd64`. A deploy to another architecture would need a
second platform added to the build first.

## Nightly load test

`.github/workflows/load.yml` runs at **03:17 UTC** and on manual dispatch. It is
not a pull request gate: shared runners are noisy, so a slow minute would fail
honest changes.

- Builds the checked-out commit into a throwaway `nakout-load` stack
- 20 virtual users for 60s against health, genres, schedule and the frontend
  through nginx
- 5 listeners holding real WebSocket connections for 8s each
- Thresholds: checks > 99%, failed requests < 1%, p95 < 500 ms, WebSocket
  handshake p95 < 2s, at least one listener message
- Uploads `k6-summary` (14 days), dumps logs on failure, always tears down

Threshold failures fail the run, so GitHub's default failure notification
applies; successful nights stay quiet. It never touches production.

It catches what functional tests cannot see: slow queries, SQLite lock
contention, WebSocket leaks and listener-count regressions.

## Operating it

**A pull request is red.** Open the failing job, fix the cause, push to the same
branch. Superseded pull request runs are cancelled automatically; a new push
starts a fresh run.

**`main` is red.** The push's pipeline is queued rather than cancelled, so an
in-flight promote always finishes. Fix forward with a new pull request; do not
force-push `main` (the `main-protection` ruleset blocks it anyway).

**Raise the bundle budget.** Edit the two constants at the top of
`frontend/scripts/check-bundle-size.mjs`; the change is visible in review.
`BUNDLE_JS_BUDGET_KB` and `BUNDLE_CSS_BUDGET_KB` override them locally.

**Change load thresholds or shape.** Edit `options` in
`load/k6/listener-load.js`. Run it locally against a throwaway stack with
`k6 run load/k6/listener-load.js` and `API_URL` / `WEB_URL` / `WS_URL`
overrides.

**Re-run a nightly.** Actions -> Nightly load test -> Run workflow. It can also
be dispatched against a branch to test a change before merging.

## Deploying and rolling back

Full instructions, including backups and verification, are in the README
sections **Production deploy**, **Container images** and **Updating**. Short
version:

```bash
git pull
export IMAGE_TAG=<full-green-sha>
docker compose pull backend frontend
docker compose up -d --no-build backend frontend
```

Rollback is the same commands with the previous SHA, or with a locally preserved
`pre-ghcr` tag. Migrations run automatically on backend start
(`backend/entrypoint.sh`), so roll back the image if a migration is the problem;
restore the volume backup if the data itself is wrong.

## Vocabulary

| Term | Meaning here |
| --- | --- |
| Continuous integration | Every push is built and verified automatically |
| Continuous delivery | Every green `main` commit yields a deployable image; deployment is a human decision |
| Continuous deployment | Not used - merges do not reach production automatically |
| Quality gate | A stage that blocks promotion when it fails |
| Shift left | Cheap checks run before containers and browsers |
| Artifact promotion | Moving the tested image forward by tag, never rebuilding |
| Ephemeral environment | A per-run compose stack that is destroyed with `down -v` |
| Scheduled regression testing | The nightly k6 canary, too slow/noisy for every pull request |

This is a **deployment pipeline with quality gates**, closer to *Continuous
Delivery* than to GitOps: the server pulls a published artifact on command, and
no agent watches the repository.

## Files

| Path | Role |
| --- | --- |
| `.github/workflows/ci.yml` | Pull request and `main` pipeline |
| `.github/workflows/load.yml` | Nightly / manual load canary |
| `load/k6/listener-load.js` | k6 scenarios, thresholds and summary |
| `frontend/scripts/check-bundle-size.mjs` | Gzip bundle budget |
| `frontend/e2e/app.spec.ts` | Browser E2E test |
| `frontend/playwright.config.ts` | Chromium, one worker, no retries |
| `docker-compose.yml` | `${IMAGE_TAG:-latest}` for both services |
| `docs/changelog.md` | Per-change history, including verification |
