# Changelog

Most recent entries first. Each entry notes whether a Docker container
restart is required (see `AGENTS.md` for the restart commands).

## 2026-10-10 — studio layout: constant page width across tabs, schedule panel no longer overflows

- `frontend/src/styles/vintage.css`:
  - `body:has(.admin-page) { justify-items: stretch }` — `body` is a
    `place-items: center` grid, which made `#root` shrink-to-fit the
    active tab's content, so `.admin-page`'s
    `min(1120px, calc(100% - 32px))` resolved against a different parent
    width on every tab (measured 1120 / 696 / 557 / 676 px on
    Now / Playlists / Genres / Schedule). Stretching `#root` gives the
    page column one definite width on all tabs; the login box
    (no `.admin-page`) keeps its old centered fit.
  - `html { scrollbar-gutter: stable }` — stops the ~15 px column jump
    when tabs toggle the vertical scrollbar.
  - `.admin-panel { min-width: 0 }` — the schedule panel (grid item)
    couldn't shrink below the timeline's `min-width: 640px` plus card
    padding, so it poked past the page's rounded edge at narrow widths;
    now the timeline scrolls inside its card instead
    (`.tlscroll` handles it).
- Verified with headless-Edge probes against the running container:
  page width 1120 px on all four tabs at 1440 viewport / 753 px at
  800, zero elements poking past the page edge, no horizontal page
  scroll, login page and public homepage unchanged.
- **Container restart required (frontend):**
  `docker compose up -d --build frontend`, then hard-refresh the
  browser (Ctrl+Shift+R).
- Verification: frontend 231 tests / 28 files, `npm run typecheck` +
  `npm run build` clean (CSS-only change).

## 2026-10-09 — admin-deck-ui branch complete — admin reskinned to the Nakout Admin reference: genre colours, grouped playlists, visual schedule timeline, reference nowcard

- Admin studio (`/studio`) now matches `UI reference/Nakout Admin.html`
  (untracked reference; same vinyl-deck world as the homepage):
  - **Backend**: `Genre.color` (hex accent colour, palette backfill
    migration `a1b2c3d4e5f6`; colour CRUD on studio endpoints; colour
    serialized on public genre/now/schedule responses; radio WS push on
    change) and `Playlist.synced_at` (migration `b2c3d4e5f6a7`, set on
    every sync, backfilled from track cache) plus a new
    `PUT /api/studio/playlists/{id}` genre-move endpoint.
  - **Shell**: brand header ("Nakout.Radio Admin" + back + logout), tab
    pills with live counts (playlists/genres/slots), natural page scroll,
    toast feedback (role="status", 2.2 s, re-arms on repeats) replacing
    success banners; errors stay inline; confirm dialogs unchanged.
  - **Playlists**: summary line, add card with "Paste a link / From your
    channel" segments, colour-chip genre picker, per-genre groups with
    refresh-all, per-row "Synced X ago", YouTube links, move select
    (flash), channel browse as cover-card grid (generative cover
    fallback).
  - **Genres**: colour swatches, cards with colour top edge, stats chips,
    "Add one" / "Schedule it" quick links, "Play now" (starts the genre's
    first track), inline edit with colour, cascade delete confirm.
  - **Schedule**: on-air card (genre since / next slot from
    `GET /api/schedule/now` — newly consumed), Sun-first day pills with
    today dot, visual 24h timeline (coloured blocks, carry-over,
    "Nothing scheduled" gaps, Now marker, click-empty-to-add,
    click-block-to-edit), slot form with presets and live sentence
    preview, 409 conflicts inline, day list rows.
  - **Now Playing**: reference nowcard (cover + title/artist/meta +
    progress bar, a11y preserved), decorative knobs removed, sync-all
    spinner.
- Deliberate cuts vs the reference (no undo on destructive actions —
  confirm dialogs instead; genre-card "N playlists" and "Starts …" chips
  — data not exposed by the API; browser-local schedule hints carry a
  "Times are shown in your local time zone." note).
- **Container restart required (backend + frontend):**
  `docker compose up -d --build backend frontend`, then hard-refresh
  the browser (Ctrl+Shift+R).
- Verification: backend `pytest -q` 221 passed; frontend 231 tests /
  28 files, `npm run typecheck` + `npm run build` clean.

## 2026-10-09 — task 9: now playing panel polish to reference (nowcard, mixer, sync spinner)

- `frontend/src/components/admin/NowPlayingPanel.tsx`: the on-air card is
  rebuilt as the reference `.nowcard` (`UI reference/Nakout Admin.html`
  238-286) — 96px `.cover` (background-image from the live
  `thumbnail_url`, falling back to `cssCover(track.title)`) beside info
  (`h3.np-title`, `.np-artist`, `.meta` row with `Genre: X` `.mono` + the
  unchanged `SOURCE_LABELS` `.badge source-*`); the `.np-bar`
  progressbar spans the card grid below with its exact a11y attributes
  preserved (`role="progressbar"` `aria-label="Playback position"`
  `aria-valuenow`); the offset clock stays in `.np-times` (last grid row).
  The three decorative `.deck-knob` spans were removed from the admin
  mixer (reference mixer is DJ + VU only; `.deck-knob` CSS kept for the
  public page / interactive knob). Sync-all shows a `.chip` with a
  `.spin` icon and is disabled while the request is pending (local
  `syncingAll`); notice/error handling unchanged.
- `frontend/src/styles/vintage.css`: added `#panel-now`-scoped nowcard
  rules (96px cover column, nowcard title sizing, `.meta` flex row,
  `.np-bar`/`.np-times` spanning `grid-column: 1 / -1`); removed the dead
  `#panel-now .admin-sleeve` rule. Public `.np-*`, `.sleeve`, `.np-cover`
  and `.deck-knob` shared rules untouched.
