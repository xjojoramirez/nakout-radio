# Icon-only Mute/Unmute Button — Design

Date: 2026-10-08
Status: Approved (conversational design review)

## Problem

The mute control in `.controls` (frontend/src/pages/RadioPage.tsx:46-53) is a
text button (`UNMUTE` / `MUTE`). On mobile, the button's `min-width: 88px`
(vintage.css `.controls button` in the 380px media query) combined with the
volume slider's `flex: 1` makes the button overlap the slider.

## Goal

Replace the text button with a compact icon-only button that works on all
screen sizes and removes the mobile overlap.

## Design

### Component (RadioPage.tsx)

Replace the text button with an icon button:

- Two inline SVG icons, rendered conditionally:
  - **Speaker with sound waves** — shown when muted (action available: unmute).
  - **Speaker with diagonal slash** — shown when unmuted (action available: mute).
- Same `onClick={player.toggleMute}` handler.
- Styled with a new `.mute-btn` class.

Two simple inline SVGs are used. No icon dependency is added (rejected:
lucide-react/react-icons — a dependency for one icon; unicode emoji —
inconsistent rendering across platforms).

### Accessibility

- `aria-label` reflects the offered action, not the state:
  - muted -> `aria-label="Unmute"`
  - unmuted -> `aria-label="Mute"`
- `title` attribute mirrors the aria-label for desktop hover tooltips.
- Icon SVGs get `aria-hidden="true"`; the accessible name comes only from
  the aria-label.

### Styling (vintage.css)

New `.mute-btn` rules:

- Circular: `border-radius: 50%`, fixed `44px x 44px` (meets touch-target
  minimum, replaces the old `min-width: 88px` text-button behavior).
- Amber background with same hover treatment as `.controls button.tune-in`
  to match the vintage aesthetic.
- Centered SVG icon at ~22px, `pointer-events: none` on the svg so clicks
  always land on the button.

The volume slider keeps `flex: 1`; since the button no longer has an
88px min-width, both fit side by side on narrow screens. No
mobile-only media-query rules are required — one style works everywhere.

### Tests (RadioPage.dom.test.tsx)

Update accessible-name queries:

- `{ name: "UNMUTE" }` -> `{ name: "Unmute" }`
- `{ name: "MUTE" }` -> `{ name: "Mute" }`
- The `/mute/i` regex in the offline test needs no change.

### Out of scope

- Volume slider styling changes.
- Any other control layout rework.

## Verification

- `npm run test` and `npm run typecheck` in `frontend/`.
