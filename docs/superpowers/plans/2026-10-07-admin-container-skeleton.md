# Admin Container Stability + Loading Skeletons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin container a stable height and show vintage-themed skeletons instead of the login flash / empty-panel flash while content loads.

**Architecture:** A new `Skeleton.tsx` renders `aria-hidden` shimmer building blocks (`Skeleton`, `SkeletonForm`, `SkeletonList`, `PanelSkeleton`). `AdminPage` gets an explicit `phase` state machine (`checking` → `login` → `loading` → `ready`) that gates skeletons. CSS adds `min-height` to `.admin` plus `.skeleton` styles honoring `prefers-reduced-motion`.

**Tech Stack:** React 18 + TypeScript, Vitest + Testing Library (jsdom), single hand-written stylesheet `vintage.css`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-07-admin-container-skeleton-design.md`

---

## Prerequisites

- Working dir for all commands: `frontend/`.
- **The workspace is NOT a git repository** (`git rev-parse` fails). Before the first commit step in Task 1, ask the user whether to run `git init` in `D:\dev\New folder\nakout-radio`. If the user declines, skip all commit steps and note it in the final summary. Do not silently initialize the repo.
- Test commands: `npm run test -- <path>` runs vitest; `npm run typecheck` runs `tsc --noEmit`.

---

### Task 1: Skeleton component

**Files:**
- Create: `frontend/src/components/admin/Skeleton.tsx`
- Test: `frontend/src/components/admin/Skeleton.dom.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/admin/Skeleton.dom.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PanelSkeleton, Skeleton, SkeletonForm, SkeletonList } from "./Skeleton";

