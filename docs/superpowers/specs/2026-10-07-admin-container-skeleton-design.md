# Admin Container Stability + Loading Skeletons — Design

Date: 2026-10-07
Status: Approved

## Problem

Two visible rough edges in the admin UI:

1. The `.admin` container has no stable height, so it collapses and jumps when panels switch or content loads (layout shift between short and tall panels).
2. There is no loading state:
   - While `api.session()` checks on mount, the login form flashes even for users with valid sessions (`AdminPage.tsx:34`).
   - After login, panels render against an empty `genres` array before the first `refreshGenres()` resolves, so empty-looking content flashes before real data arrives.

## Goal

- A stable-height admin container.
- Vintage-themed skeleton placeholders in the panel area while content is not yet loaded.
- No login-form flash during the session check.

## Approach

**Approach A (chosen): a shared skeleton primitive plus phase gating in `AdminPage`.**
Skeletons render at the container level while `genres` is not yet loaded; panels themselves are untouched. A per-panel internal loading approach (B) was rejected as too invasive for the benefit; CSS-only shimmer (C) was rejected because "loading" and "empty" are indistinguishable without a flag.

## Components

### 1. `Skeleton.tsx` — `frontend/src/components/admin/Skeleton.tsx`

New component exporting:

- `<Skeleton variant="title" | "field" | "row" />` — single shimmer block.
- `SkeletonForm` — a stack of field blocks (`count` prop).
- `SkeletonList` — row blocks (`count` prop).

All skeleton output is `aria-hidden`. Variants map to panels like this:

| Panel | Skeleton shown in the panel area while genres not loaded |
|---|---|
| Now Playing | Section-title block + compact list rows + one field block |
| Playlists | Fields block + list rows |
| Genres | `SkeletonForm` + `SkeletonList` |
| Schedule | `SkeletonForm` (time pair + days shape) + list |

The admin page header, tabs, and log-out button render immediately — only panel content is skeletonized.

### 2. `AdminPage.tsx` — phase state machine

Replace the implicit flow with an explicit `phase` state:
`"checking" | "login" | "loading" | "ready"` (tab/error/notice state unchanged).

- `checking` — minimal skeleton card; login form is NOT shown. Entered on mount while `api.session()` is pending.
- `login` — existing login form, unchanged.
- `loading` — after session success, before `refreshGenres()` resolves.
- `ready` — real panels render.

`refreshGenres()` resolving (even to an empty list or caught error) moves the page to `ready`; empty genres is a legitimate ready state, matching existing behavior at `AdminPage.tsx:26`.

### 3. CSS — `vintage.css`

- `.admin { min-height: 480px; }` for stable container height; the existing `@media (max-width: 560px)` block (`vintage.css:931`) keeps mobile compact.
- `.skeleton` blocks: `--cream-soft` background, matching `--radius`, gradient shimmer animation, corners rounded per variant.
- `prefers-reduced-motion` disables the shimmer (pattern exists at `vintage.css:949`).
- Panel wrapper gets `aria-busy` while skeletons are shown.

## Error handling

- Session check failure → `login` phase (unchanged behavior).
- Genre load failure after login → resolves to `ready` with empty genres; error/notice banner paths unchanged. Skeletons never mask errors.

## Testing — `AdminPage.dom.test.tsx`

New tests:

- Shows a skeleton (not the login form) while the session check is pending.
- Restored session eventually reaches the tabs (extends the existing restore test).
- Pending `listGenres` shows skeleton in the panel area, then the real panel once it resolves.

Existing tests should pass largely unchanged since final states are identical; update any that depend on the login form flashing during session checks.

## Out of scope

- Per-panel internal skeleton loading (e.g., NowPlayingPanel track list, which already has its own `loading` state).
- Any backend or API changes.
