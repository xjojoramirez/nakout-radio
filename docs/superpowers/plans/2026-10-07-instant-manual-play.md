# Instant Manual Play Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push admin playback changes to connected radio listeners over WebSocket so a manually started track plays immediately and from 0:00.

**Architecture:** A dedicated `/api/ws/radio` WebSocket tracks connected listeners. After each admin playback mutation, the endpoint builds the same `NowOut` payload that `GET /api/now` returns (from the request's DB session) and schedules a best-effort push to all registered sockets. The client hook `useBroadcast` applies pushed frames immediately and keeps its existing 5-second poll as a fallback.

**Tech Stack:** FastAPI + SQLModel/SQLite (backend), React + TypeScript + Vitest (frontend), pytest.

---

## File Structure

- `backend/app/routers/now.py` — extract `build_now(session, ts) -> NowOut`; `/api/now` becomes a thin wrapper.
- `backend/app/routers/ws.py` — add `/api/ws/radio` endpoint, `_radio_clients`, `_radio_loop`, `_send_to_all`, `notify_radio`.
- `backend/app/routers/admin.py` — call `notify_radio(build_now(session, utcnow()).model_dump())` after each playback mutation.
- `backend/tests/test_now.py` — unit test for `build_now`.
- `backend/tests/test_ws.py` — radio push tests.
- `frontend/src/hooks/useBroadcast.ts` — add radio socket; keep poll.
- `frontend/src/test/setup.ts` — default no-op `WebSocket` stub.
- `frontend/src/hooks/useBroadcast.dom.test.ts` — socket frame tests.
- `docs/changelog.md` — change entry.

---

## Task 1: Extract `build_now` in the `/api/now` router

**Files:**
- Modify: `backend/app/routers/now.py`
- Test: `backend/tests/test_now.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_now.py`:

```python
def test_build_now_matches_endpoint_shape(tmp_path):
    from datetime import datetime

    from app.routers.now import build_now

    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True, video="bv", duration=200)
        body = build_now(s, datetime(2026, 1, 1, 0, 0, 0))
    assert body.source == "default"
    assert body.genre is not None and body.genre.slug == "morning"
    assert body.track is not None and body.track.youtube_video_id == "bv"
    assert body.offset_seconds == 0
    assert body.server_time
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_now.py::test_build_now_matches_endpoint_shape -v`
Expected: FAIL with `ImportError: cannot import name 'build_now'`.

- [ ] **Step 3: Extract the helper**

Replace the top of `backend/app/routers/now.py`:

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.broadcast import get_current, utcnow
from app.db import get_session
from app.routers.genres import tracks_for_genre
from app.schemas import NowOut, GenreOut, TrackOut

router = APIRouter(prefix="/api", tags=["now"])


def build_now(session: Session, ts: datetime) -> NowOut:
    state = get_current(session, ts)
    genre_out = None
    if state.genre is not None:
        genre_out = GenreOut(
            id=state.genre.id,
            name=state.genre.name,
            slug=state.genre.slug,
            is_default=state.genre.is_default,
            track_count=len(tracks_for_genre(session, state.genre.id)),
        )
    return NowOut(
        genre=genre_out,
        track=TrackOut.model_validate(state.track) if state.track else None,
        offset_seconds=state.offset_seconds,
        server_time=ts.replace(tzinfo=timezone.utc).isoformat(),
        source=state.source,
    )


@router.get("/now", response_model=NowOut)
def now(session: Session = Depends(get_session)) -> NowOut:
    return build_now(session, utcnow())
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/test_now.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/now.py backend/tests/test_now.py
git commit -m "refactor: extract build_now from /api/now"
```

---

## Task 2: Add the `/api/ws/radio` endpoint and push helper

**Files:**
- Modify: `backend/app/routers/ws.py`
- Modify: `backend/app/routers/admin.py` (wire `play` only, in this task)
- Test: `backend/tests/test_ws.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ws.py`:

```python
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.models import Genre, Playlist, TrackCache


def _radio_client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app), engine


def _seed(session, slug, vids):
    st = Genre(name=slug.title(), slug=slug, is_default=True)
    session.add(st)
    session.commit()
    session.refresh(st)
    pl = Playlist(genre_id=st.id, youtube_playlist_id=f"PL-{slug}")
    session.add(pl)
    session.commit()
    session.refresh(pl)
    for pos, vid in enumerate(vids):
        session.add(
            TrackCache(
                playlist_id=pl.id,
                youtube_video_id=vid,
                title=vid.upper(),
                artist="A",
                position=pos,
                duration_seconds=100,
            )
        )
    session.commit()
    return st


