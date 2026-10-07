# Changelog

Most recent entries first. Each entry notes whether a Docker container
restart is required (see `AGENTS.md` for the restart commands).

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
