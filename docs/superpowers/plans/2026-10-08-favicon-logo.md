# Favicon & Logo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Nakout Radio a favicon set and a reusable logo built from one hand-authored SVG vintage radio, in the site's palette.

**Architecture:** Two SVG sources live in `frontend/public/` (`favicon.svg` simplified, `logo.svg` detailed). A one-time Node script rasterizes them (plus a composited apple-touch variant) into committed PNGs using `@resvg/resvg-js`. `index.html` gets static favicon links; the existing `seo` plugin in `vite.config.ts` injects absolute `og:image`/`twitter:image` and a JSON-LD `logo` property from `VITE_SITE_URL`.

**Tech Stack:** Hand-written SVG, `@resvg/resvg-js` (devDependency), Vite public dir, existing seo plugin.

**Spec:** `docs/superpowers/specs/2026-10-08-favicon-logo-design.md`

**Why no unit tests:** The deliverables are static artwork and a deterministic ~30-line rasterizer script. There is no behavior worth asserting in vitest; the real verification is running the script (dimension logging), `npm run build`, and visually checking the outputs. The frontend's existing test suite (`RadioPage.dom.test.tsx` etc.) is untouched and unaffected.

**No Docker change:** Finished assets are committed under `frontend/public/` and baked into `dist/` by the normal build. Only the usual frontend rebuild is needed at the end.

---

### Task 1: SVG sources — favicon and logo

**Files:**
- Create: `frontend/public/favicon.svg`
- Create: `frontend/public/logo.svg`

- [ ] **Step 1: Create the simplified favicon source**

Create `frontend/public/favicon.svg` with exactly:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <!-- cabinet -->
  <path d="M 8 56 L 8 26 C 8 10 18 5 32 5 C 46 5 56 10 56 26 L 56 56 C 56 57.7 54.7 59 53 59 L 11 59 C 9.3 59 8 57.7 8 56 Z"
        fill="#5b3a24" stroke="#2a1a10" stroke-width="2.5" stroke-linejoin="round"/>
  <!-- speaker grille -->
  <rect x="13" y="20" width="22" height="32" rx="4" fill="#f4e9d4" stroke="#2a1a10" stroke-width="2"/>
  <g stroke="#85705a" stroke-width="3" stroke-linecap="round">
    <line x1="18" y1="28" x2="30" y2="28"/>
    <line x1="18" y1="36" x2="30" y2="36"/>
    <line x1="18" y1="44" x2="30" y2="44"/>
  </g>
  <!-- dial -->
  <circle cx="45" cy="27" r="7.5" fill="#f0a13c" stroke="#2a1a10" stroke-width="2"/>
  <circle cx="45" cy="27" r="3" fill="#d97f1d"/>
  <!-- knob -->
  <circle cx="45" cy="42" r="6" fill="#3b2417" stroke="#2a1a10" stroke-width="2"/>
  <circle cx="45" cy="42" r="2" fill="#f4e9d4"/>
</svg>
```

- [ ] **Step 2: Create the detailed big-logo source**

Create `frontend/public/logo.svg` with exactly:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <!-- feet -->
  <rect x="112" y="448" width="56" height="40" rx="12" fill="#241408"/>
  <rect x="344" y="448" width="56" height="40" rx="12" fill="#241408"/>
  <!-- cabinet -->
  <path d="M 64 448 L 64 208 C 64 80 144 40 256 40 C 368 40 448 80 448 208 L 448 448 C 448 462 438 472 424 472 L 88 472 C 74 472 64 462 64 448 Z"
        fill="#5b3a24" stroke="#2a1a10" stroke-width="10" stroke-linejoin="round"/>
  <!-- bottom trim band -->
  <rect x="74" y="368" width="364" height="72" rx="14" fill="#3b2417" opacity="0.45"/>
  <!-- top wood highlight -->
  <path d="M 96 224 C 96 108 168 68 256 68" fill="none" stroke="#6b4630" stroke-width="16" stroke-linecap="round"/>
  <!-- speaker grille -->
  <rect x="104" y="176" width="180" height="168" rx="18" fill="#f4e9d4" stroke="#2a1a10" stroke-width="8"/>
  <g stroke="#85705a" stroke-width="10" stroke-linecap="round">
    <line x1="136" y1="209" x2="252" y2="209"/>
    <line x1="136" y1="235" x2="252" y2="235"/>
    <line x1="136" y1="260" x2="252" y2="260"/>
    <line x1="136" y1="285" x2="252" y2="285"/>
    <line x1="136" y1="311" x2="252" y2="311"/>
  </g>
  <!-- dial window -->
  <rect x="312" y="176" width="120" height="88" rx="14" fill="#f0a13c" stroke="#2a1a10" stroke-width="8"/>
  <g stroke="#f4e9d4" stroke-width="6" stroke-linecap="round">
    <line x1="336" y1="208" x2="336" y2="230"/>
    <line x1="354" y1="208" x2="354" y2="230"/>
    <line x1="390" y1="208" x2="390" y2="230"/>
    <line x1="408" y1="208" x2="408" y2="230"/>
  </g>
  <line x1="372" y1="190" x2="372" y2="250" stroke="#d97f1d" stroke-width="8" stroke-linecap="round"/>
  <!-- knobs -->
  <circle cx="352" cy="330" r="24" fill="#3b2417" stroke="#2a1a10" stroke-width="8"/>
  <circle cx="352" cy="330" r="8" fill="#f4e9d4"/>
  <circle cx="412" cy="330" r="24" fill="#3b2417" stroke="#2a1a10" stroke-width="8"/>
  <circle cx="412" cy="330" r="8" fill="#f4e9d4"/>
</svg>
```

