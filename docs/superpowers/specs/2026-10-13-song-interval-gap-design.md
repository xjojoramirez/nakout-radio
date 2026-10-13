# Nakout Radio — Song Interval Gap — Design Specification

Date: 2026-10-13
Status: Approved for planning
Issue: #7 "Song interval"

## 1. Overview

The broadcast plays songs strictly back to back: the next track starts at the
exact instant the previous one ends (`started_at + duration`). Listeners on weak
connections need several seconds to load the next YouTube video, so they miss
the first moments of every song, which ruins the shared-listen experience.

This change inserts a short, station-wide **silence gap** between songs (default
**2 seconds**, configurable). During the gap every client preloads the upcoming
video, so all listeners start each song together at 0:00.

## 2. Goals

- A configurable silent interval (default 2s) between automatically-advanced
  songs, identical for every listener because the server clock is the authority.
- Clients preload the next video during the gap so playback starts at the song's
  first second even on weak connections.
- The listener UI stays coherent during the gap: previous track remains visible,
  no progress bar, station still reads "On air".
- Existing behavior, stored broadcast state, and admin live controls keep
  working; `gap = 0` disables the feature.

## 3. Non-Goals

- No per-track or per-genre gap lengths, no jingles/ads/announcements.
- No seamless transition feature (that is issue #6, preloading earlier than the
  gap): the gap code preloads only during the gap window.
- No change to admin UI, schedules, playlists, or the WebSocket protocol shape
  beyond the three new fields.
- No multi-instance backend changes.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Gap length | Env var `TRACK_GAP_SECONDS`, default `2.0`, `0` disables, max 30s |
| When it applies | Automatic transitions only: song→song, schedule genre switches, list loops. SKIP / PLAY NOW / AUTO place a track on air immediately |
| Modeling | Fold the gap into the boundary math (`Approach A`); stored `broadcast_state` JSON unchanged |
| During the gap, API | `track` remains the just-finished track; new fields carry `next_track` + `seconds_until_start` |
| During the gap, player | Mute, `loadVideoById(next, 0)`, immediately `pauseVideo()`; timer starts it at the exact boundary |
| During the gap, UI | Keep previous track's sleeve/title/artist, hide progress bar and times, header stays "On air" |

## 5. Architecture

No new services. Changes are contained in the backend broadcast module, config,
schemas, and the frontend player/broadcast/page layers.

```
backend/
├─ app/config.py       # TRACK_GAP_SECONDS setting + validation
├─ app/broadcast.py    # gap in advance()/_advance_manual(); gap phase in get_current()
├─ app/schemas.py      # NowOut: phase, next_track, seconds_until_start
└─ app/routers/now.py  # maps the new NowState fields

frontend/src/
├─ types.ts            # BroadcastNow: new fields
├─ hooks/useBroadcast.ts   # BroadcastState + toState carry the new fields
├─ hooks/useYouTubePlayer.ts  # preload during gap, timed start, gated drift/resume
└─ pages/RadioPage.tsx # gap presentation (hide bar/times, keep "On air")
```

## 6. Backend Design

### 6.1 Setting

`Settings.track_gap_seconds: float = 2.0`, fed by `TRACK_GAP_SECONDS`. Validation:
`0 <= v <= 30` (reject negative or absurd values at startup). Documented in
`backend/.env.example`. Values are floats so 1.5s is possible without code edits.

### 6.2 Boundary math

`advance(state, now, desired, snapshot, gap_seconds=0.0)` and
`_advance_manual(state, now, gap_seconds)` compute a song's end as:

    end = started_at + duration + gap_seconds

When a boundary is crossed, the next song's `started_at` is that same `end`, so
the silent window is `[started_at + duration, started_at + duration + gap)`.
The schedule is resolved at `desired(end)` — the instant the next song starts —
so a scheduled genre switch lands after the gap with the new genre's first track.
Wrapping the track list and snapshot refreshes behave exactly as today. Multiple
missed boundaries during a long catch-up integrate gaps for each elapsed song,
keeping the walk deterministic. Call sites pass
`get_settings().track_gap_seconds`; the default `0.0` keeps the pure function
behaving exactly as before for existing unit tests.

### 6.3 Gap phase in `get_current`

After advancing to `now`:

- `now < started_at + duration` → `phase = "playing"`, as today.
- `started_at + duration <= now < started_at + duration + gap` → `phase = "gap"`:
  - `track` = the track at `index` (the just-finished song);
  - `offset_seconds` = existing clamp (`duration - 1` while in the window);
  - `next_track` = the track that starts at the boundary, obtained by
    dry-running `advance(state, end)` (no persistence): this includes schedule
    genre switches, snapshot refresh on wrap, and empty-genre fallbacks;
  - `seconds_until_start` = `(end - now).total_seconds()` (float).

Steady-state gap requests do not write to the database: the advanced state
equals the loaded state whenever a gap is reported, so `_save` is skipped by the
existing equality check. The dry-run is a pure computation over at most one
boundary crossing.

`NowState` gains `phase: str = "playing"`, `next_track: TrackCache | None = None`,
`seconds_until_start: float | None = None` (defaults keep other callers valid).

### 6.4 Manual controls

`play_now()`, `skip()`, `set_auto()`, `set_order()`, and `stop()` keep their
current semantics: they place the desired track on air at `started_at = now`
(instant), and only subsequent time-based advancement uses gaps. A manual state
that loops through its list by itself gets gaps between loops, matching "every
automatic transition".

## 7. API

### 7.1 `GET /api/now` / WS radio frames

