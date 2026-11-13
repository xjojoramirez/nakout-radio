# Library track details: show the Nakout playlist — design

Date: 2026-11-13
Status: approved, implementation pending

## Problem

When editing a track in the Studio library, the details modal shows the track's
editorial genre tags (`jazz`, `modal jazz`, ...) but not where the track sits on
Nakout. The operator cannot tell which Nakout queue will actually air it.

"Nakout playlist" here means the genre queue used by **Now Playing**, not the
YouTube source playlist. Each Nakout genre (Jazz, OPM, ...) builds its Now
Playing queue from one or more YouTube source playlists. A track can therefore
belong to several YouTube playlists while being on one Nakout playlist, or on
several Nakout playlists (genres).

## Goal

Inside the track-details modal, show a read-only **Nakout playlist** section
listing the Nakout genre queue(s) that currently include the track, with the
genre colour. The editorial **Genres** field keeps its original meaning and
values.

## Non-goals

- Showing YouTube playlist labels, URLs or IDs in this section.
- Changing how tracks are assigned to genres or source playlists.
- Editing Nakout playlist membership from the modal. Membership stays managed
  through the Playlists panel and YouTube sync.
- Changing the library list row.
- A new named playlist entity separate from genres.

## Design

### API

Add a small response model to `backend/app/schemas.py`:

```python
class NakoutPlaylistOut(BaseModel):
    slug: str
    name: str
    color: str = ""
```

Add `nakout_playlists: list[NakoutPlaylistOut]` to `TrackDetailOut` only. The
public `TrackDetailBase` response stays unchanged.

The list is deduplicated by genre, ordered by `Genre.sort_order` then
`Genre.name`, and uses an empty colour when the genre has none.

### Backend

In `track_details.admin_detail()`, query the distinct genres reachable from the
track's cached rows:

```text
TrackCache → Playlist → Genre
where TrackCache.youtube_video_id = video_id
```

Several source playlists in the same genre produce one entry. A standalone
track produces an empty list. This is derived read-only data: no migration, no
new table, and `TrackDetailIn` is unchanged so the editor never writes
memberships.

### Frontend

- Add the membership type to `frontend/src/types.ts` and the new field to
  `StudioTrackDetail`.
- In `TrackDetailEditor`, add a read-only fieldset **Nakout playlist** at the
  top of the form, before **Facts**.
- Each row shows the genre colour dot and the genre name. A small hint reads
  “Genre queue used in Now Playing”.
- With no memberships, show “Not on a Nakout playlist.”
- The existing **Genres** input remains unchanged and still edits the track's
  original editorial genres.
- Add a few `te-nakout-*` rules in `vintage.css`, matching the existing editor
  fieldset styling. No inputs and no save-payload changes.

## Testing

Backend (`backend/tests/test_track_details.py`):

- two source playlists under one genre collapse to one Nakout playlist entry;
- memberships across two genres return both, sorted by genre order;
- a standalone track returns an empty list.

Frontend (`frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx`):

- the modal renders the Nakout playlist names with the genre colour;
- the empty state appears for a track with no membership;
- the editorial Genres input still shows the original track genres.

## Rollout

- Backend and frontend both change, so rebuild both containers:
  `docker compose up -d --build backend frontend`.
- Add a `docs/changelog.md` entry with files touched, restart command and test
  results.
- Open a pull request; `main` is protected.