Note: the favicon variant and logo share the same arch silhouette (favicon
geometry is the logo scaled down, with details reduced per the spec). If you
tweak the arch curve in one, keep them consistent.

- [ ] **Step 3: Visual check**

Open `frontend/public/favicon.svg` and `frontend/public/logo.svg` in a browser
and confirm both render: arched wood cabinet, cream grille with slats on the
left, amber dial on the right, knobs below the dial (the logo additionally
shows the wood highlight, trim band, and feet). Adjust geometry if anything
looks off (this is the only eyeball gate before rasterizing).

- [ ] **Step 4: Commit**

```bash
git add frontend/public/favicon.svg frontend/public/logo.svg
git commit -m "feat: add vintage radio svg sources for favicon and logo"
```

---

### Task 2: Rasterizer script and generated PNGs

**Files:**
- Create: `frontend/scripts/render-icons.mjs`
- Modify: `frontend/package.json` (devDependency + `render:icons` script)
- Create (generated): `frontend/public/favicon-16.png`, `frontend/public/favicon-32.png`, `frontend/public/favicon-48.png`, `frontend/public/apple-touch-icon.png`, `frontend/public/logo-512.png`

- [ ] **Step 1: Install the rasterizer**

```bash
cd frontend
npm install --save-dev @resvg/resvg-js
```

Expected: installs cleanly on Windows (prebuilt binary); `package.json`
devDependencies now includes `"@resvg/resvg-js": "^2.x.y"`.

- [ ] **Step 2: Add the npm script**

In `frontend/package.json`, add to `scripts` (after `"preview"`):

```json
    "render:icons": "node scripts/render-icons.mjs",
```

- [ ] **Step 3: Write the rasterizer script**

Create `frontend/scripts/render-icons.mjs` with exactly:

```js
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const here = dirname(fileURLToPath(import.meta.url));
const pub = resolve(here, "..", "public");

function render(svg, width, outPath) {
  const png = new Resvg(svg, { fitTo: { mode: "width", value: width } }).render();
  writeFileSync(outPath, png.asPng());
  console.log(`${outPath}  ${png.width}x${png.height}`);
}

// Composites the favicon mark on a full-bleed wood background for iOS.
// iOS applies its own corner mask, so the background must be full-bleed
// (pre-rounded corners would leave black artifacts after masking).
function wrapAppleTouch(faviconSvg) {
  const inner = faviconSvg
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">` +
    `<rect width="512" height="512" fill="#4a2e1e"/>` +
    `<g transform="translate(64 64) scale(6)">${inner}</g></svg>`
  );
}

const favicon = readFileSync(join(pub, "favicon.svg"), "utf8");
const logo = readFileSync(join(pub, "logo.svg"), "utf8");

for (const size of [16, 32, 48]) {
  render(favicon, size, join(pub, `favicon-${size}.png`));
}
render(wrapAppleTouch(favicon), 180, join(pub, "apple-touch-icon.png"));
render(logo, 512, join(pub, "logo-512.png"));
```

- [ ] **Step 4: Run the script**

```bash
cd frontend
npm run render:icons
```

Expected output (5 lines, paths + dimensions):

```
...\frontend\public\favicon-16.png  16x16
...\frontend\public\favicon-32.png  32x32
...\frontend\public\favicon-48.png  48x48
...\frontend\public\apple-touch-icon.png  180x180
...\frontend\public\logo-512.png  512x512
```

- [ ] **Step 5: Verify the PNGs visually**

Open the five PNGs from `frontend/public/` and confirm they match the SVGs:
favicon PNGs show the simplified radio at each size; the apple-touch icon
shows the mark centered on a full-bleed dark-wood square; the 512px logo
shows the detailed radio.

- [ ] **Step 6: Commit**

```bash
git add frontend/scripts/render-icons.mjs frontend/package.json frontend/package-lock.json frontend/public/favicon-16.png frontend/public/favicon-32.png frontend/public/favicon-48.png frontend/public/apple-touch-icon.png frontend/public/logo-512.png
git commit -m "feat: render favicon and logo pngs from svg sources"
```

---

### Task 3: Wire icons into index.html and the seo plugin

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Add favicon links to index.html**

In `frontend/index.html`, replace:

```html
    <meta name="theme-color" content="#1c110a" />