`NowOut` gains three additive fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `phase` | `"playing" \| "gap"` | `"gap"` only during the silent window |
| `next_track` | `TrackOut \| null` | Set only during a gap; the song starting at the boundary |
| `seconds_until_start` | `float \| null` | Set only during a gap; seconds until `next_track` starts at offset 0 |

`offset_seconds`, `server_time`, `source`, and off-air semantics
(`track: null`, `source: "none"`) are unchanged. The admin WebSocket push
(`notify_radio(build_now(...))`) carries the new fields automatically.

### 7.2 Client timing

The client converts `seconds_until_start` to a local boundary timestamp with the
same transit convention as `offset`: `fetchedAt + rttMs/2 + seconds_until_start*1000`.
Negative remainders clamp to an immediate start.

## 8. Frontend Design

### 8.1 `useBroadcast`

`BroadcastState` gains `phase: "playing" | "gap"`, `nextTrack: Track | null`,
`secondsUntilStart: number | null`, populated in `toState` for both poll and
WebSocket frames. Poll cadence, retry, and refresh behavior are unchanged.

### 8.2 `useYouTubePlayer`

**Gap phase** (when a broadcast frame reports `phase === "gap"`):

1. If the upcoming video is not already preloaded: mute the player,
   `loadVideoById({ videoId: next, startSeconds: 0 })`, then immediately
   `pauseVideo()`. The short muted load primes the stream so weak connections
   have data buffered when the song starts; pausing keeps the air silent. A
   player found `PLAYING` (video longer than its metadata) is paused too.
2. Schedule the start with a timer at the computed boundary timestamp. On fire:
   `seekTo(target, true)` (target ≈ 0 corrected by transit) and `playVideo()`,
   then restore the listener's mute/volume preference.
3. Every new broadcast frame cancels and recomputes a pending timer, so polls,
   WS pushes, or admin actions can never cause a double start or a stale start.
4. Drift correction and the mobile auto-resume logic in the 1s watch interval
   are gated on `phase === "playing"` so they cannot play the previous tail or
   fight the pending start.

**Playing phase** — unchanged, with one addition: when the incoming track is
already the preloaded video, skip `loadVideoById` (avoid a refetch/stutter) and
`seekTo(target, true)` + `playVideo()` instead. A different video (admin skip
mid-gap) uses the normal load path.

**Fresh joiners mid-gap**: the player is initialized directly into the preload
state (next video, muted, paused at 0) instead of playing the previous track's
tail.

**Error retry during a gap**: `reloadCurrent()` targets the upcoming track
(respecting the same mute/pause preload rules) rather than the finished one.

### 8.3 `RadioPage`

- `gap = state?.phase === "gap"`.
- During a gap: keep the sleeve/title/artist of the previous track; hide the
  progress bar and the time readout; header remains "On air".
- Turntable and VU meter drop out naturally via `player.playing` being false.
- Offline/off-air, volume, and mute controls are unaffected.

## 9. Error Handling

| Case | Behavior |
| --- | --- |
| Admin SKIP/PLAY NOW/AUTO/STOP mid-gap | New frame cancels the timer; chosen track starts instantly via normal paths |
| Blocked/deleted upcoming video | Retry targets the upcoming track; if still failing at the boundary, the playing-phase path joins late like today |
| `TRACK_GAP_SECONDS=0` | No gap phases; new fields default; exact old behavior |
| Stale transit math | `seconds_until_start` below 0 clamps to immediate start |
| Poll/network failure during gap | Keep the timer; next successful frame reconciles |
| Schedule switch at a boundary | `next_track` already reflects the new genre; client preloads the right video |
| Off-air during gap | Existing off-air presentation; resume starts the first track instantly |

## 10. Testing

**Backend (pytest)** — `test_broadcast.py` additions plus config/schema tests:

- boundary includes the gap; offset stays clamped mid-gap;
- multiple elapsed songs integrate multiple gaps (long catch-up);
- `get_current` mid-gap returns `phase="gap"`, previous `track`, `next_track`,
  `seconds_until_start`; mid-song returns `phase="playing"` with `None`s;
- `next_track` across a schedule genre switch and across a list wrap;
- manual state loops advance with gaps while `skip`/`play_now` place instantly;
- `gap_seconds=0` preserves every existing boundary test;
- `NowOut` serializes new fields (defaults for playing);
- `TRACK_GAP_SECONDS` validation rejects negatives, accepts `0` and `1.5`.

**Frontend (Vitest)** — hook tests with mocked player:

- `useBroadcast` maps the new fields (poll and WS);
- during a gap: `loadVideoById(next, 0)` + `pauseVideo()` called, `playVideo`
  not called, drift/resume suppressed;
- timer fires at the boundary: `seekTo` + `playVideo` with restored mute state;
- a new frame cancels/reschedules the pending start (no double start);
- phase flips to playing with the preloaded video: no `loadVideoById`, seek+play;
- retry during gap targets the next track;
- `RadioPage`: progress bar/times hidden, previous title shown, "On air" kept.

## 11. Configuration

`TRACK_GAP_SECONDS` (float, default 2.0, range 0–30), documented in
`backend/.env.example`. Passed to the backend via the existing
`env_file: ./backend/.env` wiring; no compose or Caddy changes.

## 12. Limitations

- The gap is a station-wide fixed constant; per-song behavior is out of scope.
- Boundary transitions are pull-based (no scheduler process): clients time the
  gap end locally from `seconds_until_start` and reconcile on the next poll/WS
  frame (≤5s later), same eventual-consistency model as existing sync.
- Preloading relies on the YouTube IFrame API accepting `loadVideoById` +
  immediate `pause`; if the embed declines to buffer while paused, weak clients
  fall back to the pre-gap late-join behavior (no regression).