- `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`: added
  nowcard layout + no-decorative-knob + progressbar-a11y test, sync-all
  spinner pending/resolved test, cover fallback test (empty thumbnail →
  `cssCover` style) and thumbnail-URL cover test; `cssCover` is mocked
  (jsdom rejects the real SVG data URI's unencoded parens — same pattern
  as `PlaylistsPanel.dom.test.tsx`).
- Frontend source only; rebuild `frontend` to ship:
  `docker compose up -d --build frontend` (hard-refresh after).
- Verification: `npm run test` 231 passed (28 files), `npm run typecheck`
  clean, `npm run build` ok.

## 2026-10-09 — schedule panel fixes: tz note, strip-click guard, form a11y, stale error clearing

- `frontend/src/components/admin/SchedulePanel.tsx`: browser-timezone note
  in the `.sub` intro line wrapped in `.mono`; form day toggles wrapped in
  `role="group"` `aria-label="Repeat on"` (visual label kept); sentence
  falls back to "Pick a genre and a start time." when no days are
  selected; inline conflict error now also clears on genre-chip and
  day-pill/preset changes (was only time-change/reopen/submit).
- `frontend/src/components/admin/ScheduleTimeline.tsx`: strip clicks are
  ignored when the strip rect width is 0 (guards Infinity minute math).
- Frontend source only; no Docker restart required (rebuild `frontend`
  to ship: `docker compose up -d --build frontend`).
- Verification: `npm run test` 227 passed (28 files), `npm run typecheck`
  clean, `npm run build` ok.

## 2026-10-09 — task 8: admin schedule timeline, on-air card, day pills, sentence form

- `frontend/src/components/admin/ScheduleTimeline.tsx` (new): the 24h
  timeline strip — segments mirror the reference `buildSegs`: a carry-over
  block into `[0, firstStart)` labelled "continues" with the previous
  day's (Mon=0 indexing, previous six days only) last slot and its
  `--gc`, a `.blk.none` "Nothing scheduled" head gap when no previous
  slot exists, and one absolutely-positioned slot `<button>` per slot
  (left/width in % of 1440 min, `--gc` from the genre colour, 12h start
  label). Clicking a slot opens it for edit; clicking the strip (bubbling
  from the carry div, passing through the `pointer-events: none` gap
  divs) opens the add form at the clicked minute (30-min grid, clamped
  0..1410). `.nowl` "Now" marker only when the selected day is today and
  `nowMinutes` is provided. Ticks every 3 h labelled "12 AM … 12 PM …
  12 AM" (no "Midnight"); `.tl` carries
  `aria-label="Timeline for <full weekday>"`; `tlscroll/tlinner` keep the
  640 px min-width horizontal scroll.
