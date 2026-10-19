# Vinyl label shows a square album art (issue #27)

Date: 2026-10-19
Status: implemented on `fix/vinyl-round-label-27`
Report: "Make the vinyl album art cover all round in the middle. Currently,
I can see squares album art."

## Problem

The cover art on the record label is clipped to a circle (`border-radius:
50%`, `inset: 31%` in `vintage.css`), but listeners still saw a square:
the artwork itself — bars, squared-off edges and all — sat inside the round
clip.

## Root cause

The label paints `track.thumbnail_url`, which the backend takes from the
YouTube Data API `snippet.thumbnails.high` entry — i.e.
`https://i.ytimg.com/vi/<id>/hqdefault.jpg`. That rendition is 480x360
(4:3): YouTube letterboxes the 16:9 frame into it with 45px black bars top
and bottom (the 16:9 content is only 480x270 in the middle). On top of
that, an album-art video often contains its own square cover centered in
the 16:9 frame, flanked by side bands.

With `background-size: cover` on a square label the image is scaled to the
label height, which shows the *whole 4:3 rendition* center-cropped to a
square: the black bars stay visible at the top/bottom of the circle and the
square cover embedded in the frame stays visible in the middle. Measured
against the live site (P.O.D. — "Youth of the Nation"): the visible square
within the round label was exactly the thumbnail's baked-in square cover,
surrounded by the frame's red side bands and the black letterbox bars.

## Fix

Scale the background so the *16:9 frame's central square* fills the round
label: `background-size: 177.78% auto` (= 480/270 = the frame's 16/9
content ratio) with `background-position: center`. One CSS declaration in
`.record .label` (`frontend/src/styles/vintage.css`):

- the 45px letterbox bars (and any side bands of an embedded square cover)
  are scaled outside the circle;
- for a 16:9 full-bleed thumbnail this is the standard center-square crop;
- for the reported thumbnail it is exactly the square cover, round-cropped
  edge to edge.

The markup (`TurntableDeck`), the sleeve cover (`RadioPage`) and the admin
Now Playing panel are untouched — the issue is only about the round label
in the middle of the record.

## Verification

Reproduced and fixed against the running stack (frontend `:8012`, an
on-air track with a real `hqdefault.jpg`), via headless Edge + DevTools
protocol:

1. before: zoomed capture of the label showed the square cover and bars;
2. after applying the candidate `background-size` live: the label was
   filled edge to edge with a round crop of the cover;
3. after the change was built into the image and the `frontend` container
   was rebuilt/recreated: zoomed capture shows the same round crop from the
   served bundle.

`cd frontend && npm test` (all files pass), `npm run typecheck`,
`npm run build` — clean.
