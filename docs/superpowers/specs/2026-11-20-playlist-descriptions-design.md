# Nakout playlist descriptions — design

Date: 2026-11-20
Status: approved

## Problem

Listeners see Nakout playlist names (genres such as Jazz, OPM or Emo Night) in
the live "now playing" area and in Today's schedule, but the names carry no
context. A listener cannot tell what a playlist is about, and the radio page
offers no way to inspect one.

## Terminology

A **Nakout playlist** is the genre queue used by Now Playing, not a YouTube
source playlist. One genre can be fed by several YouTube playlists, so all
listener-facing copy and data live on `Genre`.

## Goal

Give every genre an optional editorial description and let listeners open an
**About this playlist** modal from:

- the live `Genre · live now` kicker,
- the genre shown in the player dock ("On the decks"),
- every row in Today's schedule.

The modal shows the description plus five automatically chosen top artists.
It deliberately shows no track list.

## Non-goals

- A public playlist browsing page.
- Descriptions per YouTube source playlist.
- Showing the queue or any track list in the modal.
- Manually curated top-artist lists.
- Editing descriptions from the listener page.

## Data model

Add to `Genre` (`backend/app/models.py`):

```python
description: str = ""
```

Alembic migration adds a non-null `description` column with server default `""`
so existing rows stay valid. The column is plain text; the 500-character limit
is enforced by the API and the Studio form, not by the database.

## Studio

### API

- `GenreIn` and `GenreUpdate` (`backend/app/routers/admin.py`) gain
  `description` with `max_length=500`. Both use a non-optional `str = ""`:
  an omitted update field stays unchanged via `exclude_unset`, `""` clears
  the text, and an explicit `null` is a 422 rather than a NULL write.
- `GenreOut` (`backend/app/schemas.py`) gains `description: str = ""`.

### UI

In `frontend/src/components/admin/GenresPanel.tsx`:

- The **New genre** form gets a three-row **Description** textarea with
  `maxLength={500}` and the hint "Shown to listeners when they open this
  playlist."
- The edit form gets the same textarea, prefilled from the genre.
- Description is saved through the existing create/update calls.
- A genre card shows the description as a two-line clamped preview when it is
  not empty.
- `frontend/src/types.ts` adds `description` to `Genre`; `api.createGenre` and
  `api.updateGenre` accept it.

## Public API

- `SlotTodayOut` gains `genre_slug: str` so a schedule row can request its
  playlist. `schedule_today` fills it from the genre map it already loads.
- `GenreDetail` gains `top_artists: list[str] = []`.
- `GET /api/genres/{slug}` returns the genre, its description and its top
  artists. The endpoint already exists and is currently unused; this gives it
  a real consumer instead of adding another route.

### Top artists rule

Use the genre's deduplicated cached tracks (`tracks_for_genre`, which already
keeps one row per video across source playlists):

1. Ignore tracks whose artist is empty after trimming.
2. Count tracks per artist.
3. Sort by count descending, then artist name ascending (case-insensitive).
4. Return the first five display names.

No extra table and no editor for this list; it follows playlist syncs.

## Listener experience

`frontend/src/pages/RadioPage.tsx`:

- The live kicker becomes a button when a genre is on air.
- The dock genre becomes a button.
- Each Today's schedule row becomes a button inside its `li` (the `li` keeps
  the `now` highlight).
- All three open the same modal with the clicked genre's slug.
- The modal fetches `GET /api/genres/{slug}` on open. It has loading, error and
  retry states so a failed request never leaves an empty card.

New `frontend/src/components/PlaylistAboutDialog.tsx`:

- Accessible dialog (`role="dialog"`, `aria-modal`, labelled by the playlist
  name), closed by Escape, overlay click and a Close button.
- Header: genre colour dot and name.
- Description paragraph, preserving line breaks. Empty state: "No description
  yet."
- "Top artists in this playlist" list of up to five names, hidden when none.
- No track list.

`frontend/src/styles/vintage.css` gets focus/hover styles for the three
clickable entry points and the modal content, reusing the existing
`.modal-overlay` / `.modal-card` foundation. Schedule and dock text must not
shift when they become buttons.

## Testing

Backend:

- `test_genres.py`: the public detail response includes the description and the
  top five artists, ordered by count then name; blank artists are ignored;
  duplicate videos across playlists do not inflate a count.
- `test_admin.py`: create and update persist a description, update without the
  field leaves it unchanged, and `""` clears it.
- `test_schedule_today.py`: slots include `genre_slug`.
- A migration test proves existing genres gain an empty description.

Frontend:

- `GenresPanel.dom.test.tsx`: the new form sends a description, the edit form
  prefills and saves it, and the card shows the preview.
- `RadioPage.dom.test.tsx`: clicking the live kicker and a schedule row opens
  the modal, shows the description and top artists, never renders a track
  list, and handles the empty description and request failure.
- A new `PlaylistAboutDialog.dom.test.tsx` covers Escape/overlay/Close.

## Rollout

- Backend and frontend both change: rebuild both containers with
  `docker compose up -d --build backend frontend`.
- Add a `docs/changelog.md` entry with files touched, restart command and test
  results.
- Open a pull request; `main` is protected. Descriptions are entered in Studio
  after deploy, so the modal shows "No description yet." until they are filled
  in.
