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

- **Palette (dark, default):** ink `#090b0e`, cream `#e9e4d8`, muted
  `#8f979e`, teal `#79c7b8`, hairlines at ~9% cream.
- **Palette (light, Sea Glass):** sage mist `#d5e1cf`, frosted panel
  `#f4faf1` at ~55%, ink `#122019`, muted `#4f6355`, sea-green `#245c3e`,
  hairlines at ~14% ink. Soft green and warm botanical glows sit behind the
  glass. The turntable plinth and vinyl stay graphite in both themes.
- **Theme choice:** first visit follows the OS, an explicit choice is remembered
  in `localStorage`, and a sun/moon switch sits in the listener header, the
  Studio header and the Studio login.
- **Type:** two families only - Inter for body, controls, the wordmark, track
  titles, headings and popup titles; JetBrains Mono for labels, times and
  metadata. Instrument Serif, Bricolage Grotesque and DM Mono were removed.
- **Shape:** circular artwork disc, 1px hairlines, one frosted panel
  (liner notes), one frosted dock and, in light mode, translucent glass cards
  in the Studio. No wood, plinth, tonearm or RPM badges on the listener page.
- **Motion:** the record keeps the existing spin-up / spin-down inertia. CSS
  adds a dashed rotation ring and a slow teal sheen; both respect
  `prefers-reduced-motion`.

## Layout

- **Header:** wordmark left, live state + listener count right, one hairline
  under it.
- **Hero:** two columns — a 344px circular disc and the now-playing column
  (kicker, title, artist, album facts, progress on mobile, liner notes). The
  kicker is set a step larger (0.68rem) for legibility.
- **Ambient bleed:** a full-viewport blurred copy of the current artwork sits
  behind the hero with no frame. It is 60px taller than the page top so the top
  edge starts off-screen, and a bottom mask dissolves it into the page and
  browser background.
- **Vertical balance:** the page uses 24px top and bottom padding (18px on
  phones) and centres itself in the viewport when the content is shorter than
  the screen, keeping the gap above the header close to the gap above the dock.
- **Schedule:** below the liner notes, two columns of hairline rows; the
  current slot is marked with a teal inset bar and teal time.
- **Dock:** fixed, inset, frosted bar with cover, "on the decks" label,
  VU bars, timecode, volume and an outlined teal control labelled **Tune in**
  when muted and **Stop listening** when audible (the action is mute/unmute,
  so the label describes what the listener experiences).
- **Volume:** graphite knob with a glowing teal indicator, and a hairline
  fader whose teal fill ends in a round dot thumb. On phones the dock swaps
  the decorative VU for the volume controls so they stay reachable.

## Artwork disc

- The deck is a square graphite plinth with an 18px radius, a hairline edge
  and a soft shadow. The circular platter is inset 8%, with the dashed
  rotation ring around it.
- The record is black vinyl with concentric grooves; `track.thumbnail_url` is
  painted only on the round centre label (42% of the disc), like the original
  deck. The label keeps a spindle hole and a thin cream ring.
- A subtle groove texture overlays the vinyl for depth.
- A slim cream tonearm on a graphite pivot sits on the plinth's top-right
  corner, with a teal centre dot and a dark headshell with a teal stylus line.
  It rests at −2° and swings to 24° while the station is playing (same on the
  Studio deck).
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
  teal accent, cream text, Inter body and headings, JetBrains Mono labels.
- Shell: sans wordmark, hairline header, quiet underline tabs, hairline cards
  and rows, outlined secondary buttons, teal primary buttons and focus rings.
  In Sea Glass light mode the cards, rows, login panel, schedule editor and
  dialogs become frosted surfaces with a white rim and soft green shadow.
- Now playing keeps the deck but renders it as the same artwork disc, with the
  mixer on a hairline panel and teal VU bars.
- Popups: blurred scrim, panel with hairline border, Inter 600 title, Inter
  body, teal primary action. The scrim and panel follow the active theme. The
  playlist-about dialog on the listener page uses the same shell.
- **Setup path:** genre → Nakout playlist → schedule slot. Genre cards expose
  Add Nakout playlist and Schedule, and the add dialog opens with the genre
  already locked. No second genre picker.
- **Schedule:** Week / Day / By genre stay. Week blocks wrap their names and
  expose the full genre and time on hover/focus. Add/Edit opens a sticky side
  editor on desktop and a bottom sheet on phones, with a live start → end and
  duration preview, the next slot, a same-start warning and Delete inside the
  editor.
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
