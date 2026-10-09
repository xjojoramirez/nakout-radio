# Volume fader beside master knob — design

Date: 2026-10-09
Branch: `vinyl-deck-ui`
Follow-up to: `2026-10-09-vinyl-deck-ui-design.md`

## Goal

On the homepage mixer, keep the interactive master-volume knob and replace the three
decorative mini-knobs with a vertical volume fader (drag line) that controls the same
volume. Admin Now Playing's decorative knob row is untouched.

## Design

- New component `frontend/src/components/deck/VolumeFader.tsx`:
  - Vertical rail with a draggable thumb; thumb position maps linearly to volume
    (bottom = 0, top = 100), driven by the `value` prop.
  - Pointer drag: pointerdown captures, vertical movement maps to volume with the same
    gain as the knob (delta / 2 per move event), clamped 0–100; `touch-action: none`.
  - Keyboard: Left/Down −2, Right/Up +2, PageDown/PageUp ±10, Home 0, End 100.
  - A11y: `role="slider"`, `tabIndex=0`, `aria-orientation="vertical"`, `aria-valuemin`
    0, `aria-valuemax` 100, `aria-valuenow`, accessible name from `label` prop.
  - `disabled` prop greys out and blocks interaction.
- `RadioPage.tsx`: mixer `.knob-row` keeps `VolumeKnob` (master), removes the three
  decorative `.deck-knob` spans, adds `VolumeFader` bound to `player.volume` /
  `player.setVolume`, `disabled` when off air, with a "Master / Volume" pairing visual
  consistent with the deck look.
- CSS in `frontend/src/styles/vintage.css` deck section: `.fader` rail + thumb styles
  reusing deck tokens (vinyl/amber/cream); `.deck-knob` styles stay (admin still uses
  them).
- Homepage volume persists via the existing `nakout.volume` localStorage key
  (through `player.setVolume`) — no new keys.

## Testing

- New `VolumeFader.dom.test.tsx` mirroring the knob suite: slider role/ARIA values,
  drag changes value (PointerEvent), keyboard steps incl. Home/End, disabled blocks.
- Existing `VolumeKnob.dom.test.tsx` unchanged; `RadioPage.dom.test.tsx` re-checked.
- Verification: `npm run test`, `npm run typecheck`, `npm run build` in `frontend`.

## Deployment

- Restart container `frontend`: `docker compose up -d --build frontend`, hard-refresh.
