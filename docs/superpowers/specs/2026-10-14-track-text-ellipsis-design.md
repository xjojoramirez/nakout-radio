# Track text overflow: ellipsis (issue #5) — design

## Problem

With a long track title and/or artist on the radio page (`RadioPage.tsx`), the
now-playing hero breaks its layout on both mobile and desktop:

- `.np-title` (the `h1`) wraps without a height cap (`text-wrap: balance;
  overflow-wrap: anywhere`), so a long title pushes the progress bar,
  controls, and schedule far down — worse on narrow phones.
- `.np-artist` has no overflow handling at all; a long unbroken artist string
  overflows the sleeve grid column horizontally.

## Goal

Long track text is capped with an ellipsis instead of breaking the hero
layout, on both mobile and desktop, while the full text stays available
(screen readers keep the full DOM text; pointer users get a hover tooltip
via the `title` attribute).

## Non-goals

- **Marquee / scrolling text.** Considered and consciously rejected for this
  fix: auto-moving content needs a pause mechanism (WCAG 2.2.2), a
  `prefers-reduced-motion` path, and JS to animate only on overflow. That is
  a separate feature (see issue #5 discussion), not a bugfix.
- The genre `kicker` line, schedule slot names, the deck's `.dj strong`, and
  the admin now-card are out of scope; only track title/artist change.

## Design

Base styles (no media query) so the fix applies to every viewport:

- `.np-title` gains a two-line clamp:
  `display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient:
  vertical; overflow: hidden;` — existing font sizing, `text-wrap:
  balance`, and `overflow-wrap: anywhere` stay. The clamp also reaches the
  reused `.np-title` spots (admin deck, admin now-card), which have the same
  overflow problem — accepted as consistent behavior.
- `.sleeve > div` gains `min-width: 0` so the grid text column can always
  shrink (defensive; the track is already `minmax(0, 1fr)`).
- `.sleeve .np-artist` gets `white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis;` — scoped to the hero so the offline notice
  ("The deck is at rest…") and empty-schedule message, which also use
  `.np-artist`, are never truncated.
- `RadioPage.tsx` puts `title={track.title}` / `title={track.artist}` on the
  hero title and artist so truncated text is readable on hover. Attributes
  are omitted for fallback text ("Tune in", "Nakout Radio").

## Testing

- jsdom does not lay out CSS, so the DOM-level test asserts the tooltip
  attributes (the only testable behavior change); the visual rules are
  verified in the built CSS bundle and by a manual browser check after
  deploy.
- No regression to existing RadioPage tests expected.
