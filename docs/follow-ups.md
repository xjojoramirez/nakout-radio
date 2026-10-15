# Follow-ups

Recommended improvements from the 2026-10-15 project review, most valuable
first. None of these are bugs; each entry notes what it is, why it matters,
and the fix sketch. Delete entries here as they land.

## 1. CI workflow (`.github/workflows/ci.yml`)

There is no CI: every verification is run by hand (and `main` is
PR-protected, so a PR can merge with failing tests). Add a workflow on
`pull_request` with two jobs reproducing the commands already used in the
changelog verification lines:

- backend: Python 3.12, `pip install -r requirements-dev.txt`, `pytest -q`
  (no secrets needed — `backend/tests/conftest.py` sets the required env
  defaults itself).
- frontend: Node 20, `npm ci`, `npm test`, `npm run typecheck`,
  `npm run build`.

Catches forgotten runs, Linux-vs-Windows differences (case-sensitive paths,
CRLF), and dependency breakage before merge.

## 2. SQLite WAL + explicit busy_timeout (`backend/app/db.py`)

Verified defaults on this stack (SQLAlchemy 2.0.36):
`journal_mode=delete`, `busy_timeout=5000`. In rollback-journal mode a writer
locks the whole database, so concurrent writes (broadcast state save at song
boundaries, playlist sync commits, admin edits, session revocation) can
transiently collide with listener polls to `/api/now` and raise
`database is locked`.

Fix: register a `connect` event on the SQLite engine that runs
`PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`. WAL is persistent in
the database file; it adds `radio.db-wal` / `radio.db-shm` siblings inside the
`/data` volume (the README's volume-level backup already covers them).

## Lower-priority nits (same review)

- Dead API surface: `GET /api/genres/{slug}` and `POST /api/queue/advance`
  (plus `api.getGenre` / `api.advance` in the frontend client and
  `CurrentGenre.cursor`, now always `null`) are unused by the UI — remove them
  or mark them deprecated.
- `formatClock` is duplicated in `frontend/src/utils/format.ts` and
  `frontend/src/utils/deck.ts`.
- `fetch_playlist_items` (`backend/app/youtube.py`) lacks the `seen_tokens`
  page-token loop guard its sibling `fetch_channel_playlists` has.
- `frontend/src/hooks/useYouTubePlayer.ts` (~715 lines of timers/refs) is the
  riskiest file in the repo; its DOM tests are the spec — change with care.
- `advance()` catch-up is capped at 10,000 iterations with a DB query per
  boundary; fine at this scale, but after a very long outage with short
  tracks the first `/api/now` could be slow.
