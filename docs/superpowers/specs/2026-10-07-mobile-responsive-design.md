# Mobile Responsive Design — Nakout Radio

Date: 2026-10-07
Status: Approved design (approach A — CSS-only responsive polish)

## Goal

Polish both existing pages (home radio player and admin panel) to look and work
well on phones. Not a touch-first redesign: occasional admin use on mobile,
desktop rendering must remain unchanged.

## Approach

CSS-only. All changes are scoped inside media queries in
`frontend/src/styles/vintage.css`. One supporting change in
`frontend/index.html` (viewport meta). No TypeScript/TSX changes, no new
dependencies, no test changes.

Two files touched:

- `frontend/src/styles/vintage.css` — all layout work
- `frontend/index.html` — upgrade viewport meta (see below)

Every new rule lives inside a media query, so desktop (>920px) rendering is
unchanged.

## Files & structure

### `frontend/index.html`

Replace:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
```

with:

```html
<meta
  name="viewport"
  content="width=device-width, initial-scale=1.0, viewport-fit=cover"
/>
```

`viewport-fit=cover` makes `env(safe-area-inset-*)` report real values on
notched phones; several rules below depend on it.

### `frontend/src/styles/vintage.css`

The existing `@media (max-width: 920px)` block stays. The existing cramped
`@media (max-width: 560px)` block is replaced by a reorganized mobile tier:

1. `@media (max-width: 920px)` (existing, unchanged): tablet/landscape tier —
   playlists sidebar stacks, search input goes full width.
2. `@media (max-width: 600px)`: the main mobile tier — page scroll unlock, tap
   targets, stacking, safe-area padding.
3. `@media (max-width: 380px)`: small-phone tier (iPhone-SE-class) — only
   padding/font-size reductions enough to avoid clipping at 320px.

Tiers use only `max-width`, so behavior is monotonic — smaller tiers inherit
larger tiers' rules.

## Home page (RadioPage) on mobile

All rules scoped under `.radio-cabinet` inside the mobile tiers.

### Header

- ≤600px: h1 font-size 2rem → 1.5rem; keep the one-row baseline layout.
- Add `flex-wrap: wrap` as a safety net; `.listeners` keeps
  `white-space: nowrap` and drops to its own line only if genuinely out of
  room (verified: at 380px a 1.5rem Bebas title + "12 listening" still fit on
  one row; at 320px it wraps cleanly).

### Now Playing card

- Stays horizontal flex with 96px art at >380px.
- ≤380px: art shrinks to 72px; `.now-playing .title` clamps to 2 lines
  (`-webkit-line-clamp` pattern, like channel cards) so an overlong YouTube
  title cannot push the artist/progress bar out of the card.
- Empty state (`.now-playing.empty`) unchanged — already full-width centered.

### VU meter

No changes. Flex row of bars, already fluid.

### Genre row ("Tuned: X")

- ≤600px: `justify-content: center`, centered text — matches the centered
  controls row and the radio-device aesthetic.

### Controls row (MUTE / RETRY + volume)

- MUTE/RETRY button: `min-height: 44px; min-width: 88px` (iOS HIG touch
  target), padding/colors unchanged.
- Volume slider: `flex: 1; min-width: 100px; max-width: 160px` (was fixed
  120px) so MUTE and slider share the available row width cleanly.
- `accent-color` already set on the range input; leave native thumb/track.

### Cabinet & page padding

- ≤600px: `.radio-cabinet` padding 28px → 20px, border-width 6px → 4px;
  body padding 16px → 8px top/bottom (cabinet is a centered grid item;
  min-height already handles centering).

## Admin page on mobile

### Unlock page scroll (≤600px)

The key change. Desktop keeps the app-like fixed shell (viewport-locked, inner
scroll areas). Inside the 600px tier, neutralize it so the whole page scrolls
as one document:

- `body.admin-fixed { height: auto; overflow: auto; place-items: start center; }`
- `.admin-shell { height: auto; min-height: 100%; display: block; }`
- `.admin-tabpanel { overflow: visible; }`
- `#panel-now`, `#panel-playlists { display: block; overflow: visible; }`
  (kill the inner flex/scroll containers)
