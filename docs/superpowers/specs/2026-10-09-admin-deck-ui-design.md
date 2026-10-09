# Nakout Admin — reference reskin design

Source of truth for the admin UI: `UI reference/Nakout Admin.html` (untracked, never
committed). Approach chosen: **reskin in place** — keep the existing four panel
components and their real API wiring; rebuild each panel's JSX to the reference
layouts; replace the admin CSS section with the reference's rules; add small new
components where genuinely reusable.

Same visual world as the public vinyl-deck page (dark wood + amber, Bricolage
Grotesque + DM Mono), already implemented as `:root` tokens in
`frontend/src/styles/vintage.css`.

## Decisions made with the user

- **Genre colours: yes** — a colour follows each genre across Genres cards,
  Playlists groups, and Schedule blocks. Requires a backend change (column, CRUD,
  migration, radio WS push on change).
- **Feedback model: toast, no undo** — reference-style fixed toast pill for success
  feedback; destructive actions keep the existing confirm dialogs (real deletes are
  not reversible with the current API). Errors stay as inline hints/banners.
- **Play now on genre cards: yes** — starts the genre through the existing playback
  endpoint.
- **Schedule: full visual 24h timeline** — blocks, carry-over, Now marker,
  click-to-add, click-to-edit; the plain slot list stays below.

## 1. Shell, header, tabs

`frontend/src/pages/AdminPage.tsx`:

- Drop the fixed-viewport shell (`body.admin-fixed`, `.admin-shell` 100vh); admin
  becomes a normally scrolling page like the reference (max-width 1120px shell,
  `padding-block: 24px 80px`).
- Header: `.brand` "Nakout<span>.</span>Radio <small>Admin</small>", right side
  `a.back` "← Back to radio" → `/` and the Log out button (same `api.logout()`).
  The login screen, session-restore, and skeleton phases are unchanged logically,
  restyled to the reference look.
- Tabs keep the existing ARIA `Tabs` component (`role="tablist"`, ids
  `tab-{id}`/`panel-{id}`) and gain a live count badge (`.count`, mono pill) on
  Playlists, Genres and Schedule tabs.
- **Toast**: new shared `Toast` component (`role="status"`, fixed bottom-centre,
  auto-hide ≈2.2 s). `onNotice` (success feedback) switches to the toast; errors
  remain inline `.hint.err` / banner elements inside each panel.
- Confirm dialogs keep the current `ConfirmDialog` component (restyled to the
  reference `.modal`/`.mbox` look).

## 2. Genre colours (backend)

- `genres.color`: `String(9)` hex column, nullable, migration backfills existing
  rows with unused palette colours in turn. Palette = the reference's 8 colours
  (`#f2a33a #e0654a #8fb996 #5fb3b3 #6fa3e0 #a58be0 #e58fb0 #d8c18a`).
- **Playlist `synced_at`**: add a nullable `synced_at` timestamp column to
  `playlists` (set on create + on every refresh/sync-all) so the "Synced X ago"
  chip is real data instead of a guess.
- `POST /api/studio/genres` accepts optional `color` (validated hex, server falls
  back to the first unused palette colour); `PUT /api/studio/genres/{id}` can
  update `color`. `GET /api/genres`, `/api/genres/{slug}` and all studio genre
  responses include `color`; studio playlist responses include `synced_at`.
- Changing a genre (including colour) keeps the existing radio WS push so the
  public page stays in sync.
- Slug auto-fill on the form is client-side only (server rules unchanged).
- Timeline data comes from the existing `GET /api/studio/slots` and
  `GET /api/schedule/now` — no new schedule endpoints.

## 3. Playlists tab

`frontend/src/components/admin/PlaylistsPanel.tsx`:

- Header block: "Playlists" + summary line ("6 playlists · 120 tracks across
  6 genres. Playlists are re-synced with YouTube when you refresh them.").
- Add card with segmented control: "Paste a link" / "From your channel"
  (same toggle behaviour as today's sidebar vs channel card, now one card).
  - Link mode: URL input + inline hint (invalid link / duplicate detected) +
    genre **colour chips** (`role="radiogroup"`, `.gchip`, chip fills with its
    genre colour when selected) + "Add playlist" (primary).
  - Channel mode: reference browse grid — cover-card grid with generated SVG
    covers (port the demo's `cover()` generator), item-count chip, per-card genre
    select + Add for un-added playlists, "Added to <genre>" badge for added ones;
    Change channel / Refresh list buttons keep their current logic.
- "Your playlists" heading + search input; playlists grouped by genre:
  `.group` per genre with coloured dot + name + "N playlists · M tracks" +
  per-group **Refresh all** (fan-out of the existing per-playlist refresh).
  Rows: YouTube playlist link (label or raw id), `.chip` "N tracks" + mono
  "Synced X ago" (relative time from `synced_at`), move-to-genre select, Refresh
  (spinner chip while syncing), Remove (confirm modal). New rows get the
  reference `.flash` animation after a move/add.
- Empty states: empty group → "Add one" link (pre-targets the add form at that
  genre); no genres at all → empty state with "Go to Genres" button.

## 4. Genres tab

`frontend/src/components/admin/GenresPanel.tsx`:

- New-genre form card (Section 1 fields + swatch row).
- Genre **cards** in a responsive grid (`.gcard`, coloured top edge via `--gc`):
  dot + name + `/slug`; chips "N playlists" / "M tracks"; next two schedule
  starts ("Starts 6:00 AM · Weekdays", "+N more"); warnings row with quick links:
  no playlists → "Add one" (jumps to Playlists add form pre-targeted), not
  scheduled → "Schedule it" (jumps to Schedule, opens the slot form pre-picked);
  actions: **Play now** (fetch `GET /studio/genres/{id}/tracks`, then
  `POST /studio/playback/play` with the first track's videoId, switch to Now
  Playing tab, toast "Now playing <genre>"; empty queue → inline error), Edit
  (inline editor with name/slug/colour swatches + validation), Delete (existing
  cascade confirm → `DELETE /studio/genres/{id}`).
- Flash animation on the changed card.

## 5. Schedule tab

`frontend/src/components/admin/SchedulePanel.tsx`:

- **On-air card** (`.onair`): LED + "On air: <genre> since <time>" and
  "Next: <genre> at <time> today/tomorrow/<day>" — data from
  `GET /api/schedule/now` (public endpoint, currently unused by the frontend;
  wire it up, refresh every 60 s alongside the existing slots list).
- Day segment pills Mon–Sun in Sun-first reference order (`aria-pressed`,
  red today-dot), driving the timeline, list, and add-form defaults.
- **Timeline** (new `ScheduleTimeline` component): 24h strip, coloured
  `--gc` blocks per slot sized by duration, carry-over strip labelled
  "continues" from the previous day's last slot, striped "Nothing scheduled"
  gap blocks, red Now marker + "Now" tag on today, 3-hour tick labels.
  Click a gap/carry area → open the add form at that time (rounded to 30 min);
  click a slot block → open it for edit.
- Slot form card: genre chips, day presets (Weekdays/Weekends/Every day) +
  individual day pills, start time, live sentence preview ("… will start at
  … on weekdays and play until the next slot begins."), server 409 conflict
  shown inline, Save disabled when incomplete.
- Day list below (reference rows): time range + genre + duration chip +
  repeat label, Edit/Delete, dim "continues from <day>" rows, dim
  "Nothing scheduled" rows with "Add slot".

## 6. Now Playing tab

`frontend/src/components/admin/NowPlayingPanel.tsx`:

- Keep every existing behaviour (transport, queue, drag reorder, shuffle,
  per-row play with confirm, sync-all, auto-following genre select, progress).
- Restyle to reference markup/CSS: `.nowcard` (cover left; title, artist,
  "Genre: x" + Schedule/Manual/Off-air badge right; amber progress bar across
  the bottom), remove the three decorative `.deck-knob` spans (mixer = DJ +
  VU only), syncing spinner on Sync-all, control/queue classes per reference.

## 7. Testing

- Backend: pytest coverage for colour (create/update/backfill/invalid/defaults,
  public serialization) and `synced_at` (set on create/refresh/sync-all,
  serialized in listing).
- Frontend: update existing admin tests to new selectors; new DOM tests for
  toast, genre colour swatches, Play now flow, playlist grouping/refresh-all,
  timeline (render blocks/carry/now marker, click-to-add/open-edit).
- `npm run test` / `typecheck` / `build` and backend `pytest -q` green before
  merge.

## 8. Rollout

Branch `admin-deck-ui` off `main` (post-PR-#1). Per-task implementer + code
review, changelog entries per task (most recent first). After merge:
`docker compose up -d --build backend frontend` then hard refresh.
`UI reference/` stays untracked.
