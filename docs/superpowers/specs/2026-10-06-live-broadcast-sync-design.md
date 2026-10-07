# Nakout Radio — Live Broadcast Sync — Design Specification

Date: 2026-10-06
Status: Approved for planning

## 1. Overview

Nakout Radio currently hands each visitor their own copy of the schedule's
current track. Every browser starts that track at 0:00 and advances to the next
song on its own, so listeners who open the page at different times hear
different songs at different positions. It behaves like a shared playlist, not a
radio.

This change makes the site a **single continuous broadcast**. The backend
becomes the authority on what is playing and at what second. Every visitor is
synced to the same position in the same song, like tuning into a real FM
station. Visitors choose only their **volume**; they do not choose the station
or the song.

Two changes ship together:

1. **Server-authoritative broadcast clock** — one schedule-driven channel whose
   track and elapsed offset are computed from a stored anchor.
2. **Muted-autoplay listener experience** — the radio starts playing
   immediately (muted, because browsers require it), with a mute toggle and a
   remembered volume slider.

## 2. Goals

- All concurrent listeners hear the same track at (approximately) the same
  second.
- The station plays continuously, 24/7, with no per-visitor control needed.
- The page starts playing audio on load, muted, without a tap.
- A visitor can unmute and set volume; the volume level is remembered.
- The time-of-day schedule still selects the live station; when it changes, the
  current song finishes before the switch.
- Preserve the single global channel: no personal station selection, and no
  per-listener skip/previous.

## 3. Non-Goals

- No per-listener skip, previous, shuffle, or "request a song".
- No mood-station dial for visitors (stations and schedule remain admin-managed).
- No queue/history view.
- No multi-instance / horizontally scaled backend. The broadcast state assumes a
  single backend process, consistent with the existing listener-count design.
- No change to how playlists are fetched from YouTube or how the schedule is
  configured.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Sync model | True broadcast sync; clients seek to a server-computed offset |
| Broadcast scope | One global, schedule-driven channel; visitor dial removed |
| Schedule transitions | Finish the current song, then switch to the new station |
| Broadcast engine | Deterministic, computed lazily from a stored anchor (no worker) |
| Client updates | Poll `/api/now` every few seconds; correct drift over ~2s |
| Start state | Muted autoplay, with a best-effort attempt to honor a saved unmuted preference |
| Volume | Slider + mute toggle, persisted in `localStorage` |

## 5. Architecture

The existing three services (`caddy`, `frontend`, `backend`) are unchanged. This
change is contained in the backend broadcast module and the frontend player
hooks.

```
backend/app/
├─ broadcast.py        # NEW: anchor load, lazy advance, current-state resolution
├─ routers/
│  ├─ now.py           # NEW: GET /api/now  (thin wrapper over broadcast.py)
│  ├─ schedule.py      # kept; /api/schedule/now delegates to broadcast
│  ├─ stations.py      # unchanged (tracks_for_station reused)
│  └─ queue.py         # kept for compatibility; no longer used by the player

frontend/src/
├─ hooks/
│  ├─ useBroadcast.ts  # NEW: polls /api/now, exposes track + offset + clock skew
│  ├─ useYouTubePlayer.ts  # REWRITTEN: join-at-offset, drift correction, volume/mute
│  └─ useSchedule.ts   # removed (replaced by useBroadcast)
└─ pages/RadioPage.tsx # dial / prev / next / shuffle / override removed
```

## 6. Broadcast Engine (backend)

### 6.1 State

The live broadcast state is stored in the existing `Setting` key/value table
under the key `broadcast_state` as a JSON string:

```json
{
  "station_id": 3,
  "track_ids": [41, 42, 43],
  "durations": [214, 187, 260],
  "index": 1,
  "started_at_utc": "2026-10-06T04:12:07"
}
```

- `track_ids` / `durations` are an ordered snapshot of the station's tracks
  (`TrackCache.id` and `duration_seconds`) taken when the snapshot was built.
  Snapshotting keeps durations stable for the duration of the current song even
  if an admin re-syncs a playlist.
