# Track text ellipsis (issue #5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Long track titles/artists in the now-playing hero truncate with an ellipsis (2-line title clamp, 1-line artist) on mobile and desktop, with the full text exposed as a `title` tooltip.

**Architecture:** CSS-only truncation with two small `title` attributes in `RadioPage.tsx`. No JS/measurement.

**Tech Stack:** React 18, TypeScript, Vitest + Testing Library (jsdom), plain CSS (`frontend/src/styles/vintage.css`).

**Spec:** `docs/superpowers/specs/2026-10-14-track-text-ellipsis-design.md`

---

### Task 1: Full-text tooltips on the now-playing hero

**Files:**
- Test: `frontend/src/pages/RadioPage.dom.test.tsx`
- Modify: `frontend/src/pages/RadioPage.tsx:93-96`

- [ ] **Step 1: Write the failing test**

Append inside the `describe("RadioPage", ...)` block in
`frontend/src/pages/RadioPage.dom.test.tsx`:

```tsx
it("exposes the full track title and artist for truncated hero text", async () => {
  const longTitle =
    "Every Grain Of Sand (Live At The Warfield 1980 Remastered Deluxe Edition)";
  const longArtist = "The Traveling Wilburys Tribute Ensemble Orchestra";
  mocked.now.mockResolvedValue({
    genre: {
      id: 1,
      name: "Morning",
      slug: "morning",
      is_default: true,
      track_count: 1,
    },
    track: { ...track("long"), title: longTitle, artist: longArtist },
    offset_seconds: 0,
    server_time: "2026-01-01T00:00:00+00:00",
    source: "schedule",
  });
  render(<RadioPage />);
  const heading = await screen.findByRole("heading", { name: longTitle });
  expect(heading).toHaveAttribute("title", longTitle);
  expect(screen.getByText(longArtist)).toHaveAttribute("title", longArtist);
});
```

- [ ] **Step 2: Run it, expect RED**

Run from `frontend/`:

```
npm test -- src/pages/RadioPage.dom.test.tsx
```

Expected: the new test FAILS — `expected null to be "…"` on the `title`
attribute (attribute not rendered yet); all other tests pass.

- [ ] **Step 3: Implement the tooltips**

In `frontend/src/pages/RadioPage.tsx`, replace:

```tsx
                  <h1 className="np-title">{track?.title ?? "Tune in"}</h1>
                  <div className="np-artist">
                    {track?.artist || "Nakout Radio"}
                  </div>
```

with:

```tsx
                  <h1
                    className="np-title"
                    title={track?.title ?? undefined}
                  >
                    {track?.title ?? "Tune in"}
                  </h1>
                  <div
                    className="np-artist"
                    title={track?.artist || undefined}
                  >
                    {track?.artist || "Nakout Radio"}
                  </div>
```

- [ ] **Step 4: Run it, expect GREEN**

```
npm test -- src/pages/RadioPage.dom.test.tsx
```

Expected: all tests pass, including the new one.

- [ ] **Step 5: Commit**

```
git add frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx
git commit -m "fix: expose full track text as tooltips for truncated hero text (issue #5)"
```

---

### Task 2: CSS truncation for the hero text

**Files:**
- Modify: `frontend/src/styles/vintage.css` (`.np-title` block ~line 1951, `.sleeve` block ~line 1927, `.np-artist` block ~line 1961)

- [ ] **Step 1: Add the two-line title clamp**

In the `.np-title` rule, append (keeping every existing declaration):

```css
  /* Long titles cap at two lines so the hero height stays stable. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
```

- [ ] **Step 2: Add the shrinkable grid cell and artist ellipsis**

After the `.sleeve { … }` rule:

```css
.sleeve > div {
  min-width: 0;
}
```

After the `.np-artist { … }` rule:

```css
.sleeve .np-artist {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

- [ ] **Step 3: Verify tests and typecheck still pass**

```
npm test
npm run typecheck
```

Expected: full suite passes, typecheck clean. (jsdom cannot assert CSS
layout, so these guard regressions only.)

- [ ] **Step 4: Verify the rules land in the built bundle**

```
npm run build
Select-String -Path dist/assets/*.css -Pattern "line-clamp", "sleeve .np-artist" -SimpleMatch
```

Expected: the built CSS matches both patterns.

- [ ] **Step 5: Commit**

```
git add frontend/src/styles/vintage.css
git commit -m "fix: clamp long track title to two lines and ellipsize the artist (issue #5)"
```

---

### Task 3: Changelog

**Files:**
- Modify: `docs/changelog.md` (top, below the intro paragraph)

- [ ] **Step 1: Add the entry (most recent first)**

```markdown
## 2026-10-14 — radio page: long track text truncates with an ellipsis (issue #5)

Long track titles wrapped without a height cap and long artist names could
overflow the now-playing hero on phones and desktop. The title now clamps to
two lines and the artist to one, both with a trailing ellipsis, and the full
text is exposed via `title` tooltips.

- `frontend/src/styles/vintage.css`: two-line clamp on `.np-title`; single-line
  ellipsis on `.sleeve .np-artist`; `.sleeve > div` gets `min-width: 0`.
- `frontend/src/pages/RadioPage.tsx`: `title` attributes on the hero title and
  artist.
- Design/plan: `docs/superpowers/specs/2026-10-14-track-text-ellipsis-design.md`,
  `docs/superpowers/plans/2026-10-14-track-text-ellipsis.md`.
- **Container restart required (frontend):**
  `docker compose up -d --build frontend`, then hard-refresh the browser
  (Ctrl+Shift+R).
- Verification: `npm test` — <N> passed; `npm run typecheck` — clean;
  `npm run build` — bundle contains the clamp/ellipsis rules.
```

Fill in `<N>` with the actual number from Step 3 of Task 2.

- [ ] **Step 2: Commit**

```
git add docs/changelog.md
git commit -m "docs: changelog for the track text ellipsis (issue #5)"
```
