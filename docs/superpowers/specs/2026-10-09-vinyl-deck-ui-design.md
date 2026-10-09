# Vinyl deck UI redesign — design doc

Date: 2026-10-09 · Status: approved · Branch: `vinyl-deck-ui`
Reference: `UI reference/Nakout Vinyl Deck.html`

## Goal

Re-skin the listener homepage as the vinyl turntable deck from the reference,
removing any listener-side station-control features (Next record / Stop). Re-skin
the entire admin studio onto the same dark theme and rebuild the admin Now
Playing tab as the deck layout — keeping all of its existing functionality.

Decision highlights (from user answers):

1. Homepage adopts the reference's full visual identity: dark `#1c110a`
   palette, wood deck, amber accents, fonts **Bricolage Grotesque** (display)
   and **DM Mono** (mono) replacing Bebas Neue / Inter site-wide.
2. Homepage audio control: the primary button toggles audio — **"Tune in"**
   (play + unmute) / **"Tune out"** (mute; broadcast keeps running while muted,
   like turning a radio down). One mixer knob is a real draggable volume knob;
   the others stay decorative. No skip/stop controls on the homepage.
3. Homepage shows the real daily schedule; a new public read-only backend
   endpoint provides today's slots.
4. The whole admin studio (all tabs) goes dark; the Now Playing tab is rebuilt
   as the deck with complete functionality (Prev / Next / Stop / Auto, genre
   select, queue reorder/shuffle/per-row play, sync).

## 1. Theme takeover (frontend)

`frontend/src/styles/vintage.css` is the single global stylesheet. Re-tokenize
it so the dark acrylic tokens win everywhere:

- `:root` palette from the reference: `--bg #1c110a`, `--wood #2b1a10`,
  `--wood-hi #3a2416`, `--amber #f2a33a`, `--cream #f1e4d0`,
  `--muted #a8917a`, `--vinyl #0c0807`, `--led #ff4a3a`.
- Font tokens: display = Bricolage Grotesque, mono = DM Mono; loaded in
  `frontend/index.html` (Google Fonts, `display=swap`). Bebas Neue/Inter links
  removed.
- Body/backdrop, buttons, inputs, panels, skeletons, modal, tabs, admin cards,
  cream panels → adjusted to the dark tokens (cream panels become wood panels,
  text becomes cream/muted). Keep existing class names so component markup and
  tests are unaffected; adjust rules where hardcoded colors remain.
- Keep `prefers-reduced-motion` support and 44px mobile touch targets.

## 2. Homepage (`frontend/src/pages/RadioPage.tsx`)

New structure (replaces the radio-cabinet markup):

- **Header**: brand `Nakout.Radio` (amber period), on-air chip — LED dot
  (red glow while playing), status text ("On air" / "Standing by"), listener
  count in mono type.
- **Left column — deck**: platter + record (grooves via gradients, album art on
  the record label). The record spins at ~33⅓ RPM-style rotation only while
  playing, with spin-up/spin-down inertia; static (no rotation) when paused,
  off-air, or under reduced-motion. Sheen overlay, pivot, tonearm rotating from
  rest (−4°) to on-record (26°) when playing.
  Decorative "Start / Stop" caption and 33/45 RPM badges (visual only).
- **Mixer strip**: left "On the decks" = station name ("Nakout Radio");
  center VU meter (existing `VUMeter` rebound, animates only while playing);
  right **volume knob** (interactive: pointer-drag vertical, arrow keys,
  ARIA slider semantics, persists to existing `nakout.volume` localStorage) +
  two decorative knobs.
- **Right column — now playing**: cover art + genre kicker ("· live now" when
  playing), `<h1>` title, artist, progress bar + elapsed/duration in mono.
- **Controls**: single primary pill — "Tune in" when muted/off, "Tune out" when
  live. Disabled + themed offline notice when `source === "none"` or no track.
  **No Next record, no Stop button anywhere on the homepage.**
- **Schedule**: "Today's schedule" list from the new endpoint; current slot
  highlighted (amber inset bar like the reference). Refreshed every 5 min.
- Mobile ≤820px: single column, deck first, 44px targets.

Audio hook unchanged: `useYouTubePlayer` still syncs to the server clock; the
previous mute/volume wiring simply maps to the new button/knob affordances.

## 3. Admin studio (dark) — `frontend/src/pages/AdminPage.tsx` + admin components

- Card, tab bar, panels (Playlists / Genres / Schedule), modals, skeletons and
  forms all inherit the dark token takeover; only rule adjustments where colors
  were hardcoded. No behavior changes.
- **Now Playing tab**
  (`frontend/src/components/admin/NowPlayingPanel.tsx`) rebuilt to the deck
  layout: turntable + mixer on the left (spins with the live playing state from
  `BroadcastNow`), now-playing info + progress on the right; transport row:
  **Prev / Next / Stop / Auto** styled as deck pills (Auto highlighted in
  schedule mode); genre select (auto-follows live genre), queue list (on-air
  badge, HTML5 drag-reorder, shuffle, per-row Play with interruption confirm
  dialog), "Sync all playlists". All existing buttons keep their labels/roles
  (tests rely on them). Mobile behavior via `useMediaQuery` kept.

## 4. Backend

One addition, no breaking changes:

- `GET /api/schedule/today` in `backend/app/routers/schedule.py` +
  schemas in `backend/app/schemas.py`. Returns
  `{ current_id: int | null, slots: [{ id, genre_id, genre_name, start_time }] }`
  — slots scheduled for "today" (weekday in `GENRE_TZ`, ascending by start
  time reported with their weekday-relevant `start_time`), current slot
  resolved with the same most-recent-occurrence rule as `resolve_genre_id`.
- Playback/broadcast/queue endpoints unchanged.

## 5. Error handling / states

- Homepage offline: notice + disabled control + static deck.
- Api errors (schedule fetch): render list without highlight; fail silently
  visible as empty section, no crash.
- Volume knob: clamp 0–100; drag works on touch via pointer events.

## 6. Verification

- Frontend: `npx vitest run` (unit/dom suites updated where markup changed),
  `npm run build` (tsc + vite).
- Backend: `pytest` (new tests: `test_schedule_today` for the endpoint incl.
  timezone/cross-midnight slot).
- `docs/changelog.md` entry; requires rebuild of **both** `frontend` and
  `backend` containers afterwards (`docker compose up -d --build backend frontend`).
