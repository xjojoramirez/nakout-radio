# Rebrand: description and logo

Date: 2026-11-26
Status: Approved

## Goal

Refresh the public description so it reads like radio first and a station that
knows the music second. Replace the vintage wood-and-amber mark with a
graphite, cream and teal mark that matches the Listening Room. Regenerate every
favicon and the social logo.

## Brand line

`Nakout Radio: Always on. Know the music.`

The line appears in the document title and the Open Graph and Twitter titles.
The descriptions carry the explanation.

## Copy

| Surface | Copy |
| --- | --- |
| Document title | Nakout Radio: Always on. Know the music. |
| Meta description | Nakout Radio never stops: one shared broadcast, a different genre as the day turns. Tune in and leave knowing the song better. Know your music. |
| OG description | One shared broadcast, a different genre as the day turns, and a station that never stops. Tune in and leave knowing the song better: its story, its credits, its chart history. Know your music. |
| Twitter description | One shared broadcast, a different genre as the day turns, and something worth knowing about every song. Tune in. Know your music. |
| JSON-LD description | Nakout Radio is a personal, always-on internet radio station. One shared broadcast, a different genre as the day turns, and something worth knowing about every song. Tune in. Know your music. |
| README intro | A personal internet-radio website streaming the owner's YouTube playlists as a single always-on broadcast, with a different genre as the day turns, liner notes and chart history for the track on air, a live listener count, and an admin panel. Tune in. Know your music. |

The meta description is 143 characters. No em dashes or en dashes in the new
copy.

## Logo

Mark A: the existing tabletop radio silhouette, with the speaker face turned
into a record and the dial carrying liner-note lines. The mark reads as radio
at a glance and as a record collection on the second look.

### Palette

| Role | Color |
| --- | --- |
| Page and icon background | `#090b0e` |
| Cabinet | `#121a1d` |
| Outline, speaker face, text | `#e9e4d8` |
| Record, feet, wells | `#0b1013` |
| Grooves, knobs | `#33403f` |
| Accent, dial, record label | `#79c7b8` |
| Inner outlines | `#090b0e` |

The old wood, cream and amber values are gone.

### Files

- `frontend/public/logo.svg` is the detailed 512 mark, transparent.
- `frontend/public/favicon.svg` is the 64 mark: cabinet, cream speaker face,
  dark record with a teal label, teal dial, one knob. It drops the grooves,
  dial lines and second knob so the shape survives 16px.
- `frontend/public/favicon.ico` packs the 16, 32 and 48 PNGs into a real ICO.
  Without it, `/favicon.ico` fell through the SPA rewrite and returned HTML.
- `frontend/public/favicon-16.png`, `favicon-32.png`, `favicon-48.png` are
  rasterized from the favicon SVG.
- `frontend/public/apple-touch-icon.png` is 180px, full-bleed `#090b0e`, with
  the mark scaled 7x and centred. iOS applies its own corner mask.
- `frontend/public/logo-512.png` is the social and JSON-LD logo on the same
  full-bleed background, so the cream outline survives light previews.

`frontend/scripts/render-icons.mjs` owns the rasterization and the two
full-bleed wrappers.

## Wiring

`frontend/index.html` links the ICO, the SVG favicon with `?v=2`, the 16, 32
and 48 PNGs with `?v=2`, and the 180px Apple touch icon with `?v=2`. It carries
the new title, meta description, OG and Twitter tags.

`frontend/vite.config.ts` keeps the `seo` plugin and updates the shared
`DESCRIPTION` used by the `RadioStation` JSON-LD. The OG and JSON-LD logo URL
carries `?v=2` so crawlers and social cards refetch it.

`README.md` updates the opening description and adds the brand line.

## Out of scope

- No station rename and no route changes.
- No change to the listening room, the deck, the schedule or the Studio.
- No new in-page tagline. The wordmark stays the only in-page brand element.
- No light theme work.

## Verification

- `npm run render:icons` writes the ICO and the five PNGs at the expected
  sizes.
- Inspect the 16, 32, 48, 180 and 512 renders on the dark and cream grounds,
  and check the ICO directory entries.
- `npm run typecheck`, `npm test`, `npm run lint`, `npm run build` and
  `npm run check:bundle` pass.
- After merge, rebuild the frontend container and hard refresh the browser.
