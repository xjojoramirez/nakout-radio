# Nakout Radio — Admin Live Control & Playlist Management — Design Specification

Date: 2026-10-06
Status: Approved for planning

## 1. Overview

The broadcast is currently deterministic: `broadcast.py` computes the live
track from the time-of-day schedule and a stored anchor. The admin **Now
Playing** tab is read-only. This change gives the admin live control of the one
global broadcast — play a specific track, skip next/previous, take over from
the schedule, and reorder or shuffle a station's play queue. Every action is
immediate and shared: all listeners hear the result.

Because there is a single broadcast, live control cannot be per-listener. It is
an admin-only override that pauses the schedule until released.

## 2. Goals

- Show the selected station's **full track queue** in play order, with the
  current track highlighted and the next few shown as **Up next**.
- Let the admin **play any track now** (immediate cut-over, with a confirmation
  prompt while a song is on air).
- Let the admin **skip Next / Prev** in the queue.
- Let the admin **take over live** (Manual mode) and explicitly return to the
  **schedule (Auto)**.
- Let the admin **reorder** the queue by dragging and **shuffle** it once.
- Persist a **custom per-station order** that survives YouTube playlist
  re-syncs.
- Let the admin **pick which station** to view and control.

## 3. Non-Goals

- No per-listener controls. Listeners still choose only volume/mute.
- No crossfade, no queue-of-requests, no history view.
- No editing of stations, playlists, or schedule slots beyond existing
  create/delete/refresh capabilities.
- No new database tables or schema migrations.
- No changes to the listener `RadioPage` UI.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Live control model | Admin takes over live; action changes what all listeners hear |
| Schedule during override | Fully paused until the admin presses Auto |
| Play-now semantics | Immediate cut-over, with a confirmation prompt while a song plays |
| Music list | Station's full track list, in broadcast order |
| Reorder | Custom per-station order, applied to playback |
| Reorder vs re-sync | Custom order survives playlist refresh/sync |
| Station scope | Panel has a station picker; acting on another station switches live to it |
| Shuffle | One-time action that randomizes the saved order |
| Engine | Manual mode as first-class broadcast state (Approach A) |
| Order storage | JSON list of `youtube_video_id`s in the `Setting` table |

## 5. Architecture

Contained in the backend broadcast module, the admin router, and the admin
frontend panel. The three services (`caddy`, `frontend`, `backend`) are
unchanged.

```
backend/app/
├─ broadcast.py         # manual mode + order-aware snapshots + control functions
├─ routers/
│  ├─ admin.py          # new live-control + order endpoints
│  ├─ stations.py       # ordered_tracks_for_station helper
│  └─ now.py            # unchanged (source may now be "manual")
├─ schemas.py           # request/response models for the new endpoints

frontend/src/
├─ api/client.ts        # new admin API methods
├─ hooks/useBroadcast.ts# source type widened with "manual"
├─ components/admin/
│  └─ NowPlayingPanel.tsx  # rewritten: picker, transport, up-next, queue, shuffle
└─ utils/queue.ts       # reorder(list, from, to) and shuffle(list) helpers
```

## 6. Custom Order Storage

The play order for a station is stored in the existing `Setting` key/value
table:

- Key: `station_order:<station_id>`
- Value: JSON array of `youtube_video_id` strings, in play order.

`sync_playlist` deletes and reinserts all `TrackCache` rows for a playlist, so a
custom order keyed on `TrackCache.id` would not survive. Keying on
`youtube_video_id` survives re-sync with no schema change and no migration.

### 6.1 `ordered_tracks_for_station(session, station_id)`

A helper (in `app/routers/stations.py`) wraps the existing
`tracks_for_station`:

1. Fetch all tracks for the station (existing query, default order).
2. Read the saved order list.
3. Emit tracks in saved order, skipping ids no longer present.
4. Append remaining tracks (new ones) in default order.
5. If there is no saved order, return the default order unchanged.

Default order is the existing `(playlist_id, position, id)`. Duplicate video
ids are resolved to the first unused match; this is a rare edge case and is
documented. `broadcast._snapshot` and the admin endpoints use this helper.

## 7. Manual Mode (Broadcast Engine)

`BroadcastState` gains a `manual: bool` field. `_load` treats a missing field as
`False`, so existing persisted `broadcast_state` values keep working; `_save`
writes it.

### 7.1 `advance()`

`advance()` branches on `state.manual`:

- **Manual** — while `now >= started_at + durations[index]`, advance `index`
  (wrapping to `0`), setting `started_at` to the boundary. The schedule
  (`desired()`) is never consulted.
- **Automatic** — the current behavior is unchanged (schedule switching at
  boundaries, snapshot re-read on wrap).

### 7.2 `source`

`NowState.source` gains the value `"manual"`. `get_current` returns `"manual"`
when the state is in manual mode and still computes `offset` from `started_at`.
The schedule-resolution check is skipped in manual mode.

### 7.3 Control functions

All acquire the existing module lock and persist state.

- `play_now(session, station_id, video_id)` — build a snapshot from the ordered
  track list; if `video_id` is not present return not-found. Set
  `manual=True`, `index` to the track's position, `started_at=now`.
- `skip(session, station_id, direction)` — if the requested station is not the
  live one, start at `0` (next) or the last index (prev); otherwise move `±1`
  with wrap. Sets `manual=True`, `started_at=now`.
- `set_auto(session)` — `manual=False`; re-initialize from the schedule at
  `now` (station resolves as in `_init`, `index=0`, `started_at=now`).
