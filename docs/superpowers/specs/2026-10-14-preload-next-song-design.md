# Preload the next song ahead of the boundary (issue #6) — design

## Problem

Issue #6: listeners on weak connections start every song cold. Today the
player preloads the next track only *during* the 2-second gap (muted, then
paused), so real buffering begins at the boundary and the first seconds can
stall. The issue asks for the next song to be preloaded well ahead of time.

**Constraint:** a single YouTube IFrame player cannot buffer a second video
without interrupting the one playing (`loadVideoById` replaces the stream).
True preloading needs a second, hidden player that buffers ahead and takes
over at the boundary.

## Goal

By the time a song starts, the listener's player has already buffered a
configurable lead window of it (default 20 s), so playback starts without a
stall even on a weak connection. If anything in the preload path is
unhealthy, the behavior falls back exactly to today's gap preload — no
user-visible regression.

## Non-goals

- Per-connection adaptivity (only preload for weak connections) — rejected
  in brainstorming; preload is station-wide and tunable instead.
- Preloading more than one track ahead, or playlist prefetch outside the
  iframe player.
- UI indicators for preload state; changing the gap protocol.

## Backend design

### Peek: expose the next track while playing

`get_current()` currently exposes `next_track` + `seconds_until_start` only
during the gap (a dry-run of `advance()` at track end + gap). Extract that
dry-run into a helper (e.g. `_peek_next(session, state, gap)`) and call it in
the playing path too:

| phase | `next_track` | `seconds_until_start` |
| --- | --- | --- |
| `playing` | first track after the current at the boundary | seconds until it starts: (track end + gap) − now |
| `gap` | unchanged (track after the gap) | unchanged (gap remaining) |

Stopped / no tracks → both `null` (as today).

`build_now` already forwards both fields and WebSocket frames use
`build_now(...).model_dump()` (`routers/admin.py`), so poll + push both carry
the new data automatically. `useBroadcast` maps the fields generically — no
change needed there.

Edge cases the peek already handles (via `advance`):

- Manual mode (skip / play now): next = following queue index, wrapping.
- Schedule genre change at the boundary: `desired(boundary)` resolves it.
- Single-track genre: next = the **same** track (same video id) — the client
  keys the pre-roll on the video id; boundary re-estimates only re-time the
  swap (so a fresh estimate never restarts the buffer), and the post-swap
  reset re-arms the same id from 0 for the following boundary.

### Setting: `PRELOAD_LEAD_SECONDS`

- `backend/app/config.py`: `preload_lead_seconds: float = 20.0`, validator
  0–300; `0` disables preloading (client falls back to the gap path).
- `backend/.env.example`: document it next to `TRACK_GAP_SECONDS`.
- Exposed per response in `NowOut` as `preload_lead_seconds: float`, so the
  station can tune it without a frontend rebuild.

## Frontend design

### Two players, two roles

- `RadioPage.tsx` gains a second hidden container (`#yt-preload`) beside
  `#yt-player`.
- `useYouTubePlayer` creates both players in the same effect:
  - **active** (`playerRef`) — audible; all existing logic (drift seek,
    mobile resume, gap fallback, ENDED → `onEnded`) applies to it unchanged.
  - **preload** (`preloadRef`) — always muted; buffers ahead; takes over at
    the boundary.
- Role swap at the boundary: the preload player becomes active; the old
  active player is paused, muted, and idles as the new preload for the
  following track. Event handlers are identity-aware: only the current
  active player drives `playing` / ENDED state (a late `PAUSED` event from
  the demoted player must not clobber the new state).

### Pre-roll lifecycle

Driven by the existing 1 s reconcile tick + broadcast effect:

1. **Arm** — when `phase === "playing"`, `nextTrack` is known,
   `preloadLead > 0`, and `now ≥ boundaryAt − lead·1000` (with `boundaryAt`
   computed by the same `fetchedAt + rtt/2 + secondsUntilStart·1000` formula
   as `scheduleGapStart`): ensure the preload player has `nextTrack` loaded
   (`loadVideoById` from 0 otherwise), `mute()`, `playVideo()` — muted
   playback is what builds the buffer. Tracking is keyed on the video id;
   boundary re-estimates only re-time the swap (a fresh estimate never
   restarts the buffer).
2. **Swap** — a boundary timer (mirror of `scheduleGapStart`) fires at
   `boundaryAt`: if the preload player still holds the right video, seek to
   the live position (≈0; the region was just buffered), apply the user's
   volume + mute state, `playVideo()`, swap roles/refs, update
   `currentVideoRef`, reset retry state.
3. **Demote** — the former active player pauses and mutes; it is re-armed
   when the following track's lead window opens.

### Fallback matrix (nothing regresses)

| Situation | Behavior |
| --- | --- |
| Preload healthy at the boundary | role swap as above |
| Preload missing / errored / wrong video / lead = 0 | today's path: active player loads the next video during the gap, boundary timer calls the existing `startPreloaded` |
| Listener joins during the gap | today's path — active player takes `nextTrack` and starts at the boundary; never waits on a cold preload player |
| Admin skip / play now / auto / stop mid-pre-roll | reconcile detects the new current video: pause + clear the preload player, load the new current on the active player; preload re-arms when the next lead window opens |
| Preload player stalls mid-roll | harmless (muted); the boundary swap seeks to the live position; if unbuffered, playback continues from the buffered start — same degradation as today |

### Data / traffic

Muted pre-roll streams up to `lead` seconds of video per song (default 20 s —
a small fraction of a song). `preload_lead_seconds = 0` disables it entirely:
behavior becomes byte-identical to today.

## Testing

Backend (`backend/tests/`):

- `test_now.py`: `next_track` + `seconds_until_start` present while playing
  (schedule flow and manual flow); math checks (remaining + gap); gap phase
  unchanged; stopped → nulls; single-track genre → next = same track.
- `test_config.py`: `preload_lead_seconds` bounds validation.

Frontend (`frontend/src/`):

- `hooks/useYouTubePlayer.dom.test.ts` (two `FakePlayer`s +
  `vi.useFakeTimers`): pre-roll starts muted + playing at the lead threshold;
  swap at the boundary (seek ≈ 0, unmute/volume per user state, `playing`
  stays true, roles swapped); no pre-roll with lead = 0 or unknown
  `nextTrack`; preload error → gap fallback; skip mid-pre-roll cancels and
  reloads; single-track genre re-arms for the next boundary.
- `pages/RadioPage.dom.test.tsx`: the second hidden container exists.

## Risks and manual verification

- **Backward seek keeps the buffer** is the core assumption: YouTube retains
  buffered ranges on backward seeks. Verify once manually with network
  throttling (DevTools slow-3G): song start should not stall, and the
  preload player should be visibly ahead in the devtools media panel.
- Two iframes on mobile (memory, iOS backgrounding): the active player's
  existing resume logic is unaffected; preload failures degrade to today's
  behavior.