- `index` is the position of the currently playing track within the snapshot.
- `started_at_utc` is the moment the track at `index` began (naive UTC, matching
  the existing `_utcnow` convention).

A module-level `threading.Lock` and an in-memory cache guard reads and writes.
The cache is loaded from `Setting` on first use. State is persisted only when it
changes (a boundary is crossed or the station switches), so steady-state polling
performs no writes.

### 6.2 Lazy advance

`get_current_state(session, now_utc)` returns the station, track, and elapsed
offset:

1. Load the cached state (or initialize it: resolve the scheduled station, build
   its snapshot, set `index = 0`, `started_at_utc = now_utc`).
2. **Replay boundaries.** While `now_utc >= started_at_utc + durations[index]`:
   - Let `boundary = started_at_utc + durations[index]`.
   - Resolve the scheduled station **at `boundary`** (converted to `STATION_TZ`).
   - If the scheduled station differs from the current one: switch — rebuild the
     snapshot for the new station, set `index = 0`, and set
     `started_at_utc = boundary` (so the new station's first track starts exactly
     at the boundary). The previous song has just finished, satisfying the
     "finish the current song, then switch" rule.
   - Otherwise: advance `index`; if it reaches the end of the snapshot, wrap to
     `0`. Set `started_at_utc = boundary`.
   - Re-reading the snapshot on a wrap (or on a station change) lets admin
     playlist edits take effect from the next song onward.
3. `offset = now_utc - started_at_utc`, clamped to `[0, duration - 1]`.
4. If the state changed during replay, persist it. Return
   `(station, track, offset)`.

Because boundaries are evaluated at their own timestamps (not at `now_utc`), the
result is correct even if nobody requested `/api/now` for a long stretch — a
returning request catches up deterministically.

### 6.3 Empty / missing stations

- If the scheduled station has no cached tracks, fall back to the station marked
  `is_default`. If that also has no tracks, or no station resolves, return an
  off-air result with `station = null`, `track = null`.
- When the broadcast is off-air, the stored state is left as-is; the next request
  re-attempts resolution, so adding tracks to the admin panel brings it back.

### 6.4 Time source

All internal timestamps are naive UTC (`datetime.now(timezone.utc).replace(tzinfo=None)`),
matching `models._utcnow`. Schedule matching converts the boundary time to
`STATION_TZ` via `ZoneInfo`, exactly as `scheduler.resolve_station_id` already
expects.

## 7. API

### 7.1 `GET /api/now`

New endpoint. Response model `NowOut`:

| Field | Type | Meaning |
| --- | --- | --- |
| `station` | `StationOut \| null` | The live station |
| `track` | `TrackOut \| null` | The track currently on air |
| `offset_seconds` | `int` | Elapsed seconds into `track` |
| `server_time` | `str` | ISO-8601 UTC timestamp used to compute `offset_seconds` |
| `source` | `str` | `"schedule"`, `"default"`, or `"none"` |

`TrackOut` is unchanged (`youtube_video_id`, `title`, `artist`,
`thumbnail_url`, `duration_seconds`, `position`).

The client computes clock skew from `server_time` and seeks to
`offset_seconds + transit`, where `transit` is half the request/response time.
`source == "none"` renders the existing "off air" state.

### 7.2 Compatibility

- `GET /api/schedule/now` is kept and internally returns the same data (adapted
  into `CurrentStationOut`) so no external caller breaks. The frontend stops
  using it.
- `POST /api/queue/advance` and the signed cursor helpers are kept but unused by
  the player. They are not removed, to avoid churn and keep optional
  admin/preview tooling possible.

## 8. Frontend

### 8.1 `useBroadcast`

Polls `GET /api/now` every 5 seconds. Exposes:

- `track`, `station`, `source`, `duration`
- `offset` and a `servertime ↔ localtime` skew estimate
- `requestRefresh()` for immediate re-poll (called on track end)

On poll error, the last known track/state is retained (the player keeps
playing); the next tick retries.

