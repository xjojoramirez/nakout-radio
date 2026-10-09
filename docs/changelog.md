# Changelog

Most recent entries first. Each entry notes whether a Docker container
restart is required (see `AGENTS.md` for the restart commands).

## 2026-10-09 — admin studio Now Playing rebuilt as vinyl deck (full transport/queue intact); dead GenreDial + btn-danger hover contrast fixed

- Rebuilt the admin Now Playing panel JSX
  (`frontend/src/components/admin/NowPlayingPanel.tsx`) as a two-column
  vinyl studio: wooden `TurntableDeck` + mixer (VU meter, stationary deck
  knobs, "On the decks" genre strip) on the left; genre select, sleeve
  (cover art, genre kicker, track title/artist), progress bar with
  `formatClock(state.offset)` elapsed time and source badge, full transport
  (Prev/Next/Stop/Auto), draggable queue with Shuffle and per-row Play, and
  the interrupt-playback ConfirmDialog on the right. All logic, handlers,
  disabled conditions and state are unchanged — only markup/classes moved
  (old `.now-playing`/`.meta`/`.source` block is gone; "On air" appears only
  as the queue-badge, the sleeve uses `SOURCE_LABELS` like "Schedule").
- New `formatClock(totalSeconds)` helper appended to
  `frontend/src/utils/format.ts` (elapsed clock; `formatDuration` kept for
  queue rows).
- Admin deck CSS appended to `frontend/src/styles/vintage.css` right after
  the `#panel-now .queue-list` shell rules (`#panel-now .admin-deck` flex
  fill + `.np-col` column-flex override, 0.9fr/1.1fr grid, capped 460px
  deck, 84px admin sleeve, tightened gaps/title clamp), plus mobile
  (≤600px) additions inside the existing block (`.admin-deck` → `display:
  block`, uncapped `.deck`); queue overflow guards untouched.
- Fixed the `.btn-danger-solid:hover:not(:disabled)` hover-contrast issue
  (was darkened `#9c2d23`; now `var(--danger)` background with `#1c110a`
  text so the label stays readable on hover).
- Removed dead code `frontend/src/components/GenreDial.tsx` (own commit;
  referenced nowhere else — verified before deletion).
- Files touched: `frontend/src/components/admin/NowPlayingPanel.tsx`,
  `frontend/src/utils/format.ts`, `frontend/src/styles/vintage.css`,
  `frontend/src/components/GenreDial.tsx` (removed).
- **Container restart required (container `frontend` only):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` (129 tests in 17 files, incl. unchanged
  `NowPlayingPanel.dom.test.tsx`) + `npm run typecheck` + `npm run build`
  green; `rg "now-playing|radio-cabinet"` (non-test files) reports no
  remaining matches.

## 2026-10-09 — vinyl deck homepage rebuild (Tune in / Tune out, no skip/stop)

- Rebuilt the listener homepage (`frontend/src/pages/RadioPage.tsx`) around
  the vinyl deck: turntable + mixer with VU meter and draggable volume knob
  (knob stays interactive even when offline), brand header with on-air LED
  and live listener count, now-playing sleeve with cover art + progress bar,
  and "Today's schedule" list highlighting the current slot (wraparound
  ranges, e.g. "5 pm – 5 am").
- Listener controls are now a single Tune in / Tune out mute button
  (playback stays muted until tuned in); no Next record / Stop on the
  homepage. A Retry button appears when the player errors.
- New schedule formatting helpers (`frontend/src/utils/deck.ts`):
  `formatClock`, `hourLabel`, `slotRange`, `todayScheduleRows` — unit tested
  in `frontend/src/utils/deck.unit.test.ts` (5 tests, red → green).
- RadioPage DOM tests rewritten (7 tests, verified failing against the old
  page first): genre kicker, tune in/out toggle, volume knob slider, absence
  of skip/stop controls, schedule rendering + current-slot highlight, graceful
  fallback when the schedule request fails, offline notice with disabled tune
  control.
- Removed the obsolete `frontend/src/components/NowPlaying.tsx` (only
  RadioPage imported it) and pruned the now-unused homepage CSS from
  `frontend/src/styles/vintage.css` (`.radio-cabinet`, `.radio-header`,
  `.listeners`, `.now-playing`, `.genre-row`, `.tuned-label`, `.genre-list`,
  `.auto`, `.controls`, `.genre-error`, `.volume`) plus the matching mobile
  (≤600px / ≤380px) rules; mobile homepage rules now target `.radio-page`,
  `.brand`, `.tune-btn`, `.sleeve`, `.np-cover`, `.np-title`. Admin still
  references `.now-playing` until its rebuild lands next.
- Files touched: `frontend/src/pages/RadioPage.tsx` (+ rewritten
  `RadioPage.dom.test.tsx`), `frontend/src/utils/deck.ts` (+ new
  `deck.unit.test.ts`), `frontend/src/styles/vintage.css`,
  `frontend/src/components/NowPlaying.tsx` (removed).
- **Container restart required (container `frontend` only):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` (129 tests in 17 files) + `npm run typecheck`
  + `npm run build` green.

