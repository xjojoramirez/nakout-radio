# Listening Room — listener page redesign (option 3)

Date: 2026-11-24
Status: implemented on `feat/listening-room`
Reference mockup: `docs/superpowers/mockups/2026-11-24-design-directions.html`

## Goal

Give the public radio page a distinct, art-led identity without changing how
the station works. The listener page becomes a quiet "listening room": the
current track's artwork is the record, the room is tinted by that artwork, and
the chrome recedes so the music and schedule lead.

Option 3 was chosen from three directions (Refined Console, Broadcast,
Listening Room). It applies to the listener page, the Studio and every popup
(playlist about, confirm, changelog, track editor, toast).

## Visual system

- **Palette:** ink `#090b0e`, cream `#e9e4d8`, muted `#8f979e`, teal
  `#79c7b8`, hairlines at ~9% cream.
- **Type:** Instrument Serif for the wordmark and track title, Inter for body
  and controls, JetBrains Mono for labels, times and metadata.
- **Shape:** circular artwork disc, 1px hairlines, one translucent panel
  (liner notes) and one floating dock. No wood, plinth, tonearm or RPM badges
  on the listener page.
- **Motion:** the record keeps the existing spin-up / spin-down inertia. CSS
  adds a dashed rotation ring and a slow teal sheen; both respect
  `prefers-reduced-motion`.

## Layout

- **Header:** wordmark left, live state + listener count right, one hairline
  under it.
- **Hero:** two columns — a 344px circular disc and the now-playing column
  (kicker, title, artist, album facts, progress on mobile, the editorial line
  "A quiet room, a loud song.", liner notes).
- **Schedule:** below the liner notes, two columns of hairline rows; the
  current slot is marked with a teal inset bar and teal time.
- **Dock:** fixed, inset, translucent bar with cover, "on the decks" label,
  VU bars, timecode, volume and an outlined teal control labelled **Tune in**
  when muted and **Stop listening** when audible (the action is mute/unmute,
  so the label describes what the listener experiences).
- **Volume:** graphite knob with a glowing teal indicator, and a hairline
  fader whose teal fill ends in a round dot thumb. On phones the dock swaps
  the decorative VU for the volume controls so they stay reachable.

## Artwork disc

- `track.thumbnail_url` is painted on `.record` (and the small centre label).
- A groove texture overlays the image so it still reads as vinyl.
- A blurred, low-opacity copy of the same image sits behind the fold as the
  room tint (`mask-image` fades it out). No colour extraction is required.
- Missing artwork falls back to the existing black vinyl + grooves.

## Responsive

- `≤980px`: disc narrows to 288px and the hero gap tightens.
- `≤820px`: the page stacks (title, disc, progress, liner, schedule), the
  schedule collapses to one column, and the dock becomes the existing
  two-row mobile bar with cover/time/volume hidden.
- `≤600px` / `≤380px`: type scales down, schedule wraps, and the tune control
  keeps a 44px touch target.

## Accessibility and behavior

- All existing behavior is unchanged: tune in / stop listening, volume knob and fader,
  schedule dialogs, playlist-about dialog, liner tabs, offline state and the
  gap phase.
- Focus rings switch to teal with visible offset; the current schedule row is
  not colour-only (it has an inset bar and bold time).
- Decorative layers (ambient, ring, grooves) are `aria-hidden` or CSS-only.
- Reduced-motion users keep a static record.

## Studio and popups

- The Studio reuses the same tokens by remapping the vintage custom properties
  inside `.admin-page` (and `.modal-overlay` for dialogs): ink background,
  teal accent, cream text, Inter body, JetBrains Mono labels, Instrument Serif
  headings.
- Shell: serif wordmark, hairline header, quiet underline tabs, hairline cards
  and rows, outlined secondary buttons, teal primary buttons and focus rings.
- Now playing keeps the deck but renders it as the same artwork disc, with the
  mixer on a hairline panel and teal VU bars.
- Popups: blurred dark overlay, ink panel with hairline border, serif title,
  Inter body, teal primary action. The playlist-about dialog on the listener
  page uses the same shell.
- Mobile: tabs scroll horizontally, the studio deck centres at 280px, the
  track editor uses the existing full-height mobile layout, and popups keep
  10–18px padding with `dvh` caps.

## Non-goals

- Dominant-colour extraction from artwork (blurred art is the tint).
- New playback or scheduling features.

## Verification

- `npm run typecheck`
- `npm test` (35 files / 372 tests)
- `npm run lint`
- `npm run build`
- Visual check in the Docker frontend after
  `docker compose up -d --build frontend`.
