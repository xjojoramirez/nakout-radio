# Edit Brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dotted `Nakout.Radio` brand with plain `Nakout Radio` (no dot, no amber accent) in both the listener and admin headers.

**Architecture:** Two-line JSX text change. No new components, no CSS changes, no API changes. Follows the approved approach A (direct plain-text swap) from `docs/superpowers/specs/2026-10-15-edit-brand-design.md`.

**Tech Stack:** React 18 + TypeScript, Vitest + Testing Library, Vite.

**Spec:** `docs/superpowers/specs/2026-10-15-edit-brand-design.md`

---

### Task 1: Listener header brand text

**Files:**
- Modify: `frontend/src/pages/RadioPage.tsx:33`
- Test: `frontend/src/pages/RadioPage.dom.test.tsx` (append new test)

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/RadioPage.dom.test.tsx`, append a new test inside the top-level `describe("RadioPage", ...)` block:

```tsx
  it("renders the brand as plain Nakout Radio (no dot)", () => {
    render(<RadioPage />);
    const brand = document.querySelector(".radio-top .brand");
    expect(brand).not.toBeNull();
    expect(brand?.textContent).toBe("Nakout Radio");
    expect(brand?.querySelector("span")).toBeNull();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/RadioPage.dom.test.tsx`
Expected: FAIL — `brand?.textContent` is `"Nakout.Radio"` (or `span` is found), assertion fails.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/pages/RadioPage.tsx:33`, change:

```tsx
        <div className="brand">
          Nakout<span>.</span>Radio
        </div>
```

to:

```tsx
        <div className="brand">Nakout Radio</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/RadioPage.dom.test.tsx`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx
git commit -m "fix: plain Nakout Radio brand on listener header (issue #15)" --author="Jojo Ramirez <31147978+xjojoramirez@users.noreply.github.com>"
```

---

### Task 2: Admin header brand text

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx:183`
- Test: `frontend/src/pages/AdminPage.dom.test.tsx` (update existing brand test)

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/AdminPage.dom.test.tsx:101-110`, replace the existing brand test:

```tsx
  it("renders the brand header", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([]);
    render(<AdminPage />);
    await login();
    expect(screen.getByText(/Nakout/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Back to radio/ }),
    ).toBeInTheDocument();
  });
```

with:

```tsx
  it("renders the brand header", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listGenres.mockResolvedValue([]);
    render(<AdminPage />);
    await login();
    const brand = document.querySelector(".admin-top .brand");
    expect(brand).not.toBeNull();
    expect(brand?.textContent).toBe("Nakout Radio Admin");
    expect(brand?.querySelector("span")).toBeNull();
    expect(
      screen.getByRole("link", { name: /Back to radio/ }),
    ).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/AdminPage.dom.test.tsx`
Expected: FAIL — `brand?.textContent` is `"Nakout.Radio Admin"` (or `span` found), assertion fails.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/pages/AdminPage.tsx:183`, change:

```tsx
          Nakout<span>.</span>Radio <small>Admin</small>
```

to:

```tsx
          Nakout Radio <small>Admin</small>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/AdminPage.dom.test.tsx`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx frontend/src/pages/AdminPage.dom.test.tsx
git commit -m "fix: plain Nakout Radio brand on admin header (issue #15)" --author="Jojo Ramirez <31147978+xjojoramirez@users.noreply.github.com>"
```

---

### Task 3: Changelog + verification

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Add changelog entry**

In `docs/changelog.md`, immediately after the `# Changelog` header block (before the first `## 2026-10-15` entry), insert:

```markdown
## 2026-10-15 — plain "Nakout Radio" brand, no dot (issue #15)

The listener and admin headers rendered the brand as `Nakout<span>.</span>Radio`
with an amber dot. Changed both to plain `Nakout Radio` text (admin keeps its
`<small>Admin</small>` suffix). No CSS changes; the now-unused `.brand span`
rule in `vintage.css` is left in place.

- Files touched:
  - `frontend/src/pages/RadioPage.tsx`
  - `frontend/src/pages/AdminPage.tsx`
  - `frontend/src/pages/RadioPage.dom.test.tsx`
  - `frontend/src/pages/AdminPage.dom.test.tsx`
  - `docs/changelog.md` (docs)
- **Container restart required?** Yes — `frontend` only:
  `docker compose up -d --build frontend`
- Verification: `npx vitest run` (both page test files pass);
  `grep -r "Nakout<span>" frontend/src` returns nothing; `npx tsc --noEmit`
  clean.
```

- [ ] **Step 2: Full verification**

Run from repo root:

```bash
cd frontend && npx vitest run && npx tsc --noEmit && cd ..
git grep -n "Nakout<span>" -- frontend/src && echo "FOUND" || echo "clean"
```

Expected: all tests pass, typecheck clean, `clean`.

- [ ] **Step 3: Commit + changelog per AGENTS.md**

```bash
git add docs/changelog.md
git commit -m "docs: changelog for brand text change (issue #15)" --author="Jojo Ramirez <31147978+xjojoramirez@users.noreply.github.com>"
```

Note: `docs/changelog.md` is modified in Task 3 Step 1, which is fine since Tasks 1–2 already committed the code+test changes.

---

## Self-Review

- **Spec coverage:** Both in-scope files (RadioPage, AdminPage) covered; out-of-scope items confirmed already correct; existing test updated; changelog per AGENTS.md. No gaps.
- **Placeholder scan:** No TBD/TODO; every step has exact code/commands.
- **Type consistency:** `brand?.textContent` / `querySelector("span")` used consistently in both tasks; test helper `login()` is defined in the existing AdminPage test file.
