# Favicon & Logo Design

Date: 2026-10-08
Status: Approved

## Goal

Give Nakout Radio a recognizable favicon and a reusable logo, matching the
site's vintage-radio UI and its existing palette.

## Approach (approved: "two-tier set")

One hand-authored SVG vintage tabletop radio, produced at two detail levels:

- **Big logo** (`logo.svg`): full detail — wood cabinet with shading, cream
  speaker grille with horizontal slats, amber dial window with needle, two
  knobs, feet, ink outline.
- **Favicon variant** (`favicon.svg`): same silhouette simplified for tiny
  sizes — no gradients, thicker shapes, 3 grille lines, one amber dial dot.

## Palette (from `frontend/src/styles/vintage.css`)

| Role | Color |
| --- | --- |
| Cabinet wood | `#5b3a24` |
| Wood shading | `#3b2417` |
| Speaker face / cream | `#f4e9d4` |
| Dial glow (amber) | `#f0a13c` |
| Needle / amber strong | `#d97f1d` |
| Outline (ink) | `#2a1a10` |

## Deliverables

| File | Contents |
| --- | --- |
| `frontend/public/favicon.svg` | simplified mark (SVG favicon) |
| `frontend/public/favicon-16.png` | 16px raster fallback |
| `frontend/public/favicon-32.png` | 32px raster fallback |
| `frontend/public/favicon-48.png` | 48px raster fallback |
| `frontend/public/apple-touch-icon.png` | 180px, mark on a full-bleed wood-brown square (iOS applies its own corner mask) |
| `frontend/public/logo.svg` | detailed big logo |
| `frontend/public/logo-512.png` | 512px raster of the big logo |
| `frontend/scripts/render-icons.mjs` | one-time rasterizer script |
| `frontend/package.json` | adds `@resvg/resvg-js` devDependency + `render:icons` script |

## HTML wiring (`frontend/index.html`)

- `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />`
- `<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />`
- `<link rel="apple-touch-icon" href="/apple-touch-icon.png" />`
- `<meta property="og:image" content="<siteUrl>/logo-512.png" />`
- `<meta name="twitter:image" content="<siteUrl>/logo-512.png" />`

`og:image`/`twitter:image` are injected at build time by the existing `seo`
plugin in `frontend/vite.config.ts` (same mechanism as `canonical`/`og:url`),
using `VITE_SITE_URL` (default `http://localhost`) so scrapers get absolute
URLs. The JSON-LD `RadioStation` block gains a matching `logo` property.

## Tooling

PNGs are rasterized from the SVG sources with `@resvg/resvg-js` (devDependency,
run locally via `npm run render:icons`; not used in the Docker build — finished
PNGs are committed under `public/` and baked into `dist/` as usual).

No favicon.ico is generated; SVG + PNG links cover current browsers.

## Out of scope

Larger OG banner art, in-page logo usage changes, backend changes.

## Verification

- `npm run build` in `frontend/` succeeds.
- PNG files exist at the expected sizes and visually match the SVGs.
- Changelog entry added to `docs/changelog.md`; deploy requires
  `docker compose up -d --build frontend` and a hard refresh.
