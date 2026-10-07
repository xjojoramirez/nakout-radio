# Schedule slot editor UI fix — design

Date: 2026-10-07

## Problem

In `frontend/src/components/admin/SchedulePanel.tsx`, the inline edit form
(genre select, day pills, start/end inputs, Save/Cancel) is rendered inside a
`.genre-admin-list li`, which is styled as a single horizontal flex row
(`display: flex; align-items: center`). The whole edit form is therefore
squeezed onto one cramped line. The Add form puts the "Add slot" button into
`.form-grid` as a stretched grid column, and time entry uses plain text inputs,
which is error-prone especially on mobile.

## Design (approved by user)

Direction: in-place edit card (over modal editor and reuse-top-form).

1. **Slot rows (list view)**: unchanged structure, smarter day summaries
   (`Every day`, `Weekdays`, `Weekends` instead of long comma lists).
2. **Edit card**: the row becomes class `slot-editing`, rendered as a stacked
   vertical card with an amber-tinted highlight:
   - Header line "Editing <genre name>".
   - Genre select, day pills, Start/End stacked; Start/End use
     `type="time"` (emits exactly the `HH:MM` format the backend validates).
   - Save/Cancel in an actions row aligned right; mobile media query already
     turns `.row-actions` into full-width buttons.
   - Keep the existing aria-labels (`Edit slot genre/start/end/Wed`, …) so
     dom tests keep passing.
3. **Add form**: restructured to mirror the edit card: genre select, day
   pills, `time-pair` Start/End grid, then its own actions row containing the
   Add slot button (no longer a stretched grid column). Same `type="time"`.

## Files

- `frontend/src/components/admin/SchedulePanel.tsx`
- `frontend/src/styles/vintage.css`

`.form-grid` remains in use by `GenresPanel.tsx` and is not restyled globally.

## Verification

`npm test` (vitest dom tests incl. AdminPage schedule edit flow),
`npm run typecheck`, `npm run lint` if present, in `frontend/`.
Container: `docker compose up -d --build frontend` required after change.