- `frontend/src/components/admin/SchedulePanel.tsx`: rebuilt to the
  reference column — `h2.sec` "Schedule" + `.sub` line with the local
  timezone; `.card.onair` fed by `api.scheduleNow()` (fetched on mount,
  on slots change, and polled every 60 s via a cleared-on-unmount
  interval): live state shows `.led.live`, the genre dot + "On air:" +
  `since <time>[ <weekday>]` and `Next: <genre> at <time>
  today|tomorrow|<weekday>` computed from the slots and the local clock,
  null-genre shows "Nothing scheduled yet / Add a slot to start the
  automatic schedule."; `.head` pairs the Sun-first `.dayseg` day pills
  (`aria-pressed`, `.pill`, red `.tdot` "Today" dot inside today's pill,
  selecting a pill re-scopes an open ADD form's days to that day) with a
  "+ Add slot" button that toggles to "Close" while the fresh-add form is
  open; the sentence form `.card.sform` (amber border) has genre chips
  (`GenreChipRadio`), "Weekdays/Weekends/Every day" `.presets` plus
  individual `.pill` day toggles, a ≤220 px "Start time" time input, the
  `data-testid="sentence"` preview ("<Genre> will start at <12h time> on
  <day label> and play until the next slot begins."), inline `.hint.err`
  for API conflicts (409s no longer go to the global error toast), and
  Cancel + "Add slot"/"Save slot" actions (save gated on genre + days +
  time); fresh adds prefill the start at the first free 30-min boundary
  from 06:00 (`freeStart`) or the clicked minute; day list rows `.srow`
  (+ `.dim`) per segment with the "6:00 AM to 9:30 AM"-style range,
  genre, `fmtMin` duration chip, `formatDays` repeat label, Edit/Delete
  (delete keeps the ConfirmDialog), "… continues from <weekday>" carry
  rows, "Nothing scheduled" gap rows whose "Add slot" opens the form at
  that minute, and an "Add the first slot" empty state opening at 06:00;
  `initialGenre` is consumed once on mount behind a ref guard (preselects
  the chip for fresh adds, fires `onIntentConsumed` once); the
  `onCountChange` tab-badge contract is kept.
- `frontend/src/components/admin/ScheduleTimeline.dom.test.tsx` (new,
  8 tests) and `frontend/src/components/admin/SchedulePanel.dom.test.tsx`
  (new, 19 tests): colours/labels/positioning, carry + gap segments,
  strip-click rounding with a mocked `getBoundingClientRect`, now-marker
  presence, tick labels, Sun-first pills + today dot, pill swapping,
  prefilled edit form, presets/sentence/save gating, create/update
  payloads, inline 409, confirm-dialog delete, day-list rows, intent
  consumption, count + on-air refresh.
- `frontend/src/pages/AdminPage.dom.test.tsx`: the four schedule-slot
  tests updated to the new markup (chip radiogroup, "+ Add slot", inline
  `.hint.err` conflict assertion, day-list rows instead of the old
  `<li>` list) and `scheduleNow` added to the mocked API.
- `frontend/src/styles/vintage.css`: added the schedule reference
  families (`.admin .onair` scoped so the public deck header keeps its
  mono `.onair`, `.led.live`, `.lab`, `.tlscroll/.tlinner/.tl/.blk`
  (`.bn/.bt/.carry/.none`)/`.nowl/.ticks` (`.f/.l`), `.sform`, `.dayrow`,
  `.pill` (+ `aria-pressed`, `.tdot`), `.presets`, `.sentence`, `.fa`,
  `.sform .two`, `.daylist`, `.srow` (+ `.dim/.sm/.tr/.sa`)); removed the
  now-unreferenced old schedule-list rules (`.days`, `.time-pair`,
  `.slot-form-actions`, `.genre-admin-list` + `.slot-editing`,
  `.slot-edit-head`, `.edit-badge`, `.st-name/.st-slug`, `.row-actions`,
  `.count-pill`) and their mobile/reduced-motion references, with `.pill`
  inheriting the 44 px touch target.
- `frontend/src/types.ts`: `CurrentGenre` now carries `offset_seconds`
  and `server_time` (matches `CurrentGenreOut`).
- `frontend/src/components/admin/GenreSelect.tsx`: deleted — its only
  consumer (the old schedule form) was replaced by the chip radio.
- Frontend-only; restart required: `docker compose up -d --build frontend`.
- Verified: `npm run test` 222 pass (28 files), `npm run typecheck` clean,
  `npm run build` ok.

## 2026-10-09 — fix: playlist thumb fit, dead media query, move-error test

- `frontend/src/styles/vintage.css`: `.pcard .pc img` now uses
  `object-fit: cover` (was `fill`) so 4:3 YouTube thumbs aren't stretched
  in the 16:9 card; removed the dead `@media (max-width: 920px) .browse`
  duplicate (the later ≤920px `repeat(2, 1fr)` block wins).
- `frontend/src/components/admin/PlaylistsPanel.dom.test.tsx`: added a
  move-error test — rejected `updatePlaylist` calls `onError` and still
  refetches via `listPlaylists`.
- Frontend-only; restart required: `docker compose up -d --build frontend`.
- Verified: `npm run test` 195 pass, `npm run typecheck` clean,
  `npm run build` ok.

## 2026-10-09 — task 7: playlists panel reskin — genre groups, chips, refresh-all, channel grid, move endpoint

- `frontend/src/components/admin/PlaylistsPanel.tsx`: rebuilt from the
  two-column layout to a single reference column — `h2.sec` "Playlists" +
  `.sub` summary (`N playlist(s) · M tracks across G genres.` with the
  computed totals); the add form became `form.card`/`.addlink` with a
  `.seg` two-toggle ("Paste a link" / "From your channel",
  `aria-pressed`), the link input is labelled "YouTube playlist link"
  (`inputmode=url`) with a live `.hint` (`.ok` "Playlist ID found: …" /
  `.err` for an invalid link *and* for duplicates — the duplicate hint
  reads "This playlist is already added under <genre>." and shows
  regardless of the selected genre); genre choice now uses
  `<GenreChipRadio>` (radiogroup "Genre") and Add playlist stays
  disabled until genre + a valid, non-duplicate link are in play;
  channel mode keeps the existing setup/save/browse logic but re-styles
  the saved list as a `.browse` grid of `.pcard`s (`.pc` 16:9 thumb with
  the real `<img>` when present, `cssCover(title)` background fallback
  when `thumbnail_url` is empty; header shows channel name + Change /
  "Refresh list", `already_added` cards render the `.added-badge`
  "Added to <genre>"); "Your playlists" `.head` pairs the `.ttl` with a
  `.filter-input` search (`input[type=search]`, `aria-label "Search
  playlists"`, kept contract) that filters rows across genre groups;
  groups are `section.group[style=--gc]` (dot, name, `.mono` count
  "N playlist(s) · M tracks", per-group "Refresh all" when N>0 firing
  all of the group's `refreshPlaylist` calls via `Promise.allSettled`
  then one combined notice — "Refreshing <genre>..." while pending;
  rows get a `.chip`/"Syncing" spinner while their refresh is in
  flight (`syncingIds`), and per-group busy state disables the
  buttons); rows are `.prow` (labelled `.pid` link or raw-id `.pid
  .idonly`, chips "N tracks" + mono "Synced <timeAgo>", Refresh /
  Remove) with a NEW genre move `<select aria-label="Genre for
  <playlist>">` that calls the new `api.updatePlaylist` and flashes the
  row (`.prow .flash` 1.4 s, same ref-guarded timer as the genre panel);
  flash also lands on newly added rows; empty states: a genre group
  with nothing shows `.gempty` "No playlists yet. Add one" (the link
  preselects that genre and flips back to link mode), a search with no
  matches shows `.empty` `No playlists match "<q>".`, and no genres at
  all shows `.empty` "Create a genre first, then add playlists to it."
  with a "Go to Genres" button via the new optional `onJump` prop
  (same `(tab, intent?)` signature as GenresPanel); `initialGenre` from
  the Genres quick link is now consumed once on mount via a `useRef`
  guard (StrictMode-safe): sets link mode + preselects the chip, then
  calls `onIntentConsumed` exactly once; the `onCountChange` contract
  (tab badge) is kept after loads/mutations.
- `frontend/src/api/client.ts`: added `updatePlaylist(id, { genre_id })`
  (`PUT /studio/playlists/{id}`).
- `backend/app/routers/admin.py`: added the `PlaylistUpdate` model and
  `PUT /studio/playlists/{playlist_id}` (requires admin; 404 for unknown
  playlist or genre; reassigns `genre_id`, commits, then pushes the
  refreshed `now` payload to the radio with the same build/commit order
  as `update_genre`).
- `backend/tests/test_admin.py`: move tests — happy-path genre update
  (200/`updated` + listed payload), unknown-genre/unknown-playlist 404,
  and an unauthenticated 401 (`3` new tests; `notify_radio` uses the
  monkeypatch-faked `_build_fetch` here only to keep the created
  playlist's sync offline).
- `frontend/src/styles/vintage.css`: added the playlists reference
  families (`.head`/`.sp`, `.filter-input`, `.addlink`, `.seg` with
  `aria-pressed` highlight + `font-family` inherit per the gchip fix
  pattern, `.addchannel`, `.browse`, `.pcard`/`.pc img` full-bleed
  16:9, `.groups`/`.group`/`.ghead`/`.prow`/`.prow .act select` pill,
  `a.pid`(+`.idonly`)/`.gempty`, `.empty` upgraded to the dashed-border
  grid style); removed the dead layout families it replaces —
  `.playlists-layout`/`.playlists-main`/`.playlists-side`/
  `.side-block`, the old `.added-playlists` row list (and its
  responsive rules), and the old channel chrome (`.channel-block`,
  `.channel-head`/`.channel-name`, `.channel-scroll`, `.channel-grid`,
  `.channel-card*`) — `.channel-setup`, `.count-pill` (Schedule),
  `.row-actions`, `.added-badge`, `.panel-head` (Now Playing) kept
  because they are still referenced; responsive tweaks for `.browse`
  at ≤920px and ≤380px and for `.prow` rows at ≤920px. Grep across
  `frontend/src` confirms no stale class references either way.
- `frontend/src/pages/AdminPage.tsx`: passes `onJump={jump}` to
  PlaylistsPanel so the "Go to Genres" button works.
- `frontend/src/pages/AdminPage.dom.test.tsx`: quick-link assertion now
  targets the new "Your playlists" heading; the add-by-URL test uses
  the chip radiogroup + "YouTube playlist link" label; the two channel
  tests click the "From your channel" segment first, "(5 tracks)" chip
  text, `synced_at` fixture completeness. No other flows changed.
- `frontend/src/components/admin/PlaylistsPanel.dom.test.tsx` (new):
  21 contract tests covering the summary line, genre groups + per-group
  empty/Refresh-all, row anatomy (links, chips, `timeAgo`, move select
  → `updatePlaylist` + flash, "Syncing" spinner), search filtering +
  no-match empty, segmented control, add-form hints (valid/invalid/
  duplicate), chip-driven add + notice, create/refresh error paths,
  channel save/browse/reload/add-from-browse + `cssCover` fallback,
  `initialGenre` intent consumption (once), refresh-all fan-out,
  ConfirmDialog removal, count callback and the no-genres empty state.
- Restart: backend + frontend —
  `docker compose up -d --build backend frontend` (then hard refresh).
- Verification: backend `python -m pytest -q` (221 passed), frontend
  `npm run test` (194 tests / 26 files), `npm run typecheck`,
  `npm run build` — all green.

## 2026-10-09 — task 6 follow-up: genre panel polish — flash timing, quick-link labels, default swatch

- `frontend/src/components/admin/GenresPanel.tsx`: `flash(created.id)`
  in `addGenre` now runs after `await onGenresChanged()` resolves (a
  slow refresh can no longer strand the flash before the new card
  exists); the flash timer lives in a `useRef` (mirroring `Toast.tsx`)
  that is cleared before re-arming and on unmount via an empty-deps
  `useEffect` cleanup, keeping the identity-guarded functional update;
  empty-genre quick links got descriptive accessible names
  (`aria-label="Add playlist to X"` / `aria-label="Schedule X"`); the
  add-form colour now defaults to `GENRE_PALETTE[0]` (#f2a33a brand
  amber) instead of palette[7].
- `frontend/src/components/admin/GenresPanel.dom.test.tsx`: quick-link
  clicks updated to the new role names; added a rejection-path test —
  `updateGenre` rejecting (409) toasts the error and keeps the inline
  editor open.
- `frontend/src/pages/AdminPage.dom.test.tsx`: create-genre fixture +
  assertion use the new `#f2a33a` default colour.
- Restart: frontend only — `docker compose up -d --build frontend`
  (then hard refresh).
- Verification: `npm run test` (173 tests / 25 files),
  `npm run typecheck`, `npm run build` — all green.

## 2026-10-09 — task 6: genres panel reskin — colour cards, play now, cross-tab quick links

- `frontend/src/components/admin/GenresPanel.tsx`: rebuilt from the list
  layout to the reference card grid — `.ggrid` of `article.gcard` with a
  `--gc` colour accent (inset top edge), `.gtop` (colour dot + name +
  `/.mono` slug), `.gstats` chips ("N tracks", "default" when
  `is_default`), and a `.gwarn` row on `track_count === 0`
  ("No playlists" `chip.warn` + "Add one"/"Schedule it" `.btn-link`
  quick links that call the new `onJump`). "Play now" fetches
  `api.genreTracks(id)` and posts `api.play(id, first video id)`, toasts
  "Now playing X." and jumps to the Now Playing tab; an empty queue
  errors "\"X\" has no tracks yet. Add a playlist." instead. The add
  form became `form.card.gform` ("New genre" `.ttl`, `.gf-grid`
  name/slug with a `.pre` "/" prefix, `PaletteSwatches` "Genre colour";
  slug auto-fills from the name until manually edited, submit sends the
  swatch colour as the third `createGenre` argument, button disabled
  until name+slug). Inline edit stays in the card (`.gedit`) with the
  same "Edit genre name"/"Edit genre slug"/"Default genre" labels plus
  swatches; Save sends `{ name, slug, is_default, color }`; Save is
  disabled while name/slug is blank. Added a `flashId` "gcard flash"
  animation on the just-added/just-edited genre (cleared after 1.5 s).
  Section header is `h2.sec` "Genres" + `.sub` reference copy; empty
  state is `.empty` "No genres yet. Create your first one above."
  Delete keeps the ConfirmDialog message and flow. Heading semantics:
  `h2` → `h2.sec`, add-form title is `h3.ttl`.
- `frontend/src/pages/AdminPage.tsx`: cross-tab jump plumbing —
  `playlistIntent`/`scheduleIntent` state plus a `useCallback` `jump`
  that records an optional `{ playlistsGenre?, scheduleGenre? }` intent
  and switches tabs; GenresPanel gets `onJump={jump}`;
  PlaylistsPanel/SchedulePanel receive `initialGenre={…Intent}` and
  `onIntentConsumed` (typed props only — consumed in tasks 7/8);
  logout resets both intents.
- `frontend/src/components/admin/PlaylistsPanel.tsx`,
  `frontend/src/components/admin/SchedulePanel.tsx`: typing-only
  optional props `initialGenre?: number | null` and
  `onIntentConsumed?: () => void` with doc comments; no behaviour yet.
- `frontend/src/styles/vintage.css`: added the missing admin
  primitives (`.chip`/`.chip.warn`/`.chip.ok`, `.mono`, `h2.sec`,
  `.sub`, `.ttl`, `.empty`) and the reference gcard family (`.gform`,
  `.gf-grid` 1.4fr/1fr collapsing at ≤640px, `.pre` slash prefix,
  `.ggrid` minmax(300px,1fr) collapsing at ≤400px, `.gcard` with the
  `--gc` inset top edge — background tokenised to `--cream-soft` to
  match existing cards, `.gtop`, `.gstats`, `.gwarn`, `.gact`,
  `.gedit` + its `.field-inline` checkbox row since the old
  `.genre-admin-list`-scoped rule no longer applies, `.btn-link`).
  `.genre-admin-list`/`.st-name`/`.st-slug`/`.row-actions` kept for the
  Schedule rows.
- `frontend/src/components/admin/GenresPanel.dom.test.tsx` (new):
  11 cases — card colour/slug/chips/default pill, empty-genre warning +
  quick-link intents, slug auto-fill until touched, add button
  disabled state, add with swatch colour + notice, Play now happy path
  (genreTracks → play(v1) → notice + jump) and empty-queue error path
  (no play call), edit colour change + flash class, Save disabled on
  blank name/slug with no api call, delete confirm message + cancel +
  confirm, empty state.
- `frontend/src/pages/AdminPage.dom.test.tsx`: updated the genre
  create/edit fixtures to carry `color` and the assertions to the
  new `createGenre(name, slug, color)` / `updateGenre(id, {…, color})`
  payloads; added a jump test ("Add one" switches to the Playlists
  tab).
- Restart: frontend only —
  `docker compose up -d --build frontend` (then hard refresh).
- Verification: `npm run test` (172 tests / 25 files),
  `npm run typecheck`, `npm run build` — all green.

## 2026-10-09 — task 5 follow-up: toast re-arm on repeat notices, mobile page paddings, dead rule removal

- `frontend/src/pages/AdminPage.tsx`: `notice` is now
  `{ text: string; id: number } | null` with a monotonic
  `noticeEpoch` ref; `onNotice` bumps the epoch and `<Toast>` is
  rendered with `key={notice?.id ?? 0}`, so a repeated identical
  message remounts the toast and restarts its 2.2 s auto-hide instead
  of being swallowed by the still-running timer. `onDone`/`onError`/
  logout clear to `null`. No test was added for the double-notice
  flow (fake timers vs `findByRole`-style async utils in this suite
  are flake-prone; the re-arm is a plain `key` remount verified by
  the existing 160-test suite).
- `frontend/src/styles/vintage.css`: inside the ≤600px media block the
  page wrapper keeps its own paddings via
  `.admin-page { padding: 8px 4px 40px; }` (declared after the
  `.admin` shorthands, generous bottom clears the fixed toast), and
  the ≤380px block gets `.admin-page { padding: 16px 10px 40px; }`.
- Removed the dead `.admin .notice` rule (no JSX consumer — notices
  render through `Toast` since the task 5 shell change).
- Restart: frontend only —
  `docker compose up -d --build frontend` (then hard refresh).
- Verification: `npm run test` (160 tests / 24 files),
  `npm run typecheck`, `npm run build` — all green.

## 2026-10-09 — task 5 admin shell: brand header, counted tabs, toast, scrolling page

- `frontend/src/pages/AdminPage.tsx`: ready header replaced with the
  reference brand row (`header.admin-top` › `div.brand` "Nakout.Radio
  Admin" + `.top-r` with `a.back` and the Log out button); notice banner
  swapped for `Toast`; wrappers now `.admin.admin-page` in all phases
  (checking/login/ready); dropped the `admin-fixed` body-class effect and
  the `admin-stable` class; moved `tabsDef` inside the component with
  live counts (`Playlists`/`Schedule` start `null`, `Genres` =
  `genres.length`); logout resets the counts; passes
  `onCountChange={setPlaylistCount}` / `{setSlotCount}` to the panels.
- `frontend/src/components/admin/Tabs.tsx`: `TabDef` gains
  `count?: number | null`; renders `span.count` after the label when a
  count is present.
- `frontend/src/components/admin/PlaylistsPanel.tsx` +
  `SchedulePanel.tsx`: optional `onCountChange?: (count: number) => void`
  prop; called with the resolved list length in `loadAdded` /
  `loadSlots` (destructured `loaded` value), so tab counts update on
  add/remove/delete and tab mount.
- `frontend/src/styles/vintage.css`: REMOVED `body.admin-fixed`,
  `.admin-shell`, the shell-fit `#panel-playlists`/`#panel-now`
  flex/overflow/scroll blocks, mobile neutralizers for the same,
  `.admin-stable`, `.admin-header`/`.admin-header-actions`, and kept
  only deck proportions (`#panel-now .admin-deck` trimmed to
  grid columns + padding, `#panel-now .admin-sleeve` intact).
  `.admin-tabpanel` is now `display: grid; gap: 18px; min-width: 0`.
  ADDED `.admin-page` (1120px shell, 22px grid gap, natural page
  scroll), margin resets for `.admin-tabs`/`.banner`/`.admin-panel`
  inside it, `.admin-top`, `.admin .brand small`, `.top-r`, `a.back`
  (+ hover), `.count` pill + `.admin-tabs .active .count`, flex
  alignment on `.admin-tabs button`; mobile block updated
  (`.admin-top .brand`, `.top-r` rules; login `h1` sizing kept).
  Reuses the existing public `.brand`/`.brand span` rules — no admin
  additions leak onto the public page.
- Tests: `AdminPage.dom.test.tsx` — tab-name queries moved to
  `/^Label/` regexes (counts append), playlist-sync notices asserted
  via `findByRole("status")` toast instead of the banner, added
  "renders the brand header" test and a Playlists-tab count
  assertion (21 tests). `Tabs.dom.test.tsx` — added count-pill
  test (2 tests).
- Restart: frontend only —
  `docker compose up -d --build frontend` (then hard refresh).
- Verification: `npm run test` (160 tests / 24 files, was 158),
  `npm run typecheck`, `npm run build` — all green.

## 2026-10-09 — task 4 primitives polish: gchip font inheritance, hint variants, toast cosmetics + unmount test

- `frontend/src/styles/vintage.css` (admin primitives block):
  `.gchip` now declares `font-family: var(--font-body)` +
  `font-size: 0.9rem` (buttons don't inherit fonts from this file);
  added `.hint.err` / `.hint.ok` variants after the bare `.hint` rule;
  `.toast` set to `opacity: 1` and `transform: translateX(-50%)`
  (dropped the dead 8px offset). No visual change to anything currently
  rendered — the touched selectors are not used on-screen yet.
- Added a timer-unmount test to
  `frontend/src/components/admin/Toast.dom.test.tsx`
  (`onDone` never fires after unmount; suite now 158 tests in 24 files).
- Restart: frontend only (`frontend/src/styles/**` is a served change,
  per AGENTS.md rule) — `docker compose up -d --build frontend`.
- Verification: `npm run test` (158 tests) + `npm run typecheck` +
  `npm run build` green.

## 2026-10-09 — shared admin UI primitives: Toast, PaletteSwatches, GenreChipRadio + CSS (admin reskin task 4)

- New `frontend/src/components/admin/`: `Toast.tsx` (capsule
  `role="status"` toast, 2.2 s auto-hide via `setTimeout`, renders null
  when the message is empty, timer keyed on the message only),
  `PaletteSwatches.tsx` (radiogroup of 8 `role="radio"` swatch buttons
  from `GENRE_PALETTE`, colour exposed as `--gc`), `GenreChipRadio.tsx`
  (radiogroup of genre chips with colour dot, `--gc` falling back to
  `var(--amber)` when `color` is empty; empty-genre list renders a
  `.hint` paragraph instead of the group). TDD: tests first, verified
  they failed, then implemented.
- `frontend/src/styles/vintage.css`: appended additive admin-primitive
  families (`.toast`, `.chips`/`.gchip`/`.dot`, `.swatches`/`.sw`,
  `.hint`, `.flash`, `.spin` + `@keyframes flash`/`spin`) anchored at the
  end of the admin section (after the schedule-slot rules, immediately
  before the `/* ---------- Vinyl deck ---------- */` comment) so all
  admin styles stay contiguous. Overlap audit before insertion: no
  pre-existing `.toast`, `.chips`, `.gchip`, `.swatches`, `.dot`,
  `.flash`, `.spin`, or `@keyframes spin` (keyframes in file were only
  `vu-flicker`, `skeleton-shimmer`, `modal-fade-in`, `modal-pop-in`).
  `.hint` existed only as the scoped `.admin-login .hint` (line ~554)
  with compatible colours, so the new bare `.hint` was safe to add
  unchanged (it only adds `min-height: 1.2em` where the scoped rule
  wins on colour/size/margin).
- New tests `Toast.dom.test.tsx` / `PaletteSwatches.dom.test.tsx` /
  `GenreChipRadio.dom.test.tsx` (10 tests total; task spec estimated
  ~12, spec-provided tests total 10). Deviation: `Toast` dep array is
  `[message]` with an eslint-disable comment instead of `[message,
  onDone]`, per task note (repo has no eslint setup; inline-arrow
  `onDone` at call sites would otherwise restart the timer per render).
- Files: `frontend/src/components/admin/Toast.tsx`,
  `PaletteSwatches.tsx`, `GenreChipRadio.tsx`,
  `Toast.dom.test.tsx`, `PaletteSwatches.dom.test.tsx`,
  `GenreChipRadio.dom.test.tsx`, `frontend/src/styles/vintage.css`,
  `docs/changelog.md`.
- Restart: frontend only (components unused elsewhere yet, no UI
  churn) — `docker compose up -d --build frontend`.
- Verification: `npm run test` → 24 files / 157 tests passed (147
  existing + 10 new); `npm run typecheck` → clean; `npm run build` →
  success.


## 2026-10-09 — follow-up: timeAgo offset parsing fixed + client colour-path payload tests

- `timeAgo` (`frontend/src/utils/format.ts`) appended `Z` to every
  string, so explicit-offset timestamps became `…+00:00Z` (unparseable →
  "NaNd ago"). It now parses strings ending in a `±HH:MM` offset or `Z`
  as-is and appends `Z` only to naive strings. Deviation from the
  suggested patch: the naive check also excludes `Z`-suffixed strings,
  otherwise `"…31Z"` became `"…31ZZ"` → NaN (caught by the existing
  unit test).
- Extended `frontend/src/utils/format.unit.test.ts`: `+00:00` →
  "5 min ago", `+02:00` → "2h ago" (offset honoured).
- Added payload coverage for the colour paths
  (`frontend/src/api/client.test.ts`, 15 → 18 tests): createGenre omits
  colour when unsupplied, sends `{name, slug, color}` when supplied,
  updateGenre forwards colour-only updates.
- Files: `frontend/src/utils/format.ts`,
  `frontend/src/utils/format.unit.test.ts`,
  `frontend/src/api/client.test.ts`, `docs/changelog.md`.
- Restart: frontend only (code changed) — `docker compose up -d --build
  frontend`.
- Verification: `npm run test` → 21 files / 147 tests passed (144 + 3
  client payload tests); `npm run typecheck` → clean; `npm run build` →
  success.

## 2026-10-09 — frontend data layer: colour/synced_at shapes, schedule time helpers, generated covers (admin reskin task 3)

- `Genre` gained `color: string`; `AddedPlaylist` gained
  `synced_at: string | null` (`frontend/src/types.ts`) — typed against the
  task-1/2 backend API (backend serializes `color` as `genre.color or ""`,
  `synced_at` as ISO-8601-with-`Z` or null).
- `api.createGenre` takes an optional `color` (omitted from the body when
  absent) and `api.updateGenre` accepts `color` in its updates
  (`frontend/src/api/client.ts`).
- New pure helpers in `frontend/src/utils/format.ts`:
  `minutesOf` ("06:05" → 365), `twelveHour` (minutes → "6:30 AM"/"Midnight"),
  `fmtMin` (90 → "1h 30m"), `timeAgo` (ISO string/null → "5 min ago"/"never",
  tolerant of a missing `Z`).
- New `frontend/src/utils/profile.ts`: `cssCover(seed)` renders a deterministic
  generative SVG (hash-picked palette/geometry) as a `url("data:image/svg+xml…")`
  CSS background value.
- New `frontend/src/palette.ts`: `GENRE_PALETTE` — 8 hex colours mirroring
  `backend/app/models.py` (parity re-checked in review; the frontend test is a
  sanity check, length + first colour).
- Test fixtures in `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`
  gained the now-required `Genre.color` field.
- Files: `frontend/src/types.ts`, `frontend/src/api/client.ts`,
  `frontend/src/utils/format.ts`, `frontend/src/utils/profile.ts`,
  `frontend/src/palette.ts`, `frontend/src/utils/format.unit.test.ts`,
  `frontend/src/utils/profile.unit.test.ts`,
  `frontend/src/palette.unit.test.ts`,
  `frontend/src/api/client.test.ts`,
  `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`,
  `docs/changelog.md`.
- Restart: frontend only (bundle-baked) — `docker compose up -d --build
  frontend`; note the colour/synced_at API shapes are typed but not yet
  visually consumed (that's a later reskin task).
- Verification (TDD: new tests written first, confirmed red, then green):
  `npm run test` → 21 files / 144 tests passed (previous 138 + 6 new);
  `npm run typecheck` → clean; `npm run build` → success. (File list and
  totals reflect the follow-up entry above; at this commit's time the
  suite was 144 in 21 files, with `client.test.ts` extended to 18 by the
  follow-up.)

## 2026-10-09 — backend tests: strengthened synced_at coverage (test-only)

- `backend/tests/test_admin.py` only: refresh test now nulls `synced_at`
  after create before refreshing (was un-failable); backfill migration
  fixture gained the `a1b2c3d4e5f6`-era `genre.color` column and a
  trackless playlist whose `synced_at` stays NULL after upgrade.
- Tests only — no container restart required.
- Verification: `python -m pytest tests/test_admin.py -k "synced" -q` →
  3 passed; full `python -m pytest -q` → 218 passed.

## 2026-10-09 — backend: playlist synced_at (set on sync, backfilled)

- `Playlist` gained a nullable `synced_at` datetime column
  (`backend/app/models.py`).
- `sync_playlist` (`backend/app/sync.py`) now stamps `playlist.synced_at` with
  naive UTC now just before its commit, so create, refresh, and sync-all all
  update the timestamp (all three call `sync_playlist` after the playlist row
  is committed).
- New migration
  `backend/alembic/versions/b2c3d4e5f6a7_playlist_synced_at.py`
  (revision `b2c3d4e5f6a7`, down_revision `a1b2c3d4e5f6`): batch-adds the
  nullable `synced_at` column and backfills it from `MAX(trackcache.fetched_at)`
  per playlist; playlists with no cached tracks stay NULL.
- `PlaylistOut` gained `synced_at: str | None = None`
  (`backend/app/schemas.py`); `list_added_playlists` serializes it as
  ISO-8601 with a `Z` suffix (`backend/app/routers/admin.py`).
- Files: `backend/app/models.py`, `backend/app/sync.py`,
  `backend/app/schemas.py`, `backend/app/routers/admin.py`,
  `backend/alembic/versions/b2c3d4e5f6a7_playlist_synced_at.py`,
  `backend/tests/test_admin.py`, `docs/changelog.md`.
- Restart required: backend only (model + migration + serialization changed) —
  `docker compose up -d --build backend`.
- Verification: `python -m pytest tests/test_admin.py -k synced_at -q` →
  3 passed (create-listing non-null, refresh non-null, migration backfill
  == `2026-10-01 10:00:00`); full `python -m pytest -q` → 218 passed
  (215 prior + 3 new). `python -m alembic heads` → single head
  `b2c3d4e5f6a7`; `alembic upgrade head` on a scratch sqlite db upgraded the
  full chain with `playlist.synced_at` present.

## 2026-10-09 — backend colour review fixes: honest palette wraparound, newline-safe colour validation

- Palette wraparound made honest in both places: exhausted-palette fallback
  now cycles by genre count (`backend/app/routers/admin.py`,
  `_first_unused_color`) instead of holding one colour forever, and the
  migration backfill (`backend/alembic/versions/a1b2c3d4e5f6_genre_color.py`)
  uses its `ORDER BY id` loop index to rotate. First-unused assignment for
  the ≤8-genre case is unchanged.
- Colour validation switched to `_COLOR_RE.fullmatch`
  (`backend/app/routers/admin.py`) so `"#123abc\n"` is rejected (422);
  normalize-then-store unchanged (`#FF00FF` → `#ff00ff`).
- Also includes the test-only commit `63478d9` (backfill migration test now
  asserts A = palette[0], B = palette[1] exactly); tests only, no behaviour
  change.
- Files: `backend/app/routers/admin.py`,
  `backend/alembic/versions/a1b2c3d4e5f6_genre_color.py`,
  `backend/tests/test_admin.py`, `docs/changelog.md`.
- Restart required: backend only (router logic + migration changed) —
  `docker compose up -d --build backend`.
- Verification: `python -m pytest -q` (whole backend suite) → 215 passed
  (colour tests: 6 passed, incl. new newline-reject + uppercase-normalize
  assertions).

## 2026-10-09 — backend: genre accent colour (model, migration, CRUD, serialization)

- Added `GENRE_PALETTE` (8 hex colours) and nullable `Genre.color` column
  (`backend/app/models.py`).
- New migration `backend/alembic/versions/a1b2c3d4e5f6_genre_color.py`
  (revision `a1b2c3d4e5f6`, down_revision `e5f6a7b8c9d0`): batch-adds the
  nullable `color` column and backfills each existing genre with the first
  unused palette colour (palette inlined in the migration, not imported).
  Note: the implementation plan claimed `d4e5f6a7b8c9` was the repo's latest
  revision; `e5f6a7b8c9d0` (add revoked session) was added later by the
  security-hardening commit, so the chain was corrected to that.
- `GenreOut` gained `color: str = ""` (`backend/app/schemas.py`); all
  serialization sites pass it through (`backend/app/routers/genres.py`
  list + detail, `backend/app/routers/now.py`, `backend/app/routers/schedule.py`).
- `backend/app/routers/admin.py`: `GenreIn`/`GenreUpdate` accept `color`
  (`#rrggbb` validated, lowercased, empty string rejected on update);
  create assigns the first unused palette colour when omitted; update
  validates before applying and now pushes `notify_radio(build_now(...))`
  so the public page stays in sync (refresh moved after the notify because
  the broadcast-state commit expires the returned ORM row).
- Tests added to `backend/tests/test_admin.py`: explicit colour on create,
  palette auto-assignment (first unused), update colour, invalid colour
  rejected (422), public genre list includes colour, and a hand-built
  pre-migration db backfill test via alembic subprocess (mirrors the
  repo's existing migration-test pattern).
- Restart required: backend only — `docker compose up -d --build backend`.
- Verification: `python -m pytest tests/test_admin.py -q` → 84 passed;
  `python -m pytest -q` (whole backend suite) → 215 passed.

## 2026-10-09 — volume fader follow-ups: Home/End key test added; fader spec drag-gain wording corrected

- Added a Home/End bounds test to
  `frontend/src/components/deck/VolumeFader.dom.test.tsx` (suite now
  138 tests in 18 files).
- Corrected the drag-gain wording in
  `docs/superpowers/specs/2026-10-09-volume-fader-design.md` (1:1, not
  the knob's delta/2 — code was already correct).
- Tests/docs only — no container restart required.
- Verification: `npm run test` (138 tests in 18 files) +
  `npm run typecheck` + `npm run build` green.

## 2026-10-09 — homepage mixer: added vertical volume fader beside master knob; removed decorative mini-knobs

- Added `VolumeFader` (`frontend/src/components/deck/VolumeFader.tsx`,
  `frontend/src/components/deck/VolumeFader.dom.test.tsx`): vertical
  `role="slider"` rail with drag (1:1 vertical gain, pointer
  capture/cancel), keyboard steps (arrows ±2 or ±10 with shift,
  PageUp/PageDown ±10, Home/End), clamped 0–100, `disabled` support.
- Wired into the RadioPage mixer below the master `VolumeKnob`
  (`frontend/src/pages/RadioPage.tsx`), bound to `player.volume` /
  `player.setVolume`, disabled when off air; the three decorative
  `.deck-knob` spans were removed (master knob unchanged).
- Fader rail/thumb styles added after the deck-knob rules
  (`frontend/src/styles/vintage.css`); `.deck-knob` styles kept for the
  admin Now Playing panel.
- Page DOM test extended: knob + fader share the same `aria-valuenow`,
  decorative knobs asserted gone (`frontend/src/pages/
  RadioPage.dom.test.tsx`).
- **Container restart required (frontend only):**
  `docker compose up -d --build frontend`, then hard-refresh the
  browser (Ctrl+Shift+R).
- Verification: `npm run test` (137 tests in 18 files) +
  `npm run typecheck` + `npm run build` green.

## 2026-10-09 — vinyl-deck-ui branch complete — dark deck homepage (no listener skip/stop), dark admin studio with deck Now Playing (full transport), public GET /api/schedule/today

- Umbrella entry for the whole branch (details in the entries below), plus
  the final verification pass and two polish fixes: the admin sleeve
  progress bar gained `aria-label="Playback position"`
  (`frontend/src/components/admin/NowPlayingPanel.tsx`), and the RadioPage
  DOM suite gained a test covering the player-error Retry path (the
  `onError` wiring fires → "Retry" renders → clicking it re-fetches
  `/api/now`) (`frontend/src/pages/RadioPage.dom.test.tsx`, now 8 tests).
- Files touched: see entries below (branch-wide), plus the two polish files
  above and `docs/changelog.md` (this entry).
- **Container restart required (cumulative for the branch — both
  containers):** `docker compose up -d --build backend frontend`, then
  hard-refresh the browser (Ctrl+Shift+R).
- Verification: `npm run test` (130 tests in 17 files) + `npm run typecheck`
  + `npm run build` green; `python -m pytest -q` 209 passed.

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
- Fixed the `.btn-danger-solid:hover:not(:disabled)` affordance (previously
  a darkened hover that read as lower contrast; now `filter:
  brightness(1.08)` so the label stays readable on hover).
- Removed dead code `frontend/src/components/GenreDial.tsx` (own commit;
  referenced nowhere else — verified before deletion).
- Review follow-ups: scoped `.admin-deck`/`.admin-sleeve` grid columns with
  `#panel-now` (they were being beaten by later base rules in the deck
  section), replaced the hover rule with `filter: brightness(1.08)` and
  deleted the dead `.source .badge` rule, added a margin guard
  (`.admin-deck .np-title { margin: 6px 0 4px; }` against the global
  `.admin h2` margin), and gave the np-bar fill `role="progressbar"` +
  aria value attributes driven by a shared `livePct` const.
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
