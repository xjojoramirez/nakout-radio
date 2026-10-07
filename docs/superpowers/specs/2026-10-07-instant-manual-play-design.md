# Nakout Radio — Instant Manual Play — Design Specification

Date: 2026-10-07
Status: Approved for planning

## 1. Overview

When an operator starts a track from the admin Now Playing panel (`Play`,
`Next`, `Prev`, `Auto`, or a queue reorder), listeners on the public radio page
do not react immediately. The radio page learns about playback only by polling
`GET /api/now` every 5 seconds, so a manual change can take up to five seconds
to appear. Worse, when the update finally arrives the player seeks to the
server-computed live offset, which by then is roughly the poll delay — the song
starts about a second in rather than at 0:00.

This change makes manual playback changes reach connected listeners
**immediately** by pushing the new `now` state over a dedicated WebSocket, while
keeping the existing poll as a safety net. Because the state is pushed at the
instant the operator acts, a manually started track begins at **0:00** for
listeners who are already connected.

## 2. Goals

- A manual `Play` (or Next/Prev/Auto/order) reaches already-connected listeners
  in well under a second.
- A manually started track begins at 0:00 for already-connected listeners.
- The existing 5-second poll and its fallback behavior remain intact, so the
  radio still recovers from dropped sockets, missed pushes, and natural
  track ends.
- No regression to the shared-broadcast semantics: all listeners hear the same
  track at the same position.

## 3. Non-Goals

- No change to how a listener who **opens the page later** joins: they still
  join at the current live offset, not at 0:00. Restarting the song for a new
  visitor would desynchronize existing listeners.
- No push for passive/auto transitions (schedule switch, natural track end).
  These continue to be handled by the client poll and the player's `ENDED`
  refresh path. (They may change at a track boundary that the poll catches
  within 5 seconds, which is the existing behavior.)
- No changes to the YouTube IFrame player, the broadcast engine, or the
  database schema.
- No multi-instance support. The push registry is in-memory, matching the
  existing listener-count limitation.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Transport | New dedicated WebSocket endpoint `/api/ws/radio` |
| Push trigger | Explicit, after each admin playback mutation |
| Payload | The same `NowOut` shape returned by `GET /api/now` |
| Fallback | Existing 5s client poll retained unchanged |
| Start position | Pushed snapshot has `offset_seconds = 0` for a manual play |
| Late joiners | Still join at the live offset (shared broadcast preserved) |
| Session | Snapshot built from the request's DB session (respects test overrides) |

## 5. Architecture

The three services (`caddy`, `frontend`, `backend`) are unchanged. The push
reuses the existing WebSocket route and the existing `/api/now` payload.

```
backend/app/
├─ routers/
│  ├─ now.py        # build_now() extracted; GET /api/now uses it
│  ├─ ws.py         # NEW: /api/ws/radio + radio client registry + notify_radio()
│  └─ admin.py      # playback/order endpoints call notify_radio(snapshot)

frontend/src/
└─ hooks/
   └─ useBroadcast.ts  # opens /api/ws/radio; updates state on push; keeps poll
```

## 6. Backend

### 6.1 Shared snapshot builder

Extract the body of the `/api/now` handler into a reusable helper, keeping the
route as a thin wrapper:

```python
# routers/now.py
def build_now(session: Session, ts: datetime) -> NowOut:
    state = get_current(session, ts)
    ...  # existing genre/track/offset/source assembly
```

`GET /api/now` becomes `return build_now(session, utcnow())`. Both the poll and
the push therefore emit an identical `NowOut`, including `offset_seconds`,
`server_time`, and `source`.

### 6.2 Radio WebSocket

A new endpoint in `routers/ws.py`, alongside the existing `/api/ws/listeners`:

- `GET /api/ws/radio` (WebSocket). On connect: accept, register the socket in a
  module-level set, then hold the connection open (drain incoming frames) until
  disconnect; always deregister in a `finally`.
- A module-level `_radio_loop: asyncio.AbstractEventLoop | None`, captured from
  `asyncio.get_running_loop()` when the endpoint runs.

The listener-count endpoint and its set are untouched.

### 6.3 Push helper

```python
def notify_radio(snapshot: dict) -> None:
    """Schedule a push of `snapshot` to all radio clients. Safe to call from a
    sync endpoint; no-op when no client has ever connected."""
    loop = _radio_loop
    if loop is None or not _radio_clients:
        return
    asyncio.run_coroutine_threadsafe(_send_to_all(snapshot), loop)
```