def test_radio_pushes_manual_play_at_zero(tmp_path):
    client, engine = _radio_client(tmp_path)
    with Session(engine) as s:
        gid = _seed(s, "chill", ["a", "b", "c"]).id
    client.post("/api/admin/login", json={"password": "test-pass"})
    with client.websocket_connect("/api/ws/radio") as ws:
        resp = client.post(
            "/api/admin/playback/play",
            json={"genre_id": gid, "youtube_video_id": "b"},
        )
        assert resp.status_code == 200
        message = ws.receive_json()
    assert message["source"] == "manual"
    assert message["track"]["youtube_video_id"] == "b"
    assert message["offset_seconds"] == 0


def test_radio_play_without_clients_succeeds(tmp_path):
    client, engine = _radio_client(tmp_path)
    with Session(engine) as s:
        gid = _seed(s, "chill", ["a", "b"]).id
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/playback/play",
        json={"genre_id": gid, "youtube_video_id": "b"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `python -m pytest tests/test_ws.py -q`
Expected: FAIL — the first test's `websocket_connect("/api/ws/radio")` raises (no such route) and/or no push reaches the socket.

- [ ] **Step 3: Add the endpoint and helpers**

Replace `backend/app/routers/ws.py` with:

```python
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/ws", tags=["ws"])

_connections: set[WebSocket] = set()
_radio_clients: set[WebSocket] = set()
_radio_loop: asyncio.AbstractEventLoop | None = None


async def _broadcast() -> None:
    payload = {"count": len(_connections)}
    for ws in list(_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            _connections.discard(ws)


@router.websocket("/listeners")
async def listeners(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    await _broadcast()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        await _broadcast()


async def _send_to_all(payload: dict) -> None:
    for ws in list(_radio_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            _radio_clients.discard(ws)


def notify_radio(payload: dict) -> None:
    """Best-effort push of `payload` to all radio listeners.

    Safe to call from a sync endpoint. No-op when no listener has connected.
    """
    loop = _radio_loop
    if loop is None or not _radio_clients:
        return
    try:
        asyncio.run_coroutine_threadsafe(_send_to_all(payload), loop)
    except RuntimeError:
        pass


@router.websocket("/radio")
async def radio(websocket: WebSocket) -> None:
    global _radio_loop
    await websocket.accept()
    _radio_loop = asyncio.get_running_loop()
    _radio_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _radio_clients.discard(websocket)
```

- [ ] **Step 4: Wire the `play` endpoint**

In `backend/app/routers/admin.py`, update the imports:

```python
from app.broadcast import play_now, set_auto, set_order, skip, utcnow
from app.routers.now import build_now
from app.routers.ws import notify_radio
```

Then replace the body of `playback_play` with:

```python
@router.post("/playback/play", dependencies=[Depends(require_admin)])
def playback_play(body: PlayIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        play_now(session, body.genre_id, body.youtube_video_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/test_ws.py tests/test_now.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/ws.py backend/app/routers/admin.py backend/tests/test_ws.py
git commit -m "feat: push manual playback to /api/ws/radio listeners"
```

---

## Task 3: Push the remaining admin playback changes

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_ws.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ws.py`:

```python
def test_radio_pushes_skip(tmp_path):
    client, engine = _radio_client(tmp_path)
    with Session(engine) as s:
        gid = _seed(s, "chill", ["a", "b", "c"]).id
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post(
        "/api/admin/playback/play",
        json={"genre_id": gid, "youtube_video_id": "a"},
    )
    with client.websocket_connect("/api/ws/radio") as ws:
        resp = client.post(
            "/api/admin/playback/next", json={"genre_id": gid}
        )
        assert resp.status_code == 200
        message = ws.receive_json()
    assert message["track"]["youtube_video_id"] == "b"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_ws.py::test_radio_pushes_skip -v`
Expected: FAIL — the socket blocks waiting for a frame that never arrives (test times out) because only `play` pushes.

- [ ] **Step 3: Add pushes to the other endpoints**

In `backend/app/routers/admin.py`, add
`notify_radio(build_now(session, utcnow()).model_dump())` immediately before the
`return {"status": "ok"}` of each of these handlers:

```python
@router.post("/playback/next", dependencies=[Depends(require_admin)])
def playback_next(body: GenreRefIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        skip(session, body.genre_id, "next")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.post("/playback/prev", dependencies=[Depends(require_admin)])
def playback_prev(body: GenreRefIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        skip(session, body.genre_id, "prev")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.post("/playback/auto", dependencies=[Depends(require_admin)])
def playback_auto(session: Session = Depends(get_session)) -> dict:
    set_auto(session)
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.put("/genres/{genre_id}/order", dependencies=[Depends(require_admin)])
def set_genre_order(
    genre_id: int, body: OrderIn, session: Session = Depends(get_session)
) -> dict:
    if session.get(Genre, genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    set_order(session, genre_id, body.video_ids)
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/test_ws.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite**

Run (from `backend/`): `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_ws.py
git commit -m "feat: push next/prev/auto/order changes to radio listeners"
```

---

## Task 4: Subscribe to the radio socket in `useBroadcast`

**Files:**
- Modify: `frontend/src/hooks/useBroadcast.ts`
- Modify: `frontend/src/test/setup.ts`
- Test: `frontend/src/hooks/useBroadcast.dom.test.ts`

- [ ] **Step 1: Add a default WebSocket stub to the test setup**

Append to `frontend/src/test/setup.ts`:

```ts
class StubWebSocket {
  static readonly OPEN = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(readonly url: string) {}
  close() {}
}
(globalThis as unknown as { WebSocket: unknown }).WebSocket = StubWebSocket;
```

- [ ] **Step 2: Write the failing tests**

Append to `frontend/src/hooks/useBroadcast.dom.test.ts`:

```ts
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
}

describe("useBroadcast (radio socket)", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("opens a radio socket on mount", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    renderHook(() => useBroadcast());
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(FakeWebSocket.instances[0].url).toContain("/api/ws/radio");
  });

  it("applies a pushed frame immediately", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          genre: null,
          track: {
            youtube_video_id: "b",
            title: "B",
            artist: "A",
            thumbnail_url: "",
            duration_seconds: 200,
            position: 1,
          },
          offset_seconds: 0,
          server_time: "2026-01-01T00:00:00+00:00",
          source: "manual",
        }),
      });
    });
    await waitFor(() =>
      expect(result.current.state?.track?.youtube_video_id).toBe("b"),
    );
    expect(result.current.state?.source).toBe("manual");
    expect(result.current.state?.rttMs).toBe(0);
  });

  it("ignores malformed socket frames", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state).not.toBeNull());
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({ data: "not-json" });
    });
    expect(result.current.state?.source).toBe("none");
  });

  it("reconnects after the socket closes", () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    renderHook(() => useBroadcast());
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `frontend/`): `npm test -- src/hooks/useBroadcast.dom.test.ts`
Expected: FAIL — no socket is created, so `FakeWebSocket.instances` is empty.

- [ ] **Step 4: Add the socket to the hook**

Replace `frontend/src/hooks/useBroadcast.ts` with:

```ts
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BroadcastNow, Genre, Track } from "../types";

export const POLL_MS = 5000;
const MIN_RETRY_MS = 1000;
const MAX_RETRY_MS = 30000;

export interface BroadcastState {
  track: Track | null;
  genre: Genre | null;
  source: string;
  /** Seconds into the current track as reported by the server. */
  offset: number;
  /** `Date.now()` when the state was received. */
  fetchedAt: number;
  /** Approximate round-trip time in milliseconds. */
  rttMs: number;
}

export function radioSocketUrl(protocol: string, host: string): string {
  const scheme = protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${host}/api/ws/radio`;
}

function toState(data: BroadcastNow, rttMs: number): BroadcastState {
  return {
    track: data.track,
    genre: data.genre,
    source: data.source,
    offset: data.offset_seconds,
    fetchedAt: Date.now(),
    rttMs,
  };
}

export function useBroadcast(): {
  state: BroadcastState | null;
  failed: boolean;
  refresh: () => void;
} {
  const [state, setState] = useState<BroadcastState | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const load = async () => {
      const started = Date.now();
      try {
        const data = await api.now();
        if (cancelled) return;
        setFailed(false);
        setState(toState(data, Date.now() - started));
      } catch {
        if (!cancelled) setFailed(true);
        // keep the last known state; the next tick retries
      }
    };

    void load();
    timer = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [tick]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let reconnectTimer: number | null = null;
    let retryDelay = MIN_RETRY_MS;

    const scheduleReconnect = () => {
      if (closed) return;
      const jitter = 0.85 + Math.random() * 0.3;
      const delay = Math.min(MAX_RETRY_MS, retryDelay) * jitter;
      retryDelay = Math.min(MAX_RETRY_MS, retryDelay * 2);
      reconnectTimer = window.setTimeout(connect, delay);
    };

    function connect() {
      if (closed) return;
      let next: WebSocket;
      try {
        next = new WebSocket(radioSocketUrl(location.protocol, location.host));
      } catch {
        scheduleReconnect();
        return;
      }
      socket = next;
      next.onopen = () => {
        retryDelay = MIN_RETRY_MS;
      };
      next.onmessage = (event) => {
        if (closed) return;
        try {
          const data = JSON.parse(event.data) as BroadcastNow;
          setFailed(false);
          setState(toState(data, 0));
        } catch {
          // ignore malformed frames
        }
      };
      next.onclose = () => {
        if (socket === next) socket = null;
        scheduleReconnect();
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return { state, failed, refresh };
}
```

- [ ] **Step 5: Run tests and typecheck**

Run (from `frontend/`): `npm test -- src/hooks/useBroadcast.dom.test.ts`
Expected: all pass.

Run (from `frontend/`): `npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Run the full frontend suite**

Run (from `frontend/`): `npm test`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useBroadcast.ts frontend/src/test/setup.ts frontend/src/hooks/useBroadcast.dom.test.ts
git commit -m "feat: apply pushed radio updates in useBroadcast"
```

---

## Task 5: Changelog and end-to-end verification

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Add the changelog entry**

Prepend after the `# Changelog` intro (most recent first) in `docs/changelog.md`:

```markdown
## 2026-10-07 — Instant manual playback on the radio page

- Starting a track from the admin Now Playing panel (Play / Next / Prev / Auto /
  queue reorder) now reaches already-connected listeners over a new
  `/api/ws/radio` WebSocket, so the radio switches immediately instead of
  waiting up to 5s for the next poll. A manually started track begins at 0:00
  for connected listeners; the 5s poll remains as a fallback. New visitors
  still join at the live offset.
- Files touched:
  - `backend/app/routers/now.py`, `backend/app/routers/ws.py`,
    `backend/app/routers/admin.py`
  - `backend/tests/test_now.py`, `backend/tests/test_ws.py` (tests)
  - `frontend/src/hooks/useBroadcast.ts`, `frontend/src/test/setup.ts`
  - `frontend/src/hooks/useBroadcast.dom.test.ts` (tests)
  - `docs/changelog.md`, `docs/superpowers/specs/2026-10-07-instant-manual-play-design.md` (docs)
- **Container restart required: `docker compose up -d --build backend frontend`**
- Verification: `python -m pytest -q` (all pass), `npm run typecheck` (pass),
  `npm test` (all pass).
```

- [ ] **Step 2: Build both containers**

Run (from repo root): `docker compose up -d --build backend frontend`
Expected: both services rebuild and recreate without error.

- [ ] **Step 3: Manual verification**

Open the public radio page in one browser tab and `/admin` in another. Log in,
open **Now Playing**, and click **Play** on a queue track that is not currently
playing. Confirm the radio switches to that track and starts at 0:00 within a
fraction of a second (hard-refresh the radio tab first with Ctrl+Shift+R).

- [ ] **Step 4: Commit**

```bash
git add docs/changelog.md docs/superpowers/specs/2026-10-07-instant-manual-play-design.md
git commit -m "docs: changelog for instant manual playback"
```

---

## Self-Review Notes

- **Spec coverage:** §6.1 `build_now` → Task 1; §6.2/6.3 WebSocket + push helper
  → Task 2; §6.4 trigger points → Tasks 2–3; §7.1 `useBroadcast` socket → Task 4;
  §8 testing → Tasks 1–4; §9 config unchanged; changelog → Task 5. §3 non-goals
  (no passive-transition push, no schema change) are respected by the plan.
- **Type consistency:** `build_now(session, ts)`, `notify_radio(payload)`,
  `radioSocketUrl(protocol, host)`, and `toState(data, rttMs)` are used with the
  same signatures everywhere they appear.
- **Payload shape:** `NowOut.model_dump()` yields exactly the `BroadcastNow`
  fields (`genre`, `track`, `offset_seconds`, `server_time`, `source`) that
  `toState` reads.
