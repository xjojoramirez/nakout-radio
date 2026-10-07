# Mobile Responsive Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the home (radio) page and admin panel to look and work well on phones, via CSS-only media-query changes plus one viewport-meta tweak.

**Architecture:** All layout work happens inside three new/expanded media-query tiers in `frontend/src/styles/vintage.css` (≤920px stays as is; ≤600px is the main mobile tier; ≤380px is the small-phone tier). The desktop admin "fixed shell" (viewport-locked, inner scroll areas) is neutralized inside the ≤600px tier so the page scrolls as one document. Desktop (>920px) rendering is unchanged because every rule is scoped inside a media query.

**Tech Stack:** Plain CSS (existing `vintage.css`), HTML meta tags, Vite/React (unchanged).

**Spec:** `docs/superpowers/specs/2026-10-07-mobile-responsive-design.md`

**Verification notes:** There are no CSS unit tests in this project (and no CSS test framework — adding one is out of scope). Each task is verified by `npm run build` (parses the CSS into the bundle and runs tsc) and the full `npm test` suite is run at the end. Since no TSX changes are made, existing DOM tests must keep passing unchanged.

All npm commands run with workdir `frontend`.

---

### Task 1: Viewport meta for safe areas

**Files:**
- Modify: `frontend/index.html:5`

- [ ] **Step 1: Edit the viewport meta tag**

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

(`viewport-fit=cover` makes `env(safe-area-inset-*)` report real values on
notched phones; Tasks 3, 4 and 6 depend on it.)

- [ ] **Step 2: Build to verify nothing broke**

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds; dist regenerated.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "Add viewport-fit=cover for mobile safe areas"
```

---

### Task 2: Mobile tier scaffold — page scroll unlock (≤600px)

**Files:**
- Modify: `frontend/src/styles/vintage.css:1090-1128` (the whole `@media (max-width: 560px)` block)

- [ ] **Step 1: Replace the old 560px block**

Find this block (starts with the comment-free `@media (max-width: 560px) {` and ends with its closing `}`):

```css
@media (max-width: 560px) {
  .admin {
    padding: 20px;
  }

  .admin-stable {
    min-height: min(360px, 55vh);
  }

  #panel-playlists {
    overflow-y: auto;
  }

  #panel-playlists .channel-scroll {
    flex: 0 0 auto;
    height: 320px;
  }

  #panel-now {
    overflow-y: auto;
  }

  #panel-now .queue-list {
    flex: 0 0 auto;
    max-height: 420px;
  }

  .radio-cabinet {
    padding: 20px;
  }

  .radio-header h1 {
    font-size: 1.6rem;
  }

  .time-pair {
    grid-template-columns: 1fr;
  }
}
```

Replace it entirely with:

```css
/* ---------- Mobile: phones (≤600px) ---------- */

@media (max-width: 600px) {
  /* Normal page scrolling: neutralize the admin fixed shell */
  body.admin-fixed {
    height: auto;
    overflow: auto;
    place-items: start center;
  }

  .admin-shell {
    height: auto;
    min-height: 100%;
    display: block;
  }

  .admin-tabpanel {
    overflow: visible;
  }

  #panel-now,
  #panel-playlists {
    display: block;
    overflow: visible;
  }

  #panel-now .queue-list,
  #panel-playlists .channel-scroll,
  #panel-playlists .added-playlists {
    flex: 0 0 auto;
    height: auto;
    max-height: none;
    overflow: visible;
  }

  body {
    padding: 8px 0;
  }

  /* Carried over from the old 560px block so nothing regresses */
  .admin {
    padding: 20px;
  }

  .admin-stable {
    min-height: min(360px, 55vh);
  }

  .radio-cabinet {
    padding: 20px;
  }

  .time-pair {
    grid-template-columns: 1fr;
  }
}
```

Rationale: the old block was a cramped one-off; the new tier moves the
breakpoint to 600px, keeps every rule it provided (so no intermediate-commit
regression), and adds the admin page-scroll unlock, which also fixes the
mobile Safari clipped-top problem described in the spec.

- [ ] **Step 2: Build to verify the CSS parses**

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "Unlock page scroll on mobile admin, move breakpoint to 600px"
```

---

### Task 3: Home page (radio) mobile rules (≤600px)

**Files:**
- Modify: `frontend/src/styles/vintage.css` (inside the new `@media (max-width: 600px)` block)

- [ ] **Step 1: Add home-page rules**

Inside the `@media (max-width: 600px)` block from Task 2, extend the existing
`.radio-cabinet` rule and add new rules after the carried-over section, before
the closing `}` of the media query:

```css
  /* Home page */
  .radio-cabinet {
    border-width: 4px;
    padding-bottom: max(20px, env(safe-area-inset-bottom));
  }

  .radio-header {
    flex-wrap: wrap;
  }

  .radio-header h1 {
    font-size: 1.5rem;
  }

  .genre-row {
    justify-content: center;
  }

  .controls button {
    min-height: 44px;
    min-width: 88px;
  }

  .volume {
    flex: 1;
  }

  .volume input[type="range"] {
    flex: 1;
    width: auto;
    min-width: 100px;
    max-width: 160px;
  }
```

(Note: two separate `.radio-cabinet` rules inside the same media query are
fine — CSS merges them. The `padding: 20px` comes from Task 2, the
`border-width`/`padding-bottom` here.)

