# Changelog

Most recent entries first. Each entry notes whether a Docker container
restart is required (see `AGENTS.md` for the restart commands).

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
