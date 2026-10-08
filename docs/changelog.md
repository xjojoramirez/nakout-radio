# Changelog

Most recent entries first. Each entry notes whether a Docker container
restart is required (see `AGENTS.md` for the restart commands).

## 2026-10-08 — Publish Caddy on standard ports 80/443 for a public domain

- Changed the `caddy` service port mapping from `8010:443` to `80:80` and
  `443:443` so automatic HTTPS (Let's Encrypt HTTP-01 / TLS-ALPN challenges)
  works for a real domain. Previously only container `443` was exposed on host
  `8010`, which no public ACME challenge could reach.
- Files touched:
  - `docker-compose.yml`
  - `docs/changelog.md` (docs)
- **Container restart required (caddy + proxy ports changed):**
  `docker compose up -d --build caddy` (recreates the container with the new
  port bindings; DNS must point at the host and ports 80/443 must be open).
- Verification:
  - No code/tests changed; config-only. Confirm with `docker compose ps` that
    `caddy` publishes `0.0.0.0:80->80/tcp` and `0.0.0.0:443->443/tcp`, then load
    `https://<domain>` and check the certificate is publicly trusted.

## 2026-10-08 — Admin Stop control takes the station off air

- Added a **Stop** button to the admin Now Playing transport. Pressing it takes
  the station off air for everyone: `/api/now` reports `source: "none"` and the
  public homepage shows the offline screen, until an admin resumes.
- Backend: new `broadcast.stop()` stores an empty *manual* `BroadcastState`
  (`genre_id=None, track_ids=[], manual=True`). Because `advance()` routes
  manual states to `_advance_manual()`, which returns immediately with no
  tracks, the schedule/default is not re-resolved while stopped — so it stays
  off air across requests and restarts. `POST /api/admin/playback/stop`
  (admin-only) calls it and pushes the new state to radio WebSocket clients.
  Play / Next / Prev build a manual state with tracks and Auto re-inits from the
  schedule, so all existing resume paths still work.
- Frontend: `api.playbackStop()`; Stop button enabled only while a track is on
  air; Auto is now enabled when the source is `manual` **or** `none`, so it
  resumes the schedule after a stop (still disabled while `schedule`/`default`).
- No DB migration (state is stored in the existing `broadcast_state` Setting).
- Files touched:
  - `backend/app/broadcast.py`, `backend/app/routers/admin.py`
  - `backend/tests/test_live_control.py`, `backend/tests/test_admin.py` (tests)
  - `frontend/src/api/client.ts`
  - `frontend/src/components/admin/NowPlayingPanel.tsx`
  - `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` (tests)
  - `docs/changelog.md` (docs)
- **Container restart required (both changed):**
  `docker compose up -d --build backend frontend`, then hard-refresh the browser.
- Verification:
  - `python -m pytest` 205 passed (new: stop goes off air and stays, stop then
    auto resumes, stop then play resumes, stop endpoint off-air/auto, stop
    requires auth).
  - `npm test` 109 passed (new: Stop calls the API and notifies; Stop disabled
    when off air; Auto enabled after a stop).
  - `npm run typecheck` clean; `npm run build` succeeds.

## 2026-10-08 — Homepage offline screen when nobody is broadcasting

- When the backend reports `source: "none"` (nobody playing / no scheduled
  track), the homepage now shows a dedicated "Radio offline" screen with an
  unlit power LED and a dimmed cabinet, instead of the empty now-playing panel
  plus MUTE/volume controls.
- `RadioPage.tsx` derives `offline = state != null && (state.source === "none"
  || !state.track)`; while offline it renders the new `OfflineNotice` and hides
  the now-playing block, VU meter, genre row, and controls. The header and the
  hidden player stay mounted, so playback resumes automatically when a track
  becomes available. Initial load (`state == null`) is unchanged.
- Files touched:
  - `frontend/src/pages/RadioPage.tsx`
  - `frontend/src/components/OfflineNotice.tsx` (new)
  - `frontend/src/styles/vintage.css`
  - `frontend/src/pages/RadioPage.dom.test.tsx` (test)
  - `docs/changelog.md` (docs)
- **Container restart required:** `docker compose up -d --build frontend`, then
  hard-refresh the browser (Ctrl+Shift+R).
- Verification:
  - `npm test` 106 passed (off-air RadioPage test now asserts the offline
    screen renders and MUTE/volume controls are absent).
  - `npm run typecheck` clean.
  - `npm run build` succeeds.

## 2026-10-08 — Fix blank homepage: guard YT player calls until ready

- Fixed `TypeError: player.getCurrentTime/getPlayerState is not a function`
  thrown while the YouTube player was still initializing. The IFrame API does
  not attach `getCurrentTime`/`getPlayerState` in the constructor — they appear
  only once the player is ready. The drift-sync effect and the 1s progress
  interval called them unconditionally; the throw inside a React passive effect
  unmounted the tree, leaving the homepage blank (and spamming the interval).
- Added an `isPlayerReady` runtime guard and applied it before every player
  method call (`useYouTubePlayer.ts`): the broadcast-sync effect, the volume
  effect, and the interval now no-op until the API methods exist. The interval
  also only reads progress when a track is present.
- Hardened cleanup: `playerRef.current` is cleared before `player.destroy()`,
  which is wrapped in try/catch, so a throwing destroy can no longer leave a
  dangling ref or escape a React effect.
- Files touched:
  - `frontend/src/hooks/useYouTubePlayer.ts`
  - `frontend/src/hooks/useYouTubePlayer.dom.test.ts` (new regression test)
  - `docs/changelog.md` (docs)
- **Container restart required:** `docker compose up -d --build frontend`, then
  hard-refresh the browser (Ctrl+Shift+R).
- Verification:
  - `npm test` 106 passed (1 new: "does not call player methods before the
    player is ready", which reproduces `getPlayerState is not a function`
    before the fix).
  - `npm run typecheck` clean.

## 2026-10-07 — Security hardening: revocable sessions, real client IP, WS caps, CSP

- Follow-up to the earlier high-severity fixes, covering the medium findings.
- **Revocable sessions:** session JWTs now carry `iat` and a unique `jti`
  (`app/auth.py`). `POST /api/admin/logout` records the token's `jti` in a new
  `revoked_session` table, and `require_admin` rejects any token whose `jti` is
  revoked — so a leaked token can no longer be replayed after logout even
  though it has not expired. Expired revocation rows are pruned on each logout.
  Added model `RevokedSession` and Alembic migration `e5f6a7b8c9d0`.
- **Real client IP for rate limiting:** uvicorn is started with
  `--proxy-headers --forwarded-allow-ips="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"`
  (`backend/entrypoint.sh`). Trusting the Docker private ranges (not `"*"`)
  makes uvicorn pick the *last untrusted* `X-Forwarded-For` entry, so a
  spoofed client header cannot evade the login lockout and cannot lock the real
  admin out.
- **WebSocket caps:** `/api/ws/listeners` and `/api/ws/radio` now close new
  connections with code 1013 once `MAX_LISTENERS` (200) or `MAX_RADIO_CLIENTS`
  (500) is reached, preventing unbounded-connection memory DoS.
- **Security headers:** `Caddyfile` now adds `Content-Security-Policy` (scoped
  to self plus the YouTube IFrame API, Google Fonts and thumbnail hosts),
  `Permissions-Policy`, and extends HSTS with `includeSubDomains`; the `Server`
  header is stripped. `X-Forwarded-For` is left to Caddy's default, which was
  verified to pass only the real client IP.
- Files touched:
  - `backend/app/auth.py`, `backend/app/models.py`,
    `backend/app/routers/admin.py`, `backend/app/routers/ws.py`,
    `backend/entrypoint.sh`
  - `backend/alembic/versions/e5f6a7b8c9d0_add_revoked_session.py` (new)
  - `backend/tests/test_auth.py`, `test_admin.py`, `test_ws.py` (tests)
  - `Caddyfile`
  - `docs/changelog.md` (docs)
- **Container restart required:**
  `docker compose up -d --build backend` and
  `docker compose up -d --force-recreate caddy` (Caddyfile is bind-mounted, so
  it needs a recreate to reload). Frontend untouched.
- Verification:
  - `python -m pytest` 201 passed (5 new: unique `jti`, wrong-key decode,
    server-side logout revocation, listener/radio connection caps).
  - `alembic upgrade head` applied cleanly to a fresh SQLite DB (creates
    `revokedsession` + index).
  - `caddy validate` → "Valid configuration".
  - Live smoke test via Caddy: `login` 200, `session` 200, `logout` 200;
    response carries CSP/Permissions-Policy/HSTS headers; a spoofed
    `X-Forwarded-For: 9.9.9.9` is ignored (backend logs the real client IP).

## 2026-10-07 — Security hardening: loopback ports, login lockout, rotated secrets

- Fixed three high-severity security findings:
  1. The `backend` (`8011:8000`) and `frontend` (`8012:80`) host port mappings
     were bound to all interfaces, exposing the API over plain HTTP and
     bypassing Caddy's TLS and security headers. Both are now bound to
     loopback (`127.0.0.1:8011:8000`, `127.0.0.1:8012:80`); only Caddy
     (`8010:443`) remains publicly reachable.
  2. `POST /api/admin/login` had no brute-force protection. Added an in-memory
     per-client lockout (`app/ratelimit.py`): 5 failed attempts within 15
     minutes locks that client out (HTTP 429) until the window expires; a
     successful login clears the counter. The check runs before password
     verification, so a locked-out client cannot retry with the correct
     password.
  3. The `SECRET_KEY` (JWT/HMAC signing) and `ADMIN_PASSWORD` in
     `backend/.env` were weak, human-readable passphrases. Both were replaced
     with 32-byte and 18-byte cryptographically random values. The
     `YT_API_KEY` still needs to be rotated manually in the Google Cloud
     Console.
- Files touched:
  - `docker-compose.yml`
  - `backend/app/ratelimit.py` (new), `backend/app/routers/admin.py`
  - `backend/tests/conftest.py`, `backend/tests/test_admin.py` (tests)
  - `backend/.env` (untracked; secrets rotated)
  - `docs/changelog.md` (docs)
- **Container restart required:**
  `docker compose up -d --build backend frontend` (backend rebuild for the
  lockout code, frontend recreate for the new port binding).
- Verification: `python -m pytest` 196 passed (up from 194; two new login
  lockout tests). Frontend untouched.

## 2026-10-07 — Reorder admin schedule panel

- The admin Schedule panel now shows the "Add schedule slot" form above the
  list of existing schedule slots, matching the order requested.
- Files touched: `frontend/src/components/admin/SchedulePanel.tsx`.
- Docker: frontend-only change, rebuild `frontend`:
  `docker compose up -d --build frontend`.
- Verification: `npm run typecheck` and `npm run test` (105 tests) pass.

## 2026-10-07 — Start-only schedule slots

- Schedule slots are now a genre plus a start time (and days of the week); the
  per-slot end time is gone. At any moment the active genre is the one whose
  most recent scheduled start has passed, so a genre plays until the next
  scheduled start, wrapping across midnight and across the week. The default
  genre is used only when the schedule is empty or a scheduled genre has no
  cached tracks.
- Backend: rewrote `app/scheduler.py` to the stateless "most recent start wins"
  resolver (removing the old `matches()` overnight logic), wired
  `app/broadcast.py` to it, and dropped `end_time` from `ScheduleSlot` (model,
  Alembic migration `d4e5f6a7b8c9`, and the admin `SlotIn`/`SlotOut`/
  `SlotUpdate` schemas). Creating or editing a slot whose start collides with
  another slot on a shared day now returns HTTP 409; `start_time` is normalized
  to `HH:MM`, `days_of_week` must be non-empty, and update ignores explicit
  nulls.
- Frontend: removed the End field from the admin Schedule form, updated the
  `ScheduleSlot` type and API client, and the slot list now reads `from 16:07`.
- Files touched:
  - `backend/app/scheduler.py`, `backend/app/broadcast.py`,
    `backend/app/models.py`, `backend/app/schemas.py`,
    `backend/app/routers/admin.py`
  - `backend/alembic/versions/d4e5f6a7b8c9_drop_schedule_end_time.py`
  - `backend/tests/test_scheduler.py`, `test_admin.py`, `test_models.py`,
    `test_now.py`, `test_genres.py`, `test_migration_station_to_genre.py`,
    `conftest.py` (tests)
  - `frontend/src/types.ts`, `frontend/src/api/client.ts`,
    `frontend/src/components/admin/SchedulePanel.tsx`,
    `frontend/src/styles/vintage.css`
  - `frontend/src/pages/AdminPage.dom.test.tsx` (tests)
  - `docs/superpowers/specs/2026-10-07-schedule-start-time-only-design.md`,
    `docs/superpowers/plans/2026-10-07-schedule-start-time-only.md` (docs)
  - `docs/changelog.md` (docs)
- **Container restart required:
  `docker compose up -d --build backend frontend`**
- Verification: `python -m pytest` 194 passed; `npm test` 105 passed;
  `npm run typecheck` pass.

## 2026-10-07 — Schedule slot editor UI overhaul

- The inline "edit slot" form used to render inside a list row styled as a
  single horizontal flex line, cramming the genre select, day pills, time
  inputs, and Save/Cancel buttons into one squished row; the Add form's button
  stretched awkwardly as a grid column, and times used plain text inputs.
- The editor is now a distinct stacked card (`li.slot-editing`): "Editing"
  badge with the slot's genre name on top, then genre select, day pills, a
  side-by-side Start/End pair, and a right-aligned Save/Cancel actions row,
  with an amber border highlight while editing. The Add form mirrors the same
  layout and shares the actions row. Start/End use `type="time"` inputs,
  matching the backend's `HH:MM` format and giving native time pickers on
  mobile. Day summaries now collapse to "Every day" / "Weekdays" /
  "Weekends". Mobile: actions become full-width buttons (extended the ≤600px
  media query to the new class).
- Files touched:
  - `frontend/src/components/admin/SchedulePanel.tsx`
  - `frontend/src/styles/vintage.css`
  - `docs/superpowers/specs/2026-10-07-schedule-slot-editor-ui-design.md` (docs)
  - `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build frontend`**
- Verification: `npm test` 104/104 pass; `npm run typecheck` pass (no lint
  script configured).

## 2026-10-07 — Schedule slot list + full CRUD in admin

- The admin Schedule tab previously only offered an "Add slot" form with no way
  to see, edit, or delete existing slots. It now lists all schedule slots
  (genre, days, time range) and supports inline editing and confirmed deletion.
- Backend: added `GET /api/admin/slots` (ordered by id, denormalized
  `genre_name`), `PUT /api/admin/slots/{id}` (partial update, validates genre
  and times), and `DELETE /api/admin/slots/{id}`; `POST /api/admin/slots` now
  returns a `SlotOut`. New `SlotOut`/`SlotUpdate` schemas. No migration needed
  (the `scheduleslot` table already exists).
- Frontend: added `ScheduleSlot` type, `listSlots`/`updateSlot`/`deleteSlot`
  client methods, and rewrote `SchedulePanel.tsx` to load and render the list
  with Edit/Delete (`ConfirmDialog`), reusing the genre/playlist CRUD patterns.
- Files touched:
  - `backend/app/schemas.py`, `backend/app/routers/admin.py`
  - `backend/tests/test_admin.py` (tests)
  - `frontend/src/types.ts`, `frontend/src/api/client.ts`,
    `frontend/src/components/admin/SchedulePanel.tsx`
  - `frontend/src/pages/AdminPage.dom.test.tsx` (tests)
  - `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build backend frontend`**
- Verification: `python -m pytest -q` 185/185 pass; `npm run typecheck` pass;
  `npm test` 104/104 pass.

## 2026-10-07 — Instant manual playback on the radio page

- Starting a track from the admin Now Playing panel (Play / Next / Prev / Auto /
  queue reorder) now reaches already-connected listeners over a new
  `/api/ws/radio` WebSocket, so the radio switches immediately instead of
  waiting up to 5s for the next poll. A manually started track begins at 0:00
  for connected listeners. The 5s poll remains as a fallback, and a pushed
  frame can no longer be overwritten by a stale in-flight poll. New visitors
  still join at the live offset.
- Backend: extracted `build_now(session, ts)` from `/api/now` (`now.py`), added
  the `/api/ws/radio` endpoint plus a best-effort `notify_radio(payload)` push
  helper (`ws.py`), and wired every playback mutation (`play`, `next`, `prev`,
  `auto`, `PUT /genres/{id}/order`) to push the new snapshot (`admin.py`).
- Frontend: `useBroadcast` subscribes to `/api/ws/radio` (reconnect/backoff) and
  applies pushed frames instantly while keeping the 5s poll.
- Files touched:
  - `backend/app/routers/now.py`, `backend/app/routers/ws.py`,
    `backend/app/routers/admin.py`
  - `backend/tests/test_now.py`, `backend/tests/test_ws.py` (tests)
  - `frontend/src/hooks/useBroadcast.ts`, `frontend/src/test/setup.ts`
  - `frontend/src/hooks/useBroadcast.dom.test.ts` (tests)
  - `docs/changelog.md`,
    `docs/superpowers/specs/2026-10-07-instant-manual-play-design.md` (docs)
- **Container restart required: `docker compose up -d --build backend frontend`**
- Verification: `python -m pytest -q` 172/172 pass; `npm run typecheck` pass;
  `npm test` 101/101 pass.

## 2026-10-07 — Strip YouTube " - Topic" suffix from artist names

- Auto-generated YouTube music channels are named `<Artist> - Topic`, so the
  cached `artist` displayed "Chiqui Pineda - Topic" for every track from such a
  channel. `fetch_playlist_items` now strips a trailing ` - Topic` suffix
  (case-insensitive, with optional surrounding whitespace) from the video
  owner channel title via a new `_clean_artist` helper.
- Existing cached tracks were fixed by re-syncing all playlists in-container:
  `docker compose exec -T backend python -c '... sync_playlist ...'`
  (112/120/184 tracks). Verified 0 remaining `- Topic` artists.
- Files touched:
  - `backend/app/youtube.py`
  - `backend/tests/test_youtube.py` (tests)
  - `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build backend`**
- Verification: `python -m pytest tests/test_youtube.py -q` 34/34 pass.

## 2026-10-07 — Mobile queue scrolls the current row into view on load

- The admin Now Playing queue auto-scrolls the currently playing row to the
  top when the panel loads ("On air" row). On mobile (≤600px) this previously
  did nothing because the queue list is not the scroll container there (the
  whole page scrolls). The panel now calls `scrollIntoView` on the current row
  on mobile, once per page load; desktop behavior is unchanged.
- Files touched:
  - `frontend/src/components/admin/NowPlayingPanel.tsx`
  - `frontend/src/test/setup.ts` (jsdom `scrollIntoView` polyfill)
  - `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` (tests)
  - `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build frontend`**
  (performed; new bundle `index-rCD1SwfZ.js` served via nginx :8012 and
  Caddy :8010).
- Verification: `npm run typecheck` (pass), `npm test` 94/94 pass.

## 2026-10-07 — Mobile queue rows swap "On air" text badge for a red dot

- In the admin Now Playing queue, mobile view (≤600px) now renders only a red
  glowing dot (no text) on the current row; the "On air" text badge no longer
  exists in the DOM on mobile. Desktop keeps the text badge. Implemented with
  a new `useMediaQuery` hook instead of CSS-only hiding.
- Files touched:
  - `frontend/src/components/admin/NowPlayingPanel.tsx`
  - `frontend/src/hooks/useMediaQuery.ts` (new)
  - `frontend/src/hooks/useMediaQuery.dom.test.ts` (tests)
  - `frontend/src/test/setup.ts` (jsdom `matchMedia` stub)
  - `frontend/src/styles/vintage.css`
  - `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build frontend`**
  (performed; new bundles `index-CYCP75vN.js` / `index-D-kck6VN.css` served
  via nginx :8012 and Caddy :8010).
- Verification: `npm run typecheck` (pass), `npm test` 92/92 pass.

## 2026-10-07 — Now Playing genre select follows the live genre on refresh

- The genre `<select>` in the admin Now Playing panel now defaults to the
  currently playing genre instead of the first genre by sort order. It keeps
  tracking the live genre until the operator explicitly picks one.
- Files touched:
  - `frontend/src/components/admin/NowPlayingPanel.tsx`
  - `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` (tests)
  - `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build frontend`**
  (performed; new bundle `index-9uDmNxEK.js` served via nginx :8012).
- Verification: `npx vitest run src/components/admin/NowPlayingPanel.dom.test.tsx`
  16/16 pass, `npx tsc --noEmit` pass.

## 2026-10-07 — Replace `window.confirm` prompts with styled confirmation modal

- Confirmation dialogs (delete genre, remove playlist, interrupt playback)
  are now an in-app themed modal instead of native browser `alert()`-style
  prompts.
- Files touched:
  - `frontend/src/components/ConfirmDialog.tsx` (new)
  - `frontend/src/components/admin/GenresPanel.tsx`
  - `frontend/src/components/admin/PlaylistsPanel.tsx`
  - `frontend/src/components/admin/NowPlayingPanel.tsx`
  - `frontend/src/styles/vintage.css`
  - `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` (tests)
  - `frontend/src/pages/AdminPage.dom.test.tsx` (tests)
  - `AGENTS.md`, `docs/changelog.md` (docs)
- **Container restart required: `docker compose up -d --build frontend`**
  (performed; new bundle `index-Wi_pVHHS.js` served via Caddy :8010 and
  nginx :8012).
- Verification: `npm run typecheck` (pass), `npm test` 89/89 pass,
  `npm run build` pass.
