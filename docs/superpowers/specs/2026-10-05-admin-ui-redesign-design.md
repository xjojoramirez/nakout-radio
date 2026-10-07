# Nakout Radio — Admin UI Redesign: Design Specification

Date: 2026-10-05
Status: Approved for planning

## 1. Overview

The admin page is a single cream card containing five stacked sections
(Station, Playlist, Browse YouTube, Schedule, Maintenance). Everything is
visible at once, so the page is long and it is hard to find a specific task.

This redesign splits the admin into **tabs**, one focused task per tab, and
adds two missing views: a list of every playlist that has been added, and a
live "what's playing" status. The existing create/sync behaviors are preserved;
only their arrangement and the two new views change.

## 2. Goals

- Replace the single long card with a tabbed layout: one panel visible at a time.
- Show every added playlist with its station, track count, and controls to
  **Refresh** or **Remove** it.
- Show what is currently playing (station, track, artist, thumbnail, source) and
  keep it up to date while the tab is open.
- Keep all current admin capabilities: create station, add playlist by URL,
  browse channel playlists, add schedule slot, sync all.

## 3. Non-Goals

- No playback controls (next/prev/shuffle) in admin; the radio page owns those.
- No editing of stations, playlists, or slots (create/delete only, plus playlist
  refresh).
- No listing of schedule slots in the admin UI.
- No change to the database schema or migrations.
- No changes to the public radio page.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Layout | Top tab bar; one panel at a time |
| Tabs | Now Playing, Playlists, Stations, Schedule |
| Added playlists | Row per playlist with station, track count, Refresh, Remove |
| Now Playing | Live read-only status; no playback controls |
| Live updates | Re-fetch on the same per-minute cadence as the radio page |
| Current source of truth | `GET /api/schedule/now` (scheduled station and its first track) |

## 5. Architecture

No new services. Changes are confined to the existing FastAPI backend and the
React admin page.

```
backend/
├─ app/
│  ├─ schemas.py           # + PlaylistOut
│  └─ routers/admin.py     # + GET /playlists, DELETE /playlists/{id}
└─ tests/test_admin.py     # + tests for the new endpoints

frontend/src/
├─ types.ts                # + AddedPlaylist
├─ api/client.ts           # + listPlaylists, deletePlaylist, refreshPlaylist
├─ pages/AdminPage.tsx     # thin shell: auth, notices, tabs
└─ components/admin/
   ├─ Tabs.tsx             # tab bar + panels
   ├─ NowPlayingPanel.tsx  # live status + Sync all
   ├─ PlaylistsPanel.tsx   # added playlists, add-by-URL, browse channel
   ├─ StationsPanel.tsx    # create station + station list
   └─ SchedulePanel.tsx    # add weekly slot
```

`AdminPage` keeps ownership of auth (login/logout), the shared error/notice
banners, and the station list fetched on login. Panels receive the props they
need (stations, callbacks) so each can be understood and tested on its own.

## 6. Data Model

No schema changes. The new playlist list is derived from the existing `Playlist`
and `TrackCache` tables:

- `Playlist.id`, `Playlist.station_id`, `Playlist.youtube_playlist_id`,
  `Playlist.label`.
- Track count = number of `TrackCache` rows for that playlist.
- Station name = the joined `Station.name`.

## 7. Backend

All endpoints require admin auth (`dependencies=[Depends(require_admin)]`).

### `app/schemas.py`

- `PlaylistOut`:
  - `id: int`
  - `station_id: int`
  - `station_name: str`
  - `youtube_playlist_id: str`
  - `label: str`
  - `track_count: int`

### `app/routers/admin.py`

- `GET /api/admin/playlists` → `list[PlaylistOut]`, ordered by station then
  playlist id. Loads all `Playlist` rows and their `Station` names, and counts
  `TrackCache` rows per playlist in a single grouped query.
- `DELETE /api/admin/playlists/{playlist_id}` → `{"status": "deleted"}`.
  Deletes the playlist's `TrackCache` rows, then the playlist. Returns `404`
  when the playlist does not exist. (Mirrors the existing station-delete
  cascade logic.)

Existing endpoints are unchanged: `POST /api/admin/playlists`,
`POST /api/admin/playlists/{id}/refresh`, `POST /api/admin/sync`,
`POST /api/admin/slots`, and the `youtube/*` endpoints.

## 8. Frontend

### Types and client

- `types.ts`: `AddedPlaylist { id: number; station_id: number;
  station_name: string; youtube_playlist_id: string; label: string;
  track_count: number }`.