### 8.2 `useYouTubePlayer` (rewritten)

- Creates the IFrame player with
  `playerVars: { autoplay: 1, mute: 1, controls: 0, disablekb: 1, playsinline: 1 }`.
- On player ready and on every poll result:
  - If the `youtube_video_id` changed → `loadVideoById({ videoId, startSeconds: offset })`.
  - Else if `|player.getCurrentTime() - offset| > DRIFT_THRESHOLD (≈2s)` →
    `seekTo(offset, true)`.
- On `PlayerState.ENDED` → call `requestRefresh()` instead of advancing locally;
  the server has already moved to the next track.
- Volume / mute:
  - `setVolume(0..100)` → `player.setVolume`, persist to `localStorage`.
  - `toggleMute()` → `mute()` / `unMute`, persist, update UI.
  - On load, read saved volume (default `70`) and saved mute preference.
- Autoplay fallback: if the saved preference is unmuted, start unmuted; if the
  player has not reached `PLAYING` within ~1.5s (browser blocked sound), call
  `mute()` + `playVideo()` and reflect muted in the UI.
- Progress for `NowPlaying` comes from `player.getCurrentTime()` (the real player
  clock), which naturally stays between resyncs.

### 8.3 `RadioPage`

- Remove: `StationDial`, the `override`/`AUTO` state, `selectStation`, and the
  PREV / NEXT / SHUFFLE buttons.
- Keep: header, listener count, `NowPlaying`, `VUMeter`.
- Add: a MUTE/UNMUTE button and a volume slider.
- Keep the RETRY affordance for the error state (`source === "none"` is a
  separate "off air" presentation; player errors still offer RETRY).
- The `resetKey` mechanism is no longer needed since the station is not
  user-selectable; the hook follows server changes on its own.

## 9. Error Handling

| Case | Behavior |
| --- | --- |
| No live station / no tracks | `/api/now` returns `source: "none"`; UI shows "off air" |
| Poll/network failure | Keep current playback; retry next tick |
| Removed/blocked video | Player `onError` requests an immediate refresh; server advance skips the track at the next boundary |
| Browser blocks unmuted autoplay | Fall back to muted autoplay; UI shows muted |
| Admin playlist edit | Takes effect from the next song boundary (snapshot re-read on wrap) |
| Backend restart | State is reloaded from `Setting`; broadcast continues from the saved anchor |

## 10. Testing

**Backend (pytest).** The advance algorithm is factored as a pure function of
`(state, durations, now, schedule_resolver)` so it can be unit-tested without a
DB or clock:

- mid-track: offset equals elapsed time within the current song.
- exact boundary: advances to the next song at offset 0.
- multiple elapsed songs while offline: lands on the correct index/offset.
- loop: wrapping past the last track returns to index 0.
- station switch: when the schedule changes, the running song ends first, then
  the new station starts at index 0 at the boundary.
- empty station / no default → off-air.
- `/api/now` endpoint test with `tracks_for_station` and the schedule mocked,
  asserting `offset_seconds`, `server_time`, and `source`.

**Frontend (Vitest).**

- Volume/mute persistence: saved values are read on mount and written on change.
- Sync math: `offset + transit` correction given a mocked `server_time` skew.
- Poll resync: a changed `youtube_video_id` triggers a load; a small drift does
  not seek, a large drift does (player mocked).

## 11. Configuration

No new environment variables. The feature reuses `STATION_TZ`, `SECRET_KEY`
(via the existing `Setting` table and cursor helpers), and the database.

## 12. Limitations

- Single backend process only. Multiple uvicorn workers would each hold their own
  in-memory cache; state persistence keeps them roughly consistent but the lock
  is per-process. This matches the existing listener-count limitation and is
  documented as a future upgrade (shared store).
- Sync is seek-based; a client that is buffering may briefly lag before the next
  drift correction.

## 13. Future Enhancements

- Push broadcast changes over the existing WebSocket instead of polling.
- Expose a "listeners currently hearing this" count per track.
- Admin "take over live" control to force a station or track immediately.
