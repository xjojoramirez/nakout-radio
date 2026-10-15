# Edit Brand — Design Specification

Date: 2026-10-15
Issue: #15 — Edit Brand ("Don't put Nakout.Radio, just Nakout Radio, no dot.")
Approach: A — Direct plain-text swap (approved)

## Goal

Replace the dotted `Nakout.Radio` brand with plain `Nakout Radio` (no dot, no amber accent) in both UI headers.

## Scope

In scope:
- `frontend/src/pages/RadioPage.tsx:33` — listener header:
  `Nakout<span>.</span>Radio` → `Nakout Radio`
- `frontend/src/pages/AdminPage.tsx:183` — admin header:
  `Nakout<span>.</span>Radio <small>Admin</small>` → `Nakout Radio <small>Admin</small>`

Out of scope (already correct):
- `frontend/index.html`, `frontend/vite.config.ts` (PWA/manifest), `backend/app/main.py` title, fallback strings (`"Nakout Radio"`), docs — all already use `Nakout Radio`.

## Decisions

- Both pages change (listener + admin, admin keeps `<small>Admin</small>` suffix).
- Plain text: remove the `<span>.</span>` entirely; no replacement amber styling.
- No CSS changes. The `.brand span { color: var(--amber); }` rule in `frontend/src/styles/vintage.css:1614` becomes unused but is left in place (harmless, avoids touching shared stylesheet for a text change).

## Testing

- Existing `frontend/src/pages/AdminPage.dom.test.tsx:106` asserts `/Nakout/` — still passes, no test change needed.
- Verification: `grep` for `Nakout<span>` under `frontend/src` returns nothing; run frontend typecheck/tests.

## Alternatives considered

- B. Keep span hook for future accent — rejected: dead markup for an explicit plain-text request.
- C. Extract shared `<Brand/>` component — rejected as overkill (YAGNI) for a 2-line text change.