- `.channel-scroll { height: auto; overflow: visible; }`
- `.queue-list { max-height: none; overflow: visible; }`
- remove the `.added-playlists` max-height cap.

This also fixes a real mobile Safari problem with the current fixed shell:
with `body { place-items: center }` and a cabinet shorter than the viewport,
content sits in the vertical middle and its top is clipped with no way to
scroll to it.

### Login screen

`.admin-login` (max-width 340px, centered) works as is; only roomier outer
padding at ≤600px. Nothing special.

### Admin header

Keep title-left / actions-right single row; h1 1.9rem → 1.5rem at ≤600px.
"Back to radio" link and "Log out" button are compact enough to share one row
at 320px.

### Tabs

Current flex-wrap layout wraps 4 tabs to 2 accidental rows on a 375px phone.
At ≤600px make it deliberate: `display: grid; grid-template-columns: repeat(2, 1fr)`
— a 2×2 grid of large tap targets. (Horizontal snap-scroll tabs rejected as
overkill for occasional use.)

### Forms & inputs

- `.form-grid`, `.skeleton-form`: `grid-template-columns: 1fr` (single
  column, full-width inputs) at ≤600px.
- `.field input, .admin input, .admin select`: `font-size: 16px` (prevents iOS
  Safari zoom-on-focus), `min-height: 44px` tap target.

### List rows → stacked cards (≤600px)

- `.added-playlists li`, `.genre-admin-list li`: `flex-wrap: wrap`; action
  buttons drop to a full-width second line.
- Row action buttons (`.row-actions .btn`, `.pl-actions .btn`):
  `min-height: 44px`, `flex: 1` for equal widths.
- `.queue-row` keeps its row layout; drag handle gets a wider tap zone
  (`min-width: 32px`); title/artist truncate via existing flex behavior;
  duration keeps `tabular-nums`.

### Playlist browser (PlaylistsPanel)

- `.channel-grid`: `repeat(auto-fill, minmax(190px, 1fr))` →
  `repeat(2, 1fr)` at ≤600px. At ≤380px:
  `repeat(auto-fill, minmax(150px, 1fr))` (1 col at 320px, 2 cols from ~380px up);
  `.channel-card .ch-title` font-size 0.85rem → 0.8rem.
- `.channel-setup` stays max-width 480px centered.
- Search input (`.panel-head input`) already full width at ≤920px; unchanged.

### Safe areas

≤600px: `.admin` and `.radio-cabinet` get
`padding-bottom: max(20px, env(safe-area-inset-bottom))`. Requires the
`viewport-fit=cover` meta from above.

## Edge cases

- Landscape phones (~640–850px wide, short height): the shell unlock applies
  only at ≤600px, so landscape is "desktop mode"; the existing per-tab inner
  scroll handles short viewports. Radio cabinet at 94vw is fine.
- Very short viewport + keyboard open (iOS): page scroll unlocked at ≤600px,
  so the OS scrolls the focused input into view naturally. No other measures
  needed.
- Long playlist/channel/song names: already handled by existing
  clamp/truncation rules plus the new title clamp; verified no overflow at
  320px.
- `prefers-reduced-motion`: existing block already disables animations; no new
  animations added, nothing to do.

## Testing & verification

1. `npm test` (vitest) and `npm run build` must pass unchanged — no TSX
   changes, so existing dom tests cover the unchanged markup.
2. Manual check via DevTools at widths 320 / 375 / 600 / 768 / 920 on:
   - home page: empty / playing / error states;
   - admin: login phase and ready phase, all four tabs.
3. Acceptance criteria:
   - At 320px: no horizontal scroll on either page in any tested state; all
     text truncated or wrapped, never clipped.
   - All buttons/inputs ≥44px tap height at ≤600px; inputs at 16px font
     (no iOS zoom).
   - Admin page scrolls as one document at ≤600px; no inner scroll traps.
   - Desktop (>920px) rendering unchanged; `git diff` shows zero changes
     outside the two files.