## 2026-10-09 — vinyl deck turntable + volume knob components (deck CSS, TDD)

- Added the reusable vinyl-deck components for the upcoming homepage and
  admin Now Playing panels:
  - `TurntableDeck({ playing, artUrl })`: wooden deck shell with spinning
    record (rAF spin loop, 33⅓ RPM target with spin-up/down inertia, honors
    `prefers-reduced-motion`), cover art on the record label, tonearm that
    swings when playing, 33/45 RPM markers
    (`frontend/src/components/deck/TurntableDeck.tsx`).
  - `VolumeKnob({ value, onChange, label, disabled })`: accessible
    `role="slider"` knob — arrow keys (±2), shift (±10), PageUp/PageDown,
    Home/End, vertical pointer drag with pointer capture, 0-100 clamping,
    `--r` rotation CSS variable
    (`frontend/src/components/deck/VolumeKnob.tsx`).
- Strict TDD: 6 `VolumeKnob` + 2 `TurntableDeck` DOM tests, verified red
  (module missing / drag coordinates lost) before green
  (`frontend/src/components/deck/*.dom.test.tsx`).
- Added the "Vinyl deck" CSS section (deck/platter/record/tonearm, RPM
  badges, mixer row, knob, now-playing sleeve/bar/times/tune button,
  schedule list, responsive + reduced-motion blocks) ahead of the
  mobile-width blocks in `frontend/src/styles/vintage.css`; the
  pre-existing `.vu-meter` rules are only overridden via
  `.mixer .vu-meter { height: 44px; }`. Review follow-up: the section was
  moved from EOF to sit just before the Mobile ≤600px block
  (`style: move vinyl deck section ahead of the mobile blocks`), and the
  knob gained a `pointerCancel` handler + 7th test clearing drag state
  mid-drag (`fix: clear knob drag state on pointer cancel`).
- Test-env fix (deviation note): jsdom 25 lacks a `PointerEvent`
  constructor, so RTL `fireEvent.pointer*` dropped `clientY`/`pointerId`
  and the knob drag test got `NaN`. Added a minimal `PointerEvent`
  polyfill (MouseEvent-based) to `frontend/src/test/setup.ts`, following
  the existing `matchMedia`/`scrollIntoView` polyfill style there; the
  existing `jest` shim and other shims are untouched.
- Files touched: `frontend/src/styles/vintage.css`,
  `frontend/src/components/deck/TurntableDeck.tsx`,
  `frontend/src/components/deck/TurntableDeck.dom.test.tsx`,
  `frontend/src/components/deck/VolumeKnob.tsx`,
  `frontend/src/components/deck/VolumeKnob.dom.test.tsx`,
  `frontend/src/test/setup.ts`.
- **Container restart required (container `frontend` only):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` (121 tests in 16 files, incl. the 9 new
  deck tests) + `npm run build` + `npm run typecheck` green.

## 2026-10-09 — vinyl deck dark theme takeover (tokens + fonts) across site incl. admin

- Replaced the Google Fonts load (Bebas Neue + Inter) with Bricolage
  Grotesque (variable display/body face) + DM Mono (`frontend/index.html`;
  preconnect links unchanged).
- Took over the token palette in `:root` with the vinyl-deck dark theme
  (dark wood/cream/amber tokens, new `--font-mono`, `--vinyl`, `--led`,
  `color-scheme: dark`), and retuned headings + selection to the new
  display face.
- Dark-surface sweep across shared controls and admin surfaces: buttons
  (primary text, secondary, danger hover), inputs, admin card, banners
  untouched surfaces via tokens, progress track, skeletons, admin tabs,
  confirmation modal, lists, badges, queue rows, back link, channel
  cards, slot editor, scrollbars
  (`frontend/src/styles/vintage.css`).
- Files touched: `frontend/index.html`,
  `frontend/src/styles/vintage.css`. Review follow-up: the same takeover
  also fixed dark-theme contrast on `.admin .days button.active` and
  `.btn-danger-solid` (dark `#1c110a` text on amber/danger fills).