- [ ] **Step 2: Build to verify the CSS parses**

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "Polish home radio page for phone widths"
```

---

### Task 4: Admin chrome — header, tabs, forms, buttons (≤600px)

**Files:**
- Modify: `frontend/src/styles/vintage.css` (inside the `@media (max-width: 600px)` block)

- [ ] **Step 1: Add admin chrome rules**

Inside the same `@media (max-width: 600px)` block, add after the Task 3 rules:

```css
  /* Admin header, tabs, forms */
  .admin {
    padding-bottom: max(20px, env(safe-area-inset-bottom));
  }

  .admin-header h1,
  .admin-login h1 {
    font-size: 1.5rem;
  }

  .admin-tabs {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }

  .admin-tabs button {
    min-height: 44px;
    padding: 10px 12px;
  }

  .form-grid,
  .skeleton-form {
    grid-template-columns: 1fr;
  }

  .field input,
  .admin input:not([type="checkbox"]),
  .admin select {
    font-size: 16px;
    min-height: 44px;
  }

  .form-grid .btn {
    height: auto;
    min-height: 44px;
  }

  .btn {
    min-height: 44px;
  }

  .days button {
    min-height: 44px;
  }
```

Notes: `16px` input font stops iOS Safari zoom-on-focus; the
`:not([type="checkbox"])` guard keeps native checkboxes (genre edit row,
`.field-inline`) unstretched. `.admin-tabs { flex-wrap: wrap }` from the
desktop rule becomes inert once `display: grid` applies.

- [ ] **Step 2: Build to verify the CSS parses**

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "Mobile admin chrome: 2x2 tab grid, 16px inputs, 44px targets"
```

---

### Task 5: Admin rows, queue, playlist browser (≤600px)

**Files:**
- Modify: `frontend/src/styles/vintage.css` (inside the `@media (max-width: 600px)` block)

- [ ] **Step 1: Add row/queue/channel rules**

Inside the same `@media (max-width: 600px)` block, add after the Task 4 rules:

```css
  /* List rows, queue, playlist browser */
  .added-playlists li,
  .genre-admin-list li {
    flex-wrap: wrap;
  }

  .added-playlists .pl-main {
    min-width: 0;
  }

  .pl-actions,
  .row-actions {
    width: 100%;
    margin-left: 0;
  }

  .pl-actions .btn,
  .row-actions .btn {
    flex: 1;
  }

  .queue-row {
    gap: 8px;
  }

  .drag-handle {
    min-width: 32px;
    text-align: center;
  }

  .queue-title,
  .queue-artist {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .channel-grid {
    grid-template-columns: repeat(2, 1fr);
  }
```

- [ ] **Step 2: Build to verify the CSS parses**

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "Mobile admin: stacked row actions, 2-col channel grid, queue truncation"
```

---

### Task 6: Small-phone tier (≤380px)

**Files:**
- Modify: `frontend/src/styles/vintage.css` (add a new block after the 600px block)

- [ ] **Step 1: Add the 380px tier**

Immediately after the closing `}` of the `@media (max-width: 600px)` block
(and before the `@media (prefers-reduced-motion: reduce)` block), add:

```css
/* ---------- Small phones (≤380px) ---------- */

@media (max-width: 380px) {
  .radio-cabinet {
    padding: 16px;
    padding-bottom: max(16px, env(safe-area-inset-bottom));
  }

  .now-playing {
    gap: 12px;
    padding: 12px;
  }

  .now-playing .art {
    width: 72px;
    height: 72px;
  }

  .now-playing .title {
    font-size: 0.95rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .admin {
    padding: 16px;
    padding-bottom: max(16px, env(safe-area-inset-bottom));
  }

  .channel-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }

  .channel-card .ch-title {
    font-size: 0.8rem;
  }

  .admin-header-actions {
    gap: 4px;
  }
}
```

- [ ] **Step 2: Build to verify the CSS parses**

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "Add small-phone (≤380px) tier: clamped titles, tighter padding"
```

---

### Task 7: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `npm test` (workdir `frontend`)
Expected: all existing vitest suites pass, zero changes to test files.

- [ ] **Step 2: Typecheck and build**

Run: `npm run typecheck` (workdir `frontend`)
Expected: no errors.

Run: `npm run build` (workdir `frontend`)
Expected: build succeeds.

- [ ] **Step 3: Manual visual checklist**

Start the dev servers (`uvicorn app.main:app --reload` in `backend`,
`npm run dev` in `frontend`), then in browser DevTools device mode check both
pages at widths **320 / 375 / 600 / 768 / 920**:

- [ ] Home page (empty / playing / error states): no horizontal scroll at 320px; MUTE button and volume slider share one row; "Tuned:" row centered; listeners count never collides with the title.
- [ ] Admin login: form centered, inputs full width, no iOS zoom (16px font).
- [ ] Admin ready — all four tabs: 2×2 tab grid; page scrolls as one document (no inner scroll traps); list-row action buttons on their own full-width line; channel grid 2 columns; queue rows truncate with ellipsis.
- [ ] At 768px/920px: desktop shell behavior intact (fixed shell, inner scroll areas).

Acceptance criteria (from spec): no horizontal scroll at 320px in any state; ≥44px tap height at ≤600px; 16px input font; admin scrolls as one document at ≤600px; desktop >920px unchanged (`git diff` shows zero changes outside `frontend/index.html` and `frontend/src/styles/vintage.css`).