`_send_to_all` awaits `ws.send_json(snapshot)` for every registered socket,
discarding any that raise. It must not touch the database — the caller passes an
already-serialized `NowOut` — so it never blocks the event loop and always
reflects the state the mutation just committed.

### 6.4 Trigger points (`routers/admin.py`)

After a successful mutation, build the snapshot from the **same request
session** and push it:

| Endpoint | Mutation | Push |
| --- | --- | --- |
| `POST /playback/play` | `play_now(...)` | `build_now(session, utcnow())` |
| `POST /playback/next` | `skip(..., "next")` | idem |
| `POST /playback/prev` | `skip(..., "prev")` | idem |
| `POST /playback/auto` | `set_auto(...)` | idem |
| `PUT /genres/{id}/order` | `set_order(...)` | idem |

`play_now` stores the manual state with `started_at = now`, so the pushed
`offset_seconds` is 0 and connected players restart/switch to 0:00.

Building from the request session (rather than opening a new session inside the
push coroutine) keeps behavior correct under the tests' `get_session`
dependency override and avoids cross-session consistency questions.

### 6.5 Error handling

A push is best-effort. If there are no clients, no captured loop, or a socket
send fails, the helper is a no-op or drops only the failing socket; it never
raises into the request path. Any missed push is recovered by the client's
5-second poll.

## 7. Frontend

### 7.1 `useBroadcast`

Keep the current behavior and add a push channel:

- Open a WebSocket to `/api/ws/radio` on mount, using the same reconnect /
  exponential-backoff pattern as `useListenerCount` (1s → 30s, jittered).
- On a message frame, parse the `NowOut` JSON into `BroadcastState` exactly as
  the poll does, setting `fetchedAt = Date.now()` and `rttMs = 0`, and apply it
  immediately.
- Keep the existing 5-second poll. It continues to load on mount, refresh after
  a forced `refresh()`, cover natural track ends, and act as a fallback when the
  socket is down.
- Malformed frames are ignored (matching `useListenerCount`).
- The socket is closed (and reconnection stopped) on unmount.

The hook's public shape — `{ state, failed, refresh }` — is unchanged, so
`RadioPage` and `NowPlayingPanel` need no changes.

### 7.2 Start position

The push arrives with `offset_seconds ≈ 0` and `rttMs = 0`, so
`liveTarget = offset + rtt/2 + elapsed ≈ 0`. `useYouTubePlayer` sees a changed
`youtube_video_id` (or an ended/at-0 same track) and calls
`loadVideoById({ videoId, startSeconds: 0 })` — from the start. No player change
is required.

## 8. Testing

**Backend (`pytest`).**

- `build_now` returns the expected `NowOut` for a seeded genre (thin test over
  the extracted helper, reusing `test_now.py` fixtures).
- Radio push: open a `/api/ws/radio` socket with `TestClient`, authenticated via
  the admin cookie, `POST /api/admin/playback/play`, and assert the socket
  receives a `now` payload whose track is the requested one and whose
  `offset_seconds` is 0.
- No-clients safety: pushing with zero connected clients does not raise and the
  admin request still returns 200.
- Existing `/api/now`, listener-count, and live-control tests continue to pass.

**Frontend (Vitest).**

- `useBroadcast` applies a pushed frame to `state` immediately (FakeWebSocket).
- A pushed frame updates `fetchedAt`/`rttMs` consistently (`rttMs` 0).
- The 5-second poll still fires and still updates state (existing tests).
- Malformed frames are ignored; reconnection is attempted after a close.

**Manual.** Rebuild both images, open the radio page and the admin panel in two
tabs, click `Play` on a queue track, and confirm the radio switches to that
track and starts at 0:00 within a fraction of a second.

## 9. Configuration

No new environment variables. Caddy already proxies `/api/ws` to the backend, so
`/api/ws/radio` is reachable without config changes.

## 10. Limitations

- The push registry and captured event loop are per-process. A single backend
  instance is assumed, consistent with the existing listener count.
- If the server has multiple uvicorn workers, a client may connect to worker A
  while a mutation is handled by worker B; that listener would fall back to the
  5-second poll. Same single-instance assumption as today.

## 11. Future Enhancements

- Push passive transitions (schedule switch, track end) from a broadcast-state
  watcher, retiring the poll entirely.
- Merge the listener-count and radio sockets into one connection.