- **Container restart required (container `frontend` only):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` + `npm run build` green (112 tests passed
  in 14 files; vite build succeeded).

## 2026-10-09 — frontend schedule/today types + useTodaySchedule hook (5-min refresh)

- Added the frontend fetch layer for the listener-homepage schedule deck
  (rendering lands in a later task):
  - `SlotToday` / `ScheduleToday` types appended after `ScheduleSlot`
    (`frontend/src/types.ts`).
  - `api.scheduleToday()` calling `GET /api/schedule/today`
    (`frontend/src/api/client.ts`).
  - `useTodaySchedule()` hook: fetch on mount, then a 5-minute
    `REFRESH_MS` interval; keeps the last good schedule when a refresh
    fails, cancelled flag on unmount (same pattern as `useBroadcast`)
    (`frontend/src/hooks/useTodaySchedule.ts`).
- Test infra: aliased `globalThis.jest = vi` in the Vitest setup so
  @testing-library's `waitFor` can advance Vitest's fake timers (`waitFor`
  otherwise hangs forever with fake timers, since RTL gates its timer
  advance on a global `jest`) (`frontend/src/test/setup.ts`).
- Files touched: `frontend/src/types.ts`, `frontend/src/api/client.ts`,
  `frontend/src/hooks/useTodaySchedule.ts`,
  `frontend/src/hooks/useTodaySchedule.dom.test.ts`,
  `frontend/src/test/setup.ts`, `docs/changelog.md` (this entry).
- **Container restart required (frontend changed):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` green — 112 passed, including 3 new
  `useTodaySchedule` hook tests; `npm run typecheck` clean.

## 2026-10-09 — Public `GET /api/schedule/today` endpoint

- Added a public, read-only schedule listing for the listener homepage deck:
  today's slots (weekday filter from `GENRE_TZ`, Asia/Manila) sorted by start
  time, plus `current_id` — the latest slot that already started today, or
  `null` before the first start (unchanged behavior: an overnight slot from
  yesterday still governs `/api/schedule/now` but is not part of today's
  list).
  - New response models `SlotTodayOut` / `ScheduleTodayOut`
    (`backend/app/schemas.py`).
  - New route `schedule_today` appended after `/now`
    (`backend/app/routers/schedule.py`).
  - Tests: fixture client override pattern from `test_admin.py`; endpoint
    time is monkeypatched to a frozen Monday 09:30 / 04:59 Manila so the
    suite is deterministic any day it runs
    (`backend/tests/test_schedule_today.py`, 4 tests).
- Files touched:
  - `backend/app/schemas.py`, `backend/app/routers/schedule.py`,
    `backend/tests/test_schedule_today.py` (commit `d4f50f7`)
  - `docs/changelog.md` (this entry)
- **Container restart required (backend changed):**
  `docker compose up -d --build backend`
- Verification: `python -m pytest tests/test_schedule_today.py -q` 4 passed;
  full suite `python -m pytest -q` 209 passed.

## 2026-10-09 — Renamed admin routes to `/studio`

- Renamed the admin surface away from the common `/admin` path to reduce
  scanner/brute-force noise (obscurity only; auth still does the real work).
  - UI route: `/admin` → `/studio` (`frontend/src/App.tsx`).
  - API prefix: `/api/admin/*` → `/api/studio/*`
    (`backend/app/routers/admin.py`). Router module, `require_admin`
    dependency, auth subject and config field names are unchanged.
  - `robots.txt` `Disallow` updated to `/studio` (`frontend/vite.config.ts`).
- Files touched:
  - `frontend/src/App.tsx`, `frontend/src/api/client.ts`,
    `frontend/src/api/client.test.ts`, `frontend/vite.config.ts`
  - `backend/app/routers/admin.py`, `backend/tests/test_admin.py`,
    `backend/tests/test_ws.py`
  - `README.md` (docs), `docs/changelog.md` (docs)
- **Container restart required (frontend + backend changed):**
  `docker compose up -d --build backend frontend`, then hard-refresh the
  browser (Ctrl+Shift+R).
- Verification: `pytest` 205 passed; `npm test` 109 passed;
  `npm run typecheck` clean.

## 2026-10-08 — Favicon and logo set

- Added a hand-authored vintage-radio logo in the site palette, at two detail
  levels: a simplified `favicon.svg` (plus 16/32/48px PNG fallbacks and a
  180px apple-touch icon) and a detailed `logo.svg`/`logo-512.png` for
  standalone reuse. PNGs are generated from the SVG sources by
  `npm run render:icons` (`frontend/scripts/render-icons.mjs`,
  `@resvg/resvg-js` devDependency).
- `index.html` now links the SVG + PNG favicons and apple-touch icon; the
  `seo` build plugin injects absolute `og:image`/`twitter:image` tags and a
  JSON-LD `logo` property pointing at `<VITE_SITE_URL>/logo-512.png`.