- `set_order(session, station_id, video_ids)` — persist the new order. If the
  station is live and manual, rebuild the snapshot from the new order while
  keeping the currently playing track at its new index and preserving
  `started_at`, so the current song is not interrupted.

The panel reads live `{manual, station, track, offset, source}` from the
existing `GET /api/now`; `source` becomes `"manual"` while overridden, and the
panel derives the current index from the ordered track list.

Shuffle is computed on the client (Fisher–Yates) and saved through
`set_order`, so reorder and shuffle share one backend path.

## 8. API

All endpoints are under `/api/admin` and require `require_admin`.

| Method & path | Body | Purpose |
| --- | --- | --- |
| `GET /api/admin/stations/{id}/tracks` | — | Ordered `TrackOut[]` for a station |
| `POST /api/admin/playback/play` | `{station_id, youtube_video_id}` | Play now |
| `POST /api/admin/playback/next` | `{station_id}` | Next |
| `POST /api/admin/playback/prev` | `{station_id}` | Prev |
| `POST /api/admin/playback/auto` | — | Return to schedule |
| `PUT /api/admin/stations/{id}/order` | `{video_ids: [...]}` | Save order (drag or shuffle) |

`GET /api/now` (listener-facing) is unchanged in shape; `source` may now be
`"manual"`, which is how the admin panel detects that an override is active.

## 9. Frontend

### 9.1 API client

`src/api/client.ts` gains: `stationTracks(id)`,
`play(stationId, videoId)`, `playbackNext(stationId)`,
`playbackPrev(stationId)`, `playbackAuto()`, `setStationOrder(id, videoIds)`.

### 9.2 `NowPlayingPanel` (rewritten)

Three stacked regions:

1. **Header** — station `<select>` (defaults to the live station) and the
   existing "Sync all playlists" button.
2. **On-air card + transport** — thumbnail, title, artist, station, and a source
   badge (`Schedule` / `Default` / `Manual`); **Prev**, **Next**, and **Auto**
   buttons. `Auto` is disabled unless `source === "manual"`.
3. **Queue** — the selected station's ordered tracks. The current track is
   highlighted and badged "On air"; the following ~5 are labeled **Up next**.
   Each row shows a drag handle, art, title/artist, duration, and a **Play**
   action. A **Shuffle** button sits above the list.

### 9.3 Interaction

- **Play now** — if a track is currently on air, confirm with
  `window.confirm('A song is playing — play "<title>" now?')`; on OK call
  `api.play(...)`.
- **Next / Prev / Auto** — call the endpoint, then refresh the broadcast so the
  panel updates immediately.
- **Reorder** — native HTML5 drag-and-drop (no new dependency).
- **Shuffle** — client-side Fisher–Yates over the current order.
- Both reorder and shuffle call `api.setStationOrder(...)` with the new
  `youtube_video_id` order, then refresh.
- Pure helpers `reorder(list, from, to)` and `shuffle(list)` live in
  `src/utils/queue.ts` and are unit-tested directly.

### 9.4 Data flow

The panel holds `stations`, `selectedStationId` (defaults to the live station
from `useBroadcast`), and `tracks` (refetched on station change and after
mutations). `useBroadcast` already polls `/api/now` every 5 seconds; its
`source` type is widened to include `"manual"`, which drives the badge and the
Auto button. `RadioPage` and the listener hooks are untouched.

### 9.5 Styling

Additions in `vintage.css` for queue rows, the drag handle, source badges, and
transport buttons, matching the existing retro look.

## 10. Error Handling

| Case | Behavior |
| --- | --- |
| Play/next/prev on an empty station | 400; panel surfaces the message via `onError` |
| Video removed between list load and play | `play_now` returns 404; panel shows the error and refetches the list |
| Reorder/shuffle while the station is live | Snapshot rebuilt; current track continues; new order applies afterward |
| Auto pressed while already automatic | No-op; button disabled |
| Index out of range after re-sync | `advance()` clamps, as today |
| Control endpoint fails | Existing `messageFor` banner; live state unchanged |
| Backend restart | Manual mode persists in `broadcast_state` and resumes |

## 11. Testing

### 11.1 Backend (pytest)

- `advance` manual mode: mid-track offset, boundary wrap, and no schedule
  switch.
- `play_now`, `skip` next/prev (including switching to a non-live station), and
  `set_auto`.
- Order: saved order applied, new tracks appended, removed tracks dropped,
  duplicates, and survival across `sync_playlist`.
- `set_order` preserves the currently playing track.
- `GET /api/now` reports `source: "manual"`.
- All new admin endpoints return 401 unauthenticated and succeed when authed.

### 11.2 Frontend (Vitest)

- `reorder` and `shuffle` helpers.
- Panel renders the on-air card, Up next, and the full queue; the current row is
  highlighted.
- Play now shows the confirm prompt and then calls `api.play`.
- Next / Prev / Auto call the right endpoints; Auto is disabled unless manual.
- Shuffle calls `setStationOrder` with a permuted order (random mocked).
- The station picker refetches the selected station's tracks.

## 12. Configuration

No new environment variables. No database migration. No new dependencies.

## 13. Limitations

- Single backend process only, consistent with the existing broadcast and
  listener-count design; manual mode relies on the same in-process lock.
- Duplicate video ids within a station resolve to the first unused match when
  applying a saved order.
- Reorder/shuffle apply to the station's aggregate queue across all its
  playlists, not within an individual playlist.

## 14. Future Enhancements

- Push manual-mode and track changes over the existing WebSocket.
- Per-playlist ordering in addition to per-station ordering.
- A shuffle-mode toggle (random playback without rewriting the saved order).
- Undo for reorder/shuffle.