- `api/client.ts`:
  - `listPlaylists()` → `GET /admin/playlists`.
  - `refreshPlaylist(id)` → `POST /admin/playlists/{id}/refresh`.
  - `deletePlaylist(id)` → `DELETE /admin/playlists/{id}`.

### `pages/AdminPage.tsx`

- Keeps login/logout, the error and notice banners, the station list, and the
  active-tab state.
- Renders the tab bar and the active panel only.
- Refreshes the station list after any action that changes stations/playlists.

### `components/admin/Tabs.tsx`

- Renders a `<nav role="tablist">` of buttons and one `<section role="tabpanel">`
  for the active tab. Uses `aria-selected` on the active button and filters the
  children/panels accordingly. Keeps the markup simple; no routing.

### `components/admin/NowPlayingPanel.tsx`

- Props: `onNotice`, `onError` (for the Sync all result).
- Calls `api.scheduleNow()` on mount and then on the same cadence as
  `useSchedule` (re-fetch at the next minute boundary).
- Shows the station name, track title, artist, thumbnail, and source label
  (schedule/default/none). Shows an empty state when nothing is scheduled.
- Contains the **Sync all playlists** button and reports its result via the
  parent notice callback.

### `components/admin/PlaylistsPanel.tsx`

- Props: `stations`, `onStationsChanged`, `onNotice`, `onError`.
- **Added playlists**: calls `api.listPlaylists()` on mount and after changes.
  Each row shows station name, playlist ID, label (if any), and track count,
  with **Refresh** and **Remove** buttons. Refresh calls `refreshPlaylist`;
  Remove calls `deletePlaylist` (after a confirmation) and reloads the list.
- **Add by URL**: station dropdown + URL input + **Add playlist**, calling
  `createPlaylist(Number(stationId), url, "")` and showing the existing
  "synced N tracks" / "sync failed" notices.
- **Browse channel**: the existing save-channel input, refresh, and channel
  playlist list with per-row station picker and **Add**, reusing the existing
  API calls. Playlists already added show an "Added" badge.

### `components/admin/StationsPanel.tsx`

- Props: `stations`, `onStationsChanged`, `onNotice`, `onError`.
- Name + slug inputs and **Add station**, then a list of existing stations with
  their track counts.

### `components/admin/SchedulePanel.tsx`

- Props: `stations`, `onNotice`, `onError`.
- Station dropdown, day toggles, start/end inputs, and **Add slot**.

## 9. Data Flow

1. **Login.** `AdminPage` authenticates, fetches stations, loads the saved
   channel, and renders the default tab (Now Playing).
2. **Now Playing.** The panel polls `schedule/now` each minute and re-renders.
3. **Added playlists.** The Playlists panel fetches `GET /admin/playlists`; a
   Refresh/Remove action mutates the server, then re-fetches the list and
   signals `onStationsChanged` so station counts stay current.
4. **Add playlist.** Any add path calls `POST /admin/playlists`, reports the
   result, then reloads the added-playlist list and stations.
5. **Sync all.** The Now Playing panel calls `POST /admin/sync` and reports a
   summary.

## 10. Error Handling

- **Unauthenticated / expired session:** the existing login flow is unchanged;
  an `ApiError` shows in the banner.
- **List/refresh/delete failures:** the panel shows the API message via
  `onError`; already-loaded rows stay visible.
- **YouTube fetch failure when loading added playlists:** not applicable (the
  list is database-only); failures show the generic API message.
- **Refresh failure:** `POST /playlists/{id}/refresh` returns `502` on YouTube
  failure; the UI shows the message and leaves the row in place.
- **Remove:** confirmed before the `DELETE` call; the list and station counts
  reload afterward.
- **Nothing playing:** Now Playing shows a "Nothing scheduled" empty state.

## 11. Testing Strategy

- **Backend (`pytest`, FastAPI `TestClient`):**
  - `GET /api/admin/playlists`: requires auth; returns station name and correct
    per-playlist track counts; ordered as specified.
  - `DELETE /api/admin/playlists/{id}`: removes the playlist and its
    `TrackCache` rows; `404` for unknown ids.
- **Frontend (`Vitest` + Testing Library):**
  - `api/client.test.ts`: the three new methods call the expected paths/verbs.
  - `AdminPage.dom.test.tsx`: after login the tab bar renders and switching
    tabs shows the matching panel; the Playlists panel renders fetched rows and
    Refresh/Remove call the right client methods; Now Playing renders the
    `scheduleNow` result.

## 12. Migration

None. No schema or configuration changes.

## 13. Configuration

No new environment variables. Uses the existing `YT_API_KEY` and settings.
