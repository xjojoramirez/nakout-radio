# Icon-Only Mute/Unmute Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the overlapping text mute button with a compact icon-only mute/unmute button that fits beside the volume slider on every screen size.

**Architecture:** `RadioPage` renders a circular icon button using two inline SVGs (speaker-with-waves / speaker-with-slash) instead of `UNMUTE`/`MUTE` text. A new `.mute-btn` CSS rule gives it a 44x44px amber circle; the volume slider keeps `flex: 1`, so both controls fit on narrow screens without overlap.

**Tech Stack:** React 18 / TypeScript / Vitest + @testing-library/react; plain CSS (`frontend/src/styles/vintage.css`).

---

## Spec reference

`docs/superpowers/specs/2026-10-08-icon-mute-button-design.md`

## Task 1: Update tests to the icon button's accessible names (TDD red)

**Files:**
- Modify: `frontend/src/pages/RadioPage.dom.test.tsx:87-100`

- [ ] **Step 1: Update the two accessible-name queries**

In `frontend/src/pages/RadioPage.dom.test.tsx`, replace:

```tsx
  it("starts muted and offers an UNMUTE control", async () => {
    render(<RadioPage />);
    expect(
      await screen.findByRole("button", { name: "UNMUTE" }),
    ).toBeInTheDocument();
  });

  it("toggles the mute control", async () => {
    render(<RadioPage />);
    fireEvent.click(await screen.findByRole("button", { name: "UNMUTE" }));
    expect(
      await screen.findByRole("button", { name: "MUTE" }),
    ).toBeInTheDocument();
  });
```

with:

```tsx
  it("starts muted and offers an Unmute control", async () => {
    render(<RadioPage />);
    expect(
      await screen.findByRole("button", { name: "Unmute" }),
    ).toBeInTheDocument();
  });

  it("toggles the mute control", async () => {
    render(<RadioPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Unmute" }));
    expect(
      await screen.findByRole("button", { name: "Mute" }),
    ).toBeInTheDocument();
  });
```

The offline test's `/mute/i` regex (line 113) needs no change.

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `frontend/`): `npm run test -- RadioPage.dom`
Expected: FAIL — the buttons still render with accessible names `"UNMUTE"`/`"MUTE"`, so both updated tests error.

## Task 2: Implement the icon-only mute button (TDD green)

**Files:**
- Modify: `frontend/src/pages/RadioPage.tsx:41-53`

- [ ] **Step 1: Add the two SVG icon components**

In `frontend/src/pages/RadioPage.tsx`, add above the `RadioPage` function:

```tsx
function SoundOnIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <path d="M3 9v6h4l5 4V5L7 9H3Z" fill="currentColor" />
      <path
        d="M15.5 8.7a4.7 4.7 0 0 1 0 6.6M18.3 6a8.5 8.5 0 0 1 0 12"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SoundOffIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <path d="M3 9v6h4l5 4V5L7 9H3Z" fill="currentColor" />
      <path
        d="M4.3 3 21 19.7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
```

- [ ] **Step 2: Replace the text button with the icon button**

In `frontend/src/pages/RadioPage.tsx`, inside the `.controls` div, replace:

```tsx
              <button
                type="button"
                className="tune-in"
                onClick={player.toggleMute}
              >
                {player.muted ? "UNMUTE" : "MUTE"}
              </button>
```

with:

```tsx
              <button
                type="button"
                className="mute-btn"
                onClick={player.toggleMute}
                aria-label={player.muted ? "Unmute" : "Mute"}
                title={player.muted ? "Unmute" : "Mute"}
              >
                {player.muted ? <SoundOffIcon /> : <SoundOnIcon />}
              </button>
```

The icon reflects current state (slashed speaker while muted, waves while
audible); the aria-label/title reflect the action the click performs.

- [ ] **Step 3: Run the tests to verify they pass**

Run (in `frontend/`): `npm run test -- RadioPage.dom`
Expected: PASS (4 tests).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx
git commit -m "feat: replace text mute button with icon-only button"
```

## Task 3: Style `.mute-btn` and final verification

**Files:**
- Modify: `frontend/src/styles/vintage.css:486` (after `.controls button.tune-in:hover`)
- Modify: `docs/changelog.md` (new entry at top)

- [ ] **Step 1: Add the `.mute-btn` rules**

In `frontend/src/styles/vintage.css`, immediately after the
`.controls button.tune-in:hover` block (line 486), insert:

```css
.controls button.mute-btn {
  min-width: 44px;
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 50%;
  background: var(--amber);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.controls button.mute-btn:hover {
  background: var(--amber-strong);
}

.controls button.mute-btn svg {
  pointer-events: none;
}
```

Notes:
- `min-width: 44px` in this rule overrides the `min-width: 88px` that the
  ≤600px media query applies to `.controls button` (higher specificity),
  which is what fixes the mobile overlap.
- Color stays `var(--ink)` on `var(--amber)` via `.controls button`,
  matching `.tune-in`; reduced-motion and hover-transition rules from
  `.controls button` apply automatically.

- [ ] **Step 2: Run the full test suite and typecheck**

Run (in `frontend/`): `npm run test`
Expected: all tests PASS.

Run (in `frontend/`): `npm run typecheck`
Expected: clean, no errors.

- [ ] **Step 3: Add the changelog entry**

In `docs/changelog.md`, insert directly below the header paragraph (line 5)
and above the `## 2026-10-08 — Basic SEO` heading:

```markdown
## 2026-10-08 — Icon-only mute/unmute button

- Replaced the text mute control (`UNMUTE`/`MUTE`) with a compact 44x44px
  circular icon button so it no longer overlaps the volume slider on mobile.
  The inline SVG icon reflects state (slashed speaker while muted, waves
  while audible); `aria-label`/`title` reflect the action ("Unmute"/"Mute").
  New `.mute-btn` styles in `vintage.css`; `min-width: 44px` overrides the
  mobile `min-width: 88px` on `.controls button`.
- Files touched:
  - `frontend/src/pages/RadioPage.tsx`
  - `frontend/src/pages/RadioPage.dom.test.tsx`
  - `frontend/src/styles/vintage.css`
  - `docs/changelog.md` (docs)
- **Container restart required (frontend source changed):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm run test` all passed; `npm run typecheck` clean.

```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/vintage.css docs/changelog.md
git commit -m "feat: style circular mute button and log changelog"
```

## Deployment note

After implementation, `frontend/src/**` changed, so only the `frontend`
container needs rebuilding: `docker compose up -d --build frontend`
(source is baked into the image, not bind-mounted). Do this when ready to
deploy; it is not part of the coding tasks above.