- Files touched:
  - `frontend/public/favicon.svg`, `frontend/public/logo.svg` (new)
  - `frontend/public/favicon-16.png`, `-32.png`, `-48.png`,
    `apple-touch-icon.png`, `logo-512.png` (new, generated)
  - `frontend/scripts/render-icons.mjs` (new)
  - `frontend/package.json`, `frontend/package-lock.json`
  - `frontend/index.html`
  - `frontend/vite.config.ts`
  - `docs/superpowers/specs/2026-10-08-favicon-logo-design.md` (docs)
  - `docs/changelog.md` (docs)
- **Container restart required (frontend changed):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run typecheck` and `npm run build` clean; rendered PNG
  dimensions confirmed (16/32/48, 180, 512); icon links and og:image tags
  present in `dist/index.html`.

## 2026-10-08 — Icon-only mute/unmute button

- Replaced the text mute control (`UNMUTE`/`MUTE`) with a compact 44x44px
  circular icon button so it no longer overlaps the volume slider on mobile.
  The inline SVG icon reflects state (slashed speaker while muted, waves
  while audible); `aria-label`/`title` reflect the action ("Unmute"/"Mute").
  New `.mute-btn` styles in `vintage.css`; `min-width: 44px` overrides the
  mobile `min-width: 88px` on `.controls button`.
- Files touched:
  - `frontend/src/pages/RadioPage.tsx`
  - `frontend/src/pages/RadioPage.dom.test.tsx`
  - `frontend/src/styles/vintage.css`
  - `docs/changelog.md` (docs)
- **Container restart required (frontend source changed):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` all passed; `npm run typecheck` clean.

## 2026-10-08 — Basic SEO: meta/Open Graph, robots.txt, sitemap.xml, JSON-LD

- Added discoverability metadata to the frontend. `index.html` now carries a
  descriptive `<title>`, `<meta name="description">`, `<meta name="robots">`,
  and Open Graph / Twitter card tags (title, description, type, site name).
- Added `frontend/vite.config.ts` `seo` plugin: at build time it injects
  `<link rel="canonical">`, `<meta property="og:url">`, and a `RadioStation`
  JSON-LD block into `dist/index.html`, and emits `robots.txt` (allows `/`,
  disallows `/admin`, points at the sitemap) and `sitemap.xml` (single homepage
  URL). All URLs derive from `VITE_SITE_URL`, defaulting to `http://localhost`.
- Wired the site URL through the build: `frontend/Dockerfile` takes
  `ARG VITE_SITE_URL` (default `http://localhost`) and `docker-compose.yml`
  passes `VITE_SITE_URL: https://${DOMAIN}` for the `frontend` build, so
  production canonical/sitemap URLs use the real domain.
- Files touched:
  - `frontend/index.html`
  - `frontend/vite.config.ts`
  - `frontend/Dockerfile`
  - `docker-compose.yml`
  - `docs/changelog.md` (docs)
- **Container restart required (frontend source + build args changed):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification:
  - `npm run typecheck` clean; `npm test` 109 passed.
  - `VITE_SITE_URL=https://radio.example.com npm run build` emits
    `dist/robots.txt` and `dist/sitemap.xml` and injects
    `<link rel="canonical" href="https://radio.example.com/">`,
    `og:url`, and the `RadioStation` JSON-LD.
  - Build without the env var falls back to `http://localhost` (no literal
    placeholder left in the output).

## 2026-10-08 — Harden containers and cap request size

- Added a shared `x-hardening` anchor applied to every service:
  `security_opt: [no-new-privileges:true]` and `pids_limit: 256`. This prevents
  privilege escalation via setuid binaries and bounds the process count per
  container.
- Added per-service resource limits so a runaway process or connection flood
  cannot exhaust the host: `caddy` 256m / 0.5 CPU, `backend` 512m / 1.0 CPU,
  `frontend` 256m / 0.5 CPU.
- Added a `request_body { max_size 10MB }` directive to the `Caddyfile` to bound
  request bodies at the edge.
- Files touched:
  - `docker-compose.yml`
  - `Caddyfile`
  - `docs/changelog.md` (docs)
- **Container restart required (compose + proxy config changed):**
  `docker compose up -d --build` (recreates all services with the new options).
- Verification:
  - `docker compose config` parses without error.
  - After `up -d`, `docker compose ps` shows all services healthy and
    `docker inspect` reports the new `HostConfig` limits
    (`Memory`, `NanoCpus`, `PidsLimit`, `SecurityOpt`).
  - `curl -sS https://<domain>/api/health` still returns `{"status":"ok"}`.

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