describe("Skeleton", () => {
  it("renders an aria-hidden block with the variant class", () => {
    const { container } = render(<Skeleton variant="row" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toHaveAttribute("aria-hidden", "true");
    expect(el).toHaveClass("skeleton", "skeleton-row");
  });

  it("SkeletonForm renders the requested field count", () => {
    const { container } = render(<SkeletonForm count={3} />);
    expect(container.querySelectorAll(".skeleton-field")).toHaveLength(3);
  });

  it("SkeletonList renders the requested row count", () => {
    const { container } = render(<SkeletonList rows={5} />);
    expect(container.querySelectorAll(".skeleton-list li")).toHaveLength(5);
  });

  it("PanelSkeleton hides real text and sizes to the panel", () => {
    const { container } = render(<PanelSkeleton tab="genres" />);
    expect(screen.queryByText(/Genres|Name|Slug/i)).toBeNull();
    expect(
      container.querySelectorAll(".skeleton"),
    ).toHaveLength(7); // title + 2 form fields + 4 list rows
  });

  it("PanelSkeleton renders something for unknown tabs", () => {
    const { container } = render(<PanelSkeleton tab="bogus" />);
    expect(container.querySelector(".admin-panel")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test -- src/components/admin/Skeleton.dom.test.tsx`
Expected: FAIL — "Cannot find module './Skeleton'" (or equivalent resolution error).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/admin/Skeleton.tsx`:

```tsx
interface SkeletonProps {
  variant?: "title" | "field" | "row";
  className?: string;
}

export function Skeleton({ variant, className }: SkeletonProps) {
  const classes = ["skeleton"];
  if (variant) classes.push(`skeleton-${variant}`);
  if (className) classes.push(className);
  return <div aria-hidden="true" className={classes.join(" ")} />;
}

export function SkeletonForm({ count }: { count: number }) {
  return (
    <div className="skeleton-form" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} variant="field" />
      ))}
    </div>
  );
}

export function SkeletonList({ rows }: { rows: number }) {
  return (
    <ul className="skeleton-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i}>
          <Skeleton variant="row" />
        </li>
      ))}
    </ul>
  );
}

function NowSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={1} />
      <SkeletonList rows={5} />
    </section>
  );
}

function PlaylistsSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={3} />
      <SkeletonList rows={4} />
    </section>
  );
}

function GenresSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={2} />
      <SkeletonList rows={4} />
    </section>
  );
}

function ScheduleSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={4} />
      <SkeletonList rows={3} />
    </section>
  );
}

export function PanelSkeleton({ tab }: { tab: string }) {
  switch (tab) {
    case "now":
      return <NowSkeleton />;
    case "playlists":
      return <PlaylistsSkeleton />;
    case "genres":
      return <GenresSkeleton />;
    case "schedule":
      return <ScheduleSkeleton />;
    default:
      return <section className="admin-panel" />;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npm run test -- src/components/admin/Skeleton.dom.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

Ask about `git init` first (see Prerequisites). Then:

```bash
git add frontend/src/components/admin/Skeleton.tsx frontend/src/components/admin/Skeleton.dom.test.tsx
git commit -m "feat(admin): add skeleton loading components"
```

---

### Task 2: Skeleton CSS + stable container height

**Files:**
- Modify: `frontend/src/styles/vintage.css` (admin section, lines ~477–486 and ~931–947)

- [ ] **Step 1: Add `min-height` to `.admin`**

In `vintage.css`, change the `.admin` rule (currently at line 479) to:

```css
.admin {
  width: min(1100px, 96vw);
  min-height: 480px;
  padding: 28px 32px;
  border-radius: var(--radius-lg);
  background: var(--cream);
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(255, 255, 255, 0.25);
}
```

- [ ] **Step 2: Keep mobile compact**

In the existing `@media (max-width: 560px)` block (line 931), update the `.admin` rule to:

```css
  .admin {
    padding: 20px;
    min-height: 360px;
  }
```

- [ ] **Step 3: Add skeleton styles**

Insert after the `.admin` rule from Step 1:

```css
/* Skeleton loading states */

.skeleton {
  border-radius: var(--radius-sm);
  background:
    linear-gradient(
      100deg,
      rgba(59, 36, 23, 0.06) 35%,
      rgba(59, 36, 23, 0.14) 45%,
      rgba(59, 36, 23, 0.06) 55%
    ),
    var(--cream-soft);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s ease-in-out infinite;
}

@keyframes skeleton-shimmer {
  0% {
    background-position: 200% 0;
  }

  100% {
    background-position: -200% 0;
  }
}

.skeleton-title {
  height: 28px;
  width: 180px;
  margin: 14px 0 10px;
}

.skeleton-field {
  height: 66px;
  margin: 8px 0;
}

.skeleton-row {
  height: 46px;
}

.skeleton-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  align-items: end;
  margin: 10px 0 4px;
}

.skeleton-form .skeleton-field {
  height: 42px;
  margin: 0;
}

.skeleton-list {
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.admin-skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 340px;
  margin: 0 auto;
  padding-top: 16px;
}

.admin-skeleton-card .skeleton-title {
  margin: 6px 0 4px;
  width: 120px;
}
```

- [ ] **Step 4: Honor reduced motion**

In the existing `@media (prefers-reduced-motion: reduce)` block (line 949), add:

```css
  .skeleton {
    animation: none;
  }
```

- [ ] **Step 5: Verify build**

Run (from `frontend/`): `npm run typecheck`
Expected: no errors (CSS-only change, but confirms nothing broke).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "feat(admin): skeleton styles and stable admin container height"
```

---

### Task 3: AdminPage phase state machine

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx` (whole file, 184 lines → uses `phase` instead of `authed`)
- Modify: `frontend/src/pages/AdminPage.dom.test.tsx` (login helper + 1 existing test + 2 new tests)

- [ ] **Step 1: Update the login helper in the test file (write failing tests)**

In `frontend/src/pages/AdminPage.dom.test.tsx`, replace the `login()` helper (currently lines 51–57) so it waits out the "checking" phase — with the new state machine the password field is not rendered until the session check rejects:

```tsx
async function login() {
  await screen.findByPlaceholderText("Password");
  fireEvent.change(screen.getByPlaceholderText("Password"), {
    target: { value: "pw" },
  });
  fireEvent.click(screen.getByText("Log in"));
  await screen.findByRole("tab", { name: "Genres" });
}
```

In the test `"shows the API error message on a bad login"` (line 89), change the first interaction to await the input:

```tsx
  it("shows the API error message on a bad login", async () => {
    mocked.login.mockRejectedValue(new ApiError(401, "invalid password"));
    render(<AdminPage />);
    fireEvent.change(await screen.findByPlaceholderText("Password"), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByText("Log in"));
    expect(await screen.findByText("invalid password")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Add the new tests**

Append inside the existing `describe("AdminPage", ...)` block:

```tsx
  it("shows a skeleton card instead of the login form while checking the session", async () => {
    mocked.session.mockReturnValue(new Promise(() => {})); // never resolves
    render(<AdminPage />);
    await waitFor(() =>
      expect(document.querySelector(".admin-skeleton-card")).toBeInTheDocument(),
    );
    expect(screen.queryByPlaceholderText("Password")).not.toBeInTheDocument();
    expect(document.querySelector('[role="tabpanel"]')).toBeNull();
  });

  it("shows panel skeletons while genres load, then the real panel", async () => {
    mocked.session.mockResolvedValue({ status: "ok" });
    let resolveGenres!: () => void;
    mocked.listGenres.mockImplementation(
      () => new Promise<void>((res) => {
        resolveGenres = res;
      }),
    );
    render(<AdminPage />);
    await screen.findByRole("tab", { name: "Now Playing" });
    expect(
      document.querySelector('[role="tabpanel"] .skeleton'),
    ).not.toBeNull();
    resolveGenres([]);
    await waitFor(() =>
      expect(
        document.querySelector('[role="tabpanel"] .skeleton'),
      ).toBeNull(),
    );
  });
```

- [ ] **Step 3: Run test to verify new tests fail**

Run (from `frontend/`): `npm run test -- src/pages/AdminPage.dom.test.tsx`
Expected: FAIL — `.admin-skeleton-card` never appears (today the login form flashes by default) and no skeleton shows during a pending `listGenres`.

- [ ] **Step 4: Rewrite AdminPage.tsx**

Replace the entire content of `frontend/src/pages/AdminPage.tsx` with:

```tsx
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { NowPlayingPanel } from "../components/admin/NowPlayingPanel";
import { PlaylistsPanel } from "../components/admin/PlaylistsPanel";
import { SchedulePanel } from "../components/admin/SchedulePanel";
import { GenresPanel } from "../components/admin/GenresPanel";
import { Tabs, type TabDef } from "../components/admin/Tabs";
import {
  PanelSkeleton,
  Skeleton,
  SkeletonForm,
} from "../components/admin/Skeleton";
import type { Genre } from "../types";
import { messageFor } from "../utils/errors";

const TABS: TabDef[] = [
  { id: "now", label: "Now Playing" },
  { id: "playlists", label: "Playlists" },
  { id: "genres", label: "Genres" },
  { id: "schedule", label: "Schedule" },
];

type Phase = "checking" | "login" | "loading" | "ready";

export function AdminPage() {
  const [phase, setPhase] = useState<Phase>("checking");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [genres, setGenres] = useState<Genre[]>([]);
  const [tab, setTab] = useState("now");

  const refreshGenres = useCallback(async () => {
    try {
      setGenres(await api.listGenres());
    } catch {
      setGenres([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await api.session();
        if (!active) return;
        setPhase("loading");
        await refreshGenres();
        if (!active) return;
        setPhase("ready");
      } catch {
        // no valid session; show the login screen
        if (active) setPhase("login");
      }
    })();
    return () => {
      active = false;
    };
  }, [refreshGenres]);

  const login = async () => {
    try {
      await api.login(password);
      setPhase("loading");
      setError("");
      await refreshGenres();
      setPhase("ready");
    } catch (err) {
      setError(messageFor(err));
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // session may already be gone; ignore
    }
    setPhase("login");
    setGenres([]);
    setPassword("");
    setError("");
    setNotice("");
  };

  const onNotice = (message: string) => {
    setError("");
    setNotice(message);
  };

  const onError = (message: string) => {
    setNotice("");
    setError(message);
  };

  if (phase === "checking") {
    return (
      <div className="admin">
        <div className="admin-skeleton-card admin-skeleton-card-test" aria-busy="true">
          <Skeleton variant="title" />
          <SkeletonForm count={1} />
        </div>
      </div>
    );
  }

  if (phase === "login") {
    return (
      <div className="admin">
        <form
          className="admin-login"
          onSubmit={(e) => {
            e.preventDefault();
            login();
          }}
        >
          <h1>Admin</h1>
          <p className="hint">Sign in to manage genres and playlists.</p>
          <label className="field">
            Password
            <input
              type="password"
              placeholder="Password"
              value={password}
              autoFocus
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary">
            Log in
          </button>
          {error && (
            <p className="error banner" role="alert">
              {error}
            </p>
          )}
          <a className="back-link" href="/">
            &larr; Back to radio
          </a>
        </form>
      </div>
    );
  }

  return (
    <div className="admin">
      <header className="admin-header">
        <h1>Admin</h1>
        <div className="admin-header-actions">
          <a className="back-link" href="/">
            &larr; Back to radio
          </a>
          <button type="button" className="btn btn-secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice banner" aria-live="polite">
          {notice}
        </p>
      )}

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      <div
        id={`panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        aria-busy={phase === "loading"}
      >
        {phase === "loading" ? (
          <PanelSkeleton tab={tab} />
        ) : (
          <>
            {tab === "now" && (
              <NowPlayingPanel
                genres={genres}
                onNotice={onNotice}
                onError={onError}
              />
            )}
            {tab === "playlists" && (
              <PlaylistsPanel
                genres={genres}
                onGenresChanged={refreshGenres}
                onNotice={onNotice}
                onError={onError}
              />
            )}
            {tab === "genres" && (
              <GenresPanel
                genres={genres}
                onGenresChanged={refreshGenres}
                onNotice={onNotice}
                onError={onError}
              />
            )}
            {tab === "schedule" && (
              <SchedulePanel
                genres={genres}
                onNotice={onNotice}
                onError={onError}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
```

Note: the `admin-skeleton-card-test` hook class lets the new test target the card. The wrapping card div also carries `aria-busy="true"`; it contains only `aria-hidden` blocks, so screen readers get nothing.

- [ ] **Step 5: Run the admin test suite to verify it passes**

Run (from `frontend/`): `npm run test -- src/pages/AdminPage.dom.test.tsx`
Expected: PASS — all previous tests plus the 2 new ones. The session-restore test (`AdminPage.dom.test.tsx:79`) now exercises `checking → loading → ready` and still finds the tabs.

- [ ] **Step 6: Run the full test suite and typecheck**

Run (from `frontend/`): `npm run test` and `npm run typecheck`
Expected: PASS — no other suite depends on the removed `authed` state (`grep -r "authed" src` should return nothing).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx frontend/src/pages/AdminPage.dom.test.tsx
git commit -m "feat(admin): phase state machine with session/genre loading skeletons"
```

---

### Task 4: Final verification

- [ ] **Step 1: Full build**

Run (from `frontend/`): `npm run build`
Expected: compiles and bundles without errors.

- [ ] **Step 2: Full test suite**

Run (from `frontend/`): `npm run test`
Expected: all suites PASS.

- [ ] **Step 3: Manual smoke check (optional, user-driven)**

If a dev environment is available: `npm run dev`, open `/admin`, hard-refresh with a live session — the login form must not flash; a skeleton appears briefly, then panels. Switch between tabs while online — container height should not jump.

- [ ] **Step 4: Commit any stragglers / final state**

```bash
git status
```

Expected: only the spec/plan docs may be untracked. Commit them if a repo exists:

```bash
git add docs/superpowers/specs/2026-10-07-admin-container-skeleton-design.md docs/superpowers/plans/2026-10-07-admin-container-skeleton.md
git commit -m "docs: admin container skeleton design and plan"
```