```

with:

```html
    <meta name="theme-color" content="#1c110a" />

    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
```

- [ ] **Step 2: Inject og:image / twitter:image / JSON-LD logo in the seo plugin**

In `frontend/vite.config.ts`, replace:

```ts
function seo(siteUrl: string): Plugin {
  const canonical = `${siteUrl}/`;
```

with:

```ts
function seo(siteUrl: string): Plugin {
  const canonical = `${siteUrl}/`;
  const ogImage = `${siteUrl}/logo-512.png`;
```

Then replace:

```ts
  const structuredData = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "RadioStation",
    name: "Nakout Radio",
    url: canonical,
    description: DESCRIPTION,
    broadcastDisplayName: "Nakout Radio",
  });
```

with:

```ts
  const structuredData = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "RadioStation",
    name: "Nakout Radio",
    url: canonical,
    logo: ogImage,
    description: DESCRIPTION,
    broadcastDisplayName: "Nakout Radio",
  });
```

Then replace:

```ts
        {
          tag: "meta",
          attrs: { property: "og:url", content: canonical },
          injectTo: "head",
        },
```

with:

```ts
        {
          tag: "meta",
          attrs: { property: "og:url", content: canonical },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { property: "og:image", content: ogImage },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { name: "twitter:image", content: ogImage },
          injectTo: "head",
        },
```

- [ ] **Step 3: Typecheck and build**

```bash
cd frontend
npm run typecheck
npm run build
```

Expected: both succeed with no errors.

- [ ] **Step 4: Verify the build output**

```powershell
Get-ChildItem frontend/dist | Where-Object { $_.Name -match 'favicon|apple|logo' } | Select-Object Name
Select-String -Path frontend/dist/index.html -Pattern 'og:image|favicon|apple-touch|twitter:image'
```

Expected: `favicon.svg`, `favicon-16.png`, `favicon-32.png`,
`favicon-48.png`, `apple-touch-icon.png`, `logo-512.png` present in `dist/`;
`dist/index.html` contains the SVG + PNG icon links and og/twitter image tags
pointing at `<VITE_SITE_URL>/logo-512.png` (default `http://localhost`).

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/vite.config.ts
git commit -m "feat: wire favicon links and og image tags"
```

---

### Task 4: Changelog

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Add the changelog entry**

In `docs/changelog.md`, insert directly below the line `Most recent entries
first. Each entry notes whether a Docker container restart is required (see
`AGENTS.md` for the restart commands).` and above the first `## 2026-10-08`
heading:

```markdown
## 2026-10-08 — Favicon and logo set

- Added a hand-authored vintage-radio logo in the site palette, at two detail
  levels: a simplified `favicon.svg` (plus 16/32/48px PNG fallbacks and a
  180px apple-touch icon) and a detailed `logo.svg`/`logo-512.png` for
  standalone reuse. PNGs are generated from the SVG sources by
  `npm run render:icons` (`frontend/scripts/render-icons.mjs`,
  `@resvg/resvg-js` devDependency).
- `index.html` now links the SVG + PNG favicons and apple-touch icon; the
  `seo` build plugin injects absolute `og:image`/`twitter:image` tags and a
  JSON-LD `logo` property pointing at `<VITE_SITE_URL>/logo-512.png`.
- Files touched:
  - `frontend/public/favicon.svg`, `frontend/public/logo.svg` (new)
  - `frontend/public/favicon-16.png`, `-32.png`, `-48.png`,
    `apple-touch-icon.png`, `logo-512.png` (new, generated)
  - `frontend/scripts/render-icons.mjs` (new)
  - `frontend/package.json`, `frontend/package-lock.json`
  - `frontend/index.html`
  - `frontend/vite.config.ts`
  - `docs/changelog.md` (docs)
- **Container restart required (frontend changed):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run typecheck` and `npm run build` clean; rendered PNG
  dimensions confirmed (16/32/48, 180, 512); icon links and og:image tags
  present in `dist/index.html`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: changelog for favicon and logo set"
```

---

## Final manual step (user)

Deploy the change:

```bash
docker compose up -d --build frontend
```

Then hard-refresh the browser (Ctrl+Shift+R) and confirm the radio favicon
appears in the tab. (Per AGENTS.md; no backend/caddy changes.)
