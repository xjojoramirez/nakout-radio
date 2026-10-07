# Live Broadcast Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Nakout Radio into a single server-driven broadcast where every listener hears the same track at the same second, with muted autoplay on load plus a remembered mute/volume control.

**Architecture:** The backend stores a "broadcast anchor" in the existing `Setting` table and lazily computes the live station, track, and elapsed offset as a pure function of server time (no background worker). The frontend polls `GET /api/now`, seeks the YouTube player to the server offset, corrects drift, and exposes only mute/volume controls.

**Tech Stack:** Python 3 / FastAPI / SQLModel + SQLite / Alembic (backend); React 18 + TypeScript + Vite + Vitest (frontend); YouTube IFrame Player API.

**Spec:** `docs/superpowers/specs/2026-10-06-live-broadcast-sync-design.md`

> **Repository note:** This workspace is not currently a git repository. The `git add`/`git commit` steps below assume one is initialized (`git init`). If you are not using version control, skip those steps.

---

## File Structure

**Backend**
- Create `backend/app/broadcast.py` — broadcast state (`BroadcastState`), pure `advance()`, DB wiring (`get_current`), and `utcnow`.
- Create `backend/app/routers/now.py` — `GET /api/now`.
- Modify `backend/app/schemas.py` — add `NowOut`; extend `CurrentStationOut`.
- Modify `backend/app/routers/schedule.py` — delegate `/api/schedule/now` to the broadcast.
- Modify `backend/app/main.py` — mount the `now` router.
- Create `backend/tests/test_broadcast.py` — pure advance unit tests.
- Create `backend/tests/test_now.py` — endpoint + DB wiring tests.
- Modify `backend/tests/test_stations.py` — default-fallback source becomes `"default"`.

**Frontend**
- Modify `frontend/src/types.ts` — add `BroadcastNow`.
- Modify `frontend/src/api/client.ts` — add `now()`.
- Modify `frontend/src/api/client.test.ts` — test `now()`.
- Create `frontend/src/hooks/useBroadcast.ts` — poll `/api/now`.
- Create `frontend/src/hooks/useBroadcast.dom.test.ts`.
- Delete `frontend/src/hooks/useSchedule.ts` and `frontend/src/hooks/useSchedule.dom.test.ts`.
- Rewrite `frontend/src/hooks/useYouTubePlayer.ts` — join-at-offset, drift correction, mute/volume.
- Rewrite `frontend/src/hooks/useYouTubePlayer.dom.test.ts`.
- Rewrite `frontend/src/pages/RadioPage.tsx` — remove dial/override/prev/next/shuffle; add mute + volume.
- Rewrite `frontend/src/pages/RadioPage.dom.test.tsx`.
- Modify `frontend/src/styles/vintage.css` — style the volume slider.

---

## Task 1: Pure broadcast advance function

**Files:**
- Create: `backend/app/broadcast.py`
- Test: `backend/tests/test_broadcast.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_broadcast.py`:

```python
from datetime import datetime, timedelta

from app.broadcast import BroadcastState, advance


def _state(station_id, track_ids, durations, index, started_at):
    return BroadcastState(
        station_id=station_id,
        track_ids=list(track_ids),
        durations=list(durations),
        index=index,
        started_at=started_at,
    )


def _desired_at(mapping):
    def resolver(at):
        chosen = None
        for at_dt, sid in mapping:
            if at >= at_dt:
                chosen = sid
        return chosen

    return resolver


START = datetime(2026, 1, 1, 0, 0, 0)


def test_mid_track_does_not_advance():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state, START + timedelta(seconds=30), lambda at: 1, lambda sid: ([10, 11], [100, 100])
    )
    assert result.index == 0
    assert result.started_at == START


def test_crosses_boundary_to_next_track():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state, START + timedelta(seconds=100), lambda at: 1, lambda sid: ([10, 11], [100, 100])
    )
    assert result.index == 1
    assert result.started_at == START + timedelta(seconds=100)


def test_catches_up_after_long_absence():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state, START + timedelta(seconds=250), lambda at: 1, lambda sid: ([10, 11], [100, 100])
    )
    # 100s -> track 1, 200s -> loop to track 0, next boundary is 300s.
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=200)


def test_loops_and_rebuilds_snapshot():
    state = _state(1, [10, 11], [100, 100], 0, START)
    calls = []

    def snapshot(sid):
        calls.append(sid)
        return ([10, 11], [100, 100])

    result = advance(state, START + timedelta(seconds=200), lambda at: 1, snapshot)
    assert result.index == 0
    assert calls == [1]


def test_station_switch_waits_for_song_end():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=50), 2)])
    table = {1: ([10], [100]), 2: ([20, 21], [100, 100])}
    result = advance(
        state, START + timedelta(seconds=120), desired, lambda sid: table[sid]
    )
    assert result.station_id == 2
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=100)


def test_empty_station_stays_off_air():
    state = _state(1, [], [], 0, START)
    result = advance(
        state, START + timedelta(seconds=10), lambda at: 1, lambda sid: ([], [])
    )
    assert result.track_ids == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_broadcast.py -v` (from `backend/`)
Expected: FAIL with `ModuleNotFoundError: No module named 'app.broadcast'` / `ImportError: cannot import name 'BroadcastState'`.

- [ ] **Step 3: Write the minimal implementation**

Create `backend/app/broadcast.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from app.scheduler import resolve_station_id  # noqa: F401  (used in Task 2)


def utcnow() -> datetime:
    """Naive UTC, matching models._utcnow."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class BroadcastState:
    station_id: int | None
    track_ids: list[int]
    durations: list[int]
    index: int
    started_at: datetime


def advance(
    state: BroadcastState,
    now: datetime,
    desired: Callable[[datetime], int | None],
    snapshot: Callable[[int], tuple[list[int], list[int]]],
) -> BroadcastState:
    """Advance ``state`` forward through finished tracks.

    ``desired(at)`` returns the station that should be live at time ``at``.
    ``snapshot(station_id)`` returns that station's ``(track_ids, durations)``.
    Boundary times are evaluated at the boundary itself so the result is correct
    even after a long gap with no requests. Does not mutate the input.
    """
    state = replace(
        state,
        track_ids=list(state.track_ids),
        durations=list(state.durations),
    )
    for _ in range(10000):
        if not state.track_ids:
            target = desired(state.started_at)
            if target is None or target == state.station_id:
                return state
            state.station_id = target
            state.track_ids, state.durations = snapshot(target)
            state.index = 0
            continue

        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration)
        if now < end:
            return state

        target = desired(end)
        if target is not None and target != state.station_id:
            state.station_id = target
            state.track_ids, state.durations = snapshot(target)
            state.index = 0
            state.started_at = end
        else:
            state.index += 1
            state.started_at = end
            if state.index >= len(state.track_ids):
                state.index = 0
                state.track_ids, state.durations = snapshot(state.station_id)
    return state
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_broadcast.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_broadcast.py
git commit -m "feat(broadcast): add pure broadcast advance function"
```

---

## Task 2: Broadcast DB wiring and `/api/now` endpoint

**Files:**
- Modify: `backend/app/broadcast.py` (append DB wiring)
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/now.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_now.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_now.py`:

```python
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import create_app
from app.models import Playlist, ScheduleSlot, Station, TrackCache


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _client(engine):
    from fastapi.testclient import TestClient

    def override():
        with Session(engine) as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def _seed_station(session, slug, *, default=False, video="vid", duration=200):
    st = Station(name=slug.title(), slug=slug, is_default=default)
    session.add(st)
    session.commit()
    session.refresh(st)
    pl = Playlist(station_id=st.id, youtube_playlist_id=f"PL-{slug}")
    session.add(pl)
    session.commit()
    session.refresh(pl)
    session.add(
        TrackCache(
            playlist_id=pl.id,
            youtube_video_id=video,
            title="T",
            artist="A",
            position=0,
            duration_seconds=duration,
        )
    )
    session.commit()
    return st


def test_now_returns_track_offset_and_server_time(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_station(s, "morning", default=True)
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "default"
    assert body["station"]["slug"] == "morning"
    assert body["track"]["youtube_video_id"] == "vid"
    assert 0 <= body["offset_seconds"] < 200
    assert body["server_time"]


def test_now_off_air(tmp_path):
    engine = _engine(tmp_path)
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "none"
    assert body["station"] is None
    assert body["track"] is None
    assert body["offset_seconds"] == 0


def test_now_uses_matching_slot(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        night = _seed_station(s, "night", video="nv")
        for start, end in (("00:00", "12:00"), ("12:00", "00:00")):
            s.add(
                ScheduleSlot(
                    station_id=night.id,
                    days_of_week=[0, 1, 2, 3, 4, 5, 6],
                    start_time=start,
                    end_time=end,
                )
            )
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "schedule"
    assert body["station"]["slug"] == "night"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_now.py -v`
Expected: FAIL — `404` for `/api/now` (endpoint missing) or `ImportError`.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas.py`, add after `CurrentStationOut`:

```python
class NowOut(BaseModel):
    station: StationOut | None
    track: TrackOut | None
    offset_seconds: int
    server_time: str
    source: str
```

- [ ] **Step 4: Append DB wiring to `backend/app/broadcast.py`**

Append to `backend/app/broadcast.py`:

```python
import json
from threading import Lock
from typing import NamedTuple
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.config import get_settings
from app.models import ScheduleSlot, Setting, Station, TrackCache
from app.routers.stations import tracks_for_station
from app.scheduler import matches

STATE_KEY = "broadcast_state"
_lock = Lock()


class NowState(NamedTuple):
    station: Station | None
    track: TrackCache | None
    offset_seconds: int
    source: str


def _resolve(session: Session, at_utc: datetime) -> tuple[int | None, bool]:
    settings = get_settings()
    local = at_utc.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo(settings.station_tz)
    )
    default = session.exec(
        select(Station).where(Station.is_default.is_(True))
    ).first()
    slots = session.exec(select(ScheduleSlot)).all()
    rows = [(s.station_id, s.days_of_week, s.start_time, s.end_time) for s in slots]
    matched = [s for s in rows if matches(s[1], s[2], s[3], local)]
    station_id = resolve_station_id(
        rows, local, default.id if default else None
    )
    return station_id, bool(matched)


def _desired(session: Session, at_utc: datetime) -> int | None:
    station_id, _ = _resolve(session, at_utc)
    if station_id is not None and tracks_for_station(session, station_id):
        return station_id
    default = session.exec(
        select(Station).where(Station.is_default.is_(True))
    ).first()
    if default is not None and tracks_for_station(session, default.id):
        return default.id
    return station_id


def _snapshot(session: Session, station_id: int) -> tuple[list[int], list[int]]:
    tracks = tracks_for_station(session, station_id)
    return [int(t.id) for t in tracks], [t.duration_seconds or 1 for t in tracks]


def _load(session: Session) -> BroadcastState | None:
    row = session.get(Setting, STATE_KEY)
    if row is None or not row.value:
        return None
    data = json.loads(row.value)
    sid = data.get("station_id")
    return BroadcastState(
        station_id=int(sid) if sid is not None else None,
        track_ids=[int(x) for x in data["track_ids"]],
        durations=[int(x) for x in data["durations"]],
        index=int(data["index"]),
        started_at=datetime.fromisoformat(data["started_at_utc"]),
    )


def _save(session: Session, state: BroadcastState) -> None:
    payload = json.dumps(
        {
            "station_id": state.station_id,
            "track_ids": state.track_ids,
            "durations": state.durations,
            "index": state.index,
            "started_at_utc": state.started_at.isoformat(),
        }
    )
    session.merge(Setting(key=STATE_KEY, value=payload))
    session.commit()


def _init(session: Session, now: datetime) -> BroadcastState:
    station_id = _desired(session, now)
    if station_id is None:
        return BroadcastState(None, [], [], 0, now)
    ids, durations = _snapshot(session, station_id)
    return BroadcastState(station_id, ids, durations, 0, now)


def get_current(session: Session, now: datetime | None = None) -> NowState:
    now = now or utcnow()
    with _lock:
        state = _load(session)
        initialized = state is None
        if state is None:
            state = _init(session, now)
        before = state
        state = advance(
            state,
            now,
            lambda at: _desired(session, at),
            lambda sid: _snapshot(session, sid),
        )
        if initialized or state != before:
            _save(session, state)

    if state.station_id is None or not state.track_ids:
        return NowState(None, None, 0, "none")
    track = session.get(TrackCache, state.track_ids[state.index])
    station = session.get(Station, state.station_id)
    if track is None or station is None:
        return NowState(None, None, 0, "none")
    duration = state.durations[state.index] or 1
    offset = int((now - state.started_at).total_seconds())
    offset = max(0, min(offset, duration - 1))
    _, from_schedule = _resolve(session, now)
    return NowState(station, track, offset, "schedule" if from_schedule else "default")
```

- [ ] **Step 5: Create the router**

Create `backend/app/routers/now.py`:

```python
from datetime import timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.broadcast import get_current, utcnow
from app.db import get_session
from app.routers.stations import tracks_for_station
from app.schemas import NowOut, StationOut, TrackOut

router = APIRouter(prefix="/api", tags=["now"])


@router.get("/now", response_model=NowOut)
def now(session: Session = Depends(get_session)) -> NowOut:
    ts = utcnow()
    state = get_current(session, ts)
    station_out = None
    if state.station is not None:
        station_out = StationOut(
            id=state.station.id,
            name=state.station.name,
            slug=state.station.slug,
            is_default=state.station.is_default,
            track_count=len(tracks_for_station(session, state.station.id)),
        )
    return NowOut(
        station=station_out,
        track=TrackOut.model_validate(state.track) if state.track else None,
        offset_seconds=state.offset_seconds,
        server_time=ts.replace(tzinfo=timezone.utc).isoformat(),
        source=state.source,
    )
```

- [ ] **Step 6: Mount the router**

In `backend/app/main.py`, change the router import and mounts:

```python
    from app.routers import admin, now, queue, schedule, stations, ws

    app.include_router(stations.router)
    app.include_router(schedule.router)
    app.include_router(now.router)
    app.include_router(admin.router)
    app.include_router(ws.router)
    app.include_router(queue.router)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_now.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Commit**

```bash
git add backend/app/broadcast.py backend/app/schemas.py backend/app/routers/now.py backend/app/main.py backend/tests/test_now.py
git commit -m "feat(api): add GET /api/now broadcast endpoint"
```

---

## Task 3: Delegate the schedule endpoint and update its tests

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/schedule.py`
- Modify: `backend/tests/test_stations.py:135-143`

- [ ] **Step 1: Update the fallback test to expect the new source**

In `backend/tests/test_stations.py`, inside `test_schedule_now_falls_back_to_default`, change:

```python
    assert body["source"] == "schedule"
```

to:

```python
    assert body["source"] == "default"
```

(The default station now reports `"default"`; slot matches report `"schedule"`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_stations.py::test_schedule_now_falls_back_to_default -v`
Expected: PASS currently only if implemented — run it *before* Step 3 and it should still pass because `/api/schedule/now` still returns `"schedule"`. This step documents the expected post-change value; the red state appears in Step 4 after the router change if the assertion were still `"schedule"`.

- [ ] **Step 3: Extend `CurrentStationOut`**

In `backend/app/schemas.py`, replace `CurrentStationOut` with:

```python
class CurrentStationOut(BaseModel):
    station: StationOut | None
    track: TrackOut | None
    cursor: str | None = None
    source: str
    offset_seconds: int = 0
    server_time: str | None = None
```

- [ ] **Step 4: Delegate the schedule router**

Replace the body of `backend/app/routers/schedule.py` with:

```python
from datetime import timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.broadcast import get_current, utcnow
from app.db import get_session
from app.routers.stations import tracks_for_station
from app.schemas import CurrentStationOut, StationOut, TrackOut

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/now", response_model=CurrentStationOut)
def schedule_now(session: Session = Depends(get_session)) -> CurrentStationOut:
    ts = utcnow()
    state = get_current(session, ts)
    station_out = None
    if state.station is not None:
        station_out = StationOut(
            id=state.station.id,
            name=state.station.name,
            slug=state.station.slug,
            is_default=state.station.is_default,
            track_count=len(tracks_for_station(session, state.station.id)),
        )
    return CurrentStationOut(
        station=station_out,
        track=TrackOut.model_validate(state.track) if state.track else None,
        cursor=None,
        source=state.source,
        offset_seconds=state.offset_seconds,
        server_time=ts.replace(tzinfo=timezone.utc).isoformat(),
    )
```

- [ ] **Step 5: Run the schedule tests to verify they pass**

Run: `python -m pytest tests/test_stations.py -v`
Expected: PASS (all, including the updated fallback assertion).

- [ ] **Step 6: Run the full backend suite**

Run: `python -m pytest -q`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/schedule.py backend/tests/test_stations.py
git commit -m "feat(schedule): delegate /api/schedule/now to the broadcast engine"
```

---

## Task 4: Frontend API type and client method

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/api/client.test.ts` (inside the `describe` block, before its closing `});`):

```ts
  it("GETs the live broadcast", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          station: null,
          track: null,
          offset_seconds: 0,
          server_time: "2026-01-01T00:00:00+00:00",
          source: "none",
        }),
        { status: 200 },
      ),
    );
    const result = await api.now();
    expect(spy.mock.calls[0][0]).toBe("/api/now");
    expect(result.source).toBe("none");
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- client` (from `frontend/`)
Expected: FAIL — `api.now is not a function`.

- [ ] **Step 3: Add the type**

In `frontend/src/types.ts`, add after `CurrentStation`:

```ts
export interface BroadcastNow {
  station: Station | null;
  track: Track | null;
  offset_seconds: number;
  server_time: string;
  source: string;
}
```

- [ ] **Step 4: Add the client method**

In `frontend/src/api/client.ts`, add `BroadcastNow` to the type import list:

```ts
import type {
  AddedPlaylist,
  BroadcastNow,
  ChannelPlaylist,
  ChannelSource,
  CurrentStation,
  Station,
  StationDetail,
  Track,
} from "../types";
```

Then add to the `api` object, immediately after `scheduleNow`:

```ts
  now: () => request<BroadcastNow>("/now"),
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- client`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(frontend): add /api/now client method"
```

---

## Task 5: `useBroadcast` hook, remove `useSchedule`

**Files:**
- Create: `frontend/src/hooks/useBroadcast.ts`
- Create: `frontend/src/hooks/useBroadcast.dom.test.ts`
- Delete: `frontend/src/hooks/useSchedule.ts`
- Delete: `frontend/src/hooks/useSchedule.dom.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useBroadcast.dom.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useBroadcast } from "./useBroadcast";

function nowResponse(overrides: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      station: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
      ...overrides,
    }),
    { status: 200 },
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useBroadcast", () => {
  it("loads the broadcast on mount", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(nowResponse({ source: "schedule" })),
    );
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state?.source).toBe("schedule"));
  });

  it("records the fetch time and round-trip time", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state).not.toBeNull());
    expect(result.current.state?.fetchedAt).toBeGreaterThan(0);
    expect(result.current.state?.rttMs).toBeGreaterThanOrEqual(0);
  });

  it("polls again after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(nowResponse());
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useBroadcast());
    await act(async () => {
      await Promise.resolve();
    });
    const initial = fetchMock.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });
    expect(fetchMock.mock.calls.length).toBeGreaterThan(initial);
  });

  it("keeps the previous state when a poll fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(nowResponse({ source: "schedule" }))
      .mockRejectedValueOnce(new Error("boom"));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state?.source).toBe("schedule"));
    await act(async () => {
      result.current.refresh();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.state?.source).toBe("schedule");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- useBroadcast`
Expected: FAIL — cannot resolve `./useBroadcast`.

- [ ] **Step 3: Write the hook**

Create `frontend/src/hooks/useBroadcast.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Station, Track } from "../types";

export const POLL_MS = 5000;

export interface BroadcastState {
  track: Track | null;
  station: Station | null;
  source: string;
  /** Seconds into the current track as reported by the server. */
  offset: number;
  /** `Date.now()` when the response resolved. */
  fetchedAt: number;
  /** Approximate round-trip time in milliseconds. */
  rttMs: number;
}

export function useBroadcast(): {
  state: BroadcastState | null;
  refresh: () => void;
} {
  const [state, setState] = useState<BroadcastState | null>(null);
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
        setState({
          track: data.track,
          station: data.station,
          source: data.source,
          offset: data.offset_seconds,
          fetchedAt: Date.now(),
          rttMs: Date.now() - started,
        });
      } catch {
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

  return { state, refresh };
}
```

- [ ] **Step 4: Delete the obsolete hook and test**

Delete `frontend/src/hooks/useSchedule.ts` and `frontend/src/hooks/useSchedule.dom.test.ts`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- useBroadcast`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useBroadcast.ts frontend/src/hooks/useBroadcast.dom.test.ts
git rm frontend/src/hooks/useSchedule.ts frontend/src/hooks/useSchedule.dom.test.ts
git commit -m "feat(frontend): add useBroadcast, remove useSchedule"
```

---

## Task 6: Rewrite `useYouTubePlayer`

**Files:**
- Rewrite: `frontend/src/hooks/useYouTubePlayer.ts`
- Rewrite: `frontend/src/hooks/useYouTubePlayer.dom.test.ts`

- [ ] **Step 1: Write the failing test**

Replace `frontend/src/hooks/useYouTubePlayer.dom.test.ts` with:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BroadcastState } from "./useBroadcast";
import { useYouTubePlayer } from "./useYouTubePlayer";

function broadcast(overrides: Partial<BroadcastState> = {}): BroadcastState {
  return {
    track: {
      youtube_video_id: "a",
      title: "a",
      artist: "",
      thumbnail_url: "",
      duration_seconds: 200,
      position: 0,
    },
    station: null,
    source: "schedule",
    offset: 0,
    fetchedAt: Date.now(),
    rttMs: 0,
    ...overrides,
  };
}

describe("useYouTubePlayer", () => {
  let players: any[];

  beforeEach(() => {
    window.localStorage.clear();
    players = [];
    class FakePlayer {
      opts: any;
      loadVideoById = vi.fn();
      playVideo = vi.fn();
      pauseVideo = vi.fn();
      mute = vi.fn();
      unMute = vi.fn();
      setVolume = vi.fn();
      seekTo = vi.fn();
      getPlayerState = vi.fn(() => 1);
      getCurrentTime = vi.fn(() => 0);
      destroy = vi.fn();
      constructor(_el: string, opts: any) {
        this.opts = opts;
        players.push(this);
      }
    }
    (window as unknown as { YT: unknown }).YT = {
      PlayerState: { PLAYING: 1, ENDED: 8 },
      Player: FakePlayer,
    };
  });

  afterEach(() => {
    delete (window as unknown as { YT?: unknown }).YT;
    vi.useRealTimers();
  });

  it("creates a muted autoplay player for the live track", async () => {
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), vi.fn()));
    await waitFor(() => expect(players.length).toBe(1));
    expect(players[0].opts.videoId).toBe("a");
    expect(players[0].opts.playerVars.autoplay).toBe(1);
    expect(players[0].opts.playerVars.mute).toBe(1);
  });

  it("does not create a player while off air", async () => {
    renderHook(() =>
      useYouTubePlayer("yt-player", broadcast({ track: null }), vi.fn()),
    );
    await Promise.resolve();
    expect(players.length).toBe(0);
  });

  it("loads a changed track at the broadcast offset", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    rerender({
      b: broadcast({
        track: { ...broadcast().track!, youtube_video_id: "b" },
        offset: 12,
      }),
    });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "b",
        startSeconds: expect.any(Number),
      }),
    );
  });

  it("seeks when the broadcast offset drifts from playback", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    players[0].getCurrentTime = vi.fn(() => 0);
    rerender({ b: broadcast({ offset: 30, fetchedAt: Date.now() }) });
    await waitFor(() => expect(players[0].seekTo).toHaveBeenCalled());
  });

  it("requests a resync when the track ends", async () => {
    const onEnded = vi.fn();
    renderHook(() => useYouTubePlayer("yt-player", broadcast(), onEnded));
    await waitFor(() => expect(players.length).toBe(1));
    act(() => {
      players[0].opts.events.onStateChange({ data: 8 });
    });
    expect(onEnded).toHaveBeenCalled();
  });

  it("starts muted on first visit", () => {
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    expect(result.current.muted).toBe(true);
  });

  it("toggleMute updates state and storage", async () => {
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await waitFor(() => expect(players.length).toBe(1));
    act(() => {
      result.current.toggleMute();
    });
    await waitFor(() => expect(result.current.muted).toBe(false));
    expect(window.localStorage.getItem("nakout.muted")).toBe("false");
  });

  it("setVolume clamps, persists, and unmutes", async () => {
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await waitFor(() => expect(players.length).toBe(1));
    act(() => {
      result.current.setVolume(150);
    });
    await waitFor(() => expect(result.current.volume).toBe(100));
    expect(window.localStorage.getItem("nakout.volume")).toBe("100");
    expect(result.current.muted).toBe(false);
  });

  it("falls back to muted when autoplay with sound is blocked", async () => {
    vi.useFakeTimers();
    window.localStorage.setItem("nakout.muted", "false");
    const { result } = renderHook(() =>
      useYouTubePlayer("yt-player", broadcast(), vi.fn()),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    players[0].getPlayerState.mockReturnValue(0);
    act(() => {
      players[0].opts.events.onReady();
    });
    act(() => {
      vi.advanceTimersByTime(1600);
    });
    expect(players[0].mute).toHaveBeenCalled();
    expect(result.current.muted).toBe(true);
    expect(window.localStorage.getItem("nakout.muted")).toBe("true");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- useYouTubePlayer`
Expected: FAIL — the current hook has a different signature (`initial`, `containerId`, `options`).

- [ ] **Step 3: Rewrite the hook**

Replace `frontend/src/hooks/useYouTubePlayer.ts` with:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import type { Track } from "../types";
import type { BroadcastState } from "./useBroadcast";

const VOLUME_KEY = "nakout.volume";
const MUTED_KEY = "nakout.muted";
const DRIFT_THRESHOLD = 3;
const AUTOPLAY_FALLBACK_MS = 1500;

interface YTPlayer {
  loadVideoById: (opts: { videoId: string; startSeconds?: number }) => void;
  playVideo: () => void;
  pauseVideo: () => void;
  mute: () => void;
  unMute: () => void;
  setVolume: (v: number) => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  getPlayerState: () => number;
  getCurrentTime: () => number;
  destroy: () => void;
}

interface YTNamespace {
  Player: new (element: string | HTMLElement, options: unknown) => YTPlayer;
  PlayerState: { PLAYING: number; ENDED: number };
}

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<void> | null = null;

function loadIframeApi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.YT?.Player) return Promise.resolve();
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    const existing = document.querySelector(
      'script[src="https://www.youtube.com/iframe_api"]',
    );
    if (!existing) {
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      document.body.appendChild(script);
    }
  });
  return apiPromise;
}

export function storedVolume(): number {
  const raw = window.localStorage.getItem(VOLUME_KEY);
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 70;
}

export function storedMuted(): boolean {
  return window.localStorage.getItem(MUTED_KEY) !== "false";
}

export function liveTarget(broadcast: BroadcastState, now = Date.now()): number {
  const elapsed = (now - broadcast.fetchedAt) / 1000;
  return Math.max(0, broadcast.offset + broadcast.rttMs / 2000 + elapsed);
}

export interface PlayerControls {
  ready: boolean;
  playing: boolean;
  progress: number;
  error: boolean;
  muted: boolean;
  volume: number;
  track: Track | null;
  toggleMute: () => void;
  setVolume: (value: number) => void;
}

export function useYouTubePlayer(
  containerId: string,
  broadcast: BroadcastState | null,
  onEnded: () => void,
): PlayerControls {
  const playerRef = useRef<YTPlayer | null>(null);
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;
  const broadcastRef = useRef(broadcast);
  broadcastRef.current = broadcast;

  const [apiReady, setApiReady] = useState(false);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(false);
  const [muted, setMuted] = useState(() => storedMuted());
  const [volume, setVolumeState] = useState(() => storedVolume());

  const volumeRef = useRef(volume);
  volumeRef.current = volume;
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const currentVideoRef = useRef<string | null>(null);

  const hasTrack = broadcast?.track != null;

  useEffect(() => {
    let cancelled = false;
    loadIframeApi().then(() => {
      if (!cancelled) setApiReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!apiReady || !hasTrack || playerRef.current || !window.YT) return;
    const current = broadcastRef.current;
    if (!current?.track) return;
    const initialId = current.track.youtube_video_id;
    const start = liveTarget(current);
    const yt = window.YT;
    setError(false);
    const player = new yt.Player(containerId, {
      height: "1",
      width: "1",
      videoId: initialId,
      playerVars: {
        autoplay: 1,
        mute: 1,
        controls: 0,
        disablekb: 1,
        playsinline: 1,
      },
      events: {
        onReady: () => {
          setReady(true);
          player.setVolume(volumeRef.current);
          if (mutedRef.current) {
            player.mute();
            player.playVideo();
          } else {
            player.unMute();
            player.playVideo();
            window.setTimeout(() => {
              if (player.getPlayerState() !== yt.PlayerState.PLAYING) {
                player.mute();
                setMuted(true);
                window.localStorage.setItem(MUTED_KEY, "true");
                player.playVideo();
              }
            }, AUTOPLAY_FALLBACK_MS);
          }
        },
        onStateChange: (e: { data: number }) => {
          setPlaying(e.data === yt.PlayerState.PLAYING);
          if (e.data === yt.PlayerState.ENDED) {
            onEndedRef.current();
          }
        },
        onError: () => setError(true),
      },
    });
    playerRef.current = player;
    currentVideoRef.current = initialId;
    return () => {
      player.destroy();
      playerRef.current = null;
      currentVideoRef.current = null;
      setReady(false);
      setPlaying(false);
    };
  }, [apiReady, hasTrack, containerId]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !broadcast?.track) return;
    const videoId = broadcast.track.youtube_video_id;
    const target = liveTarget(broadcast);
    if (currentVideoRef.current !== videoId) {
      currentVideoRef.current = videoId;
      setError(false);
      player.loadVideoById({ videoId, startSeconds: target });
    } else if (Math.abs(player.getCurrentTime() - target) > DRIFT_THRESHOLD) {
      player.seekTo(target, true);
    }
  }, [broadcast]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;
    player.setVolume(volume);
    if (muted || volume === 0) player.mute();
    else player.unMute();
  }, [volume, muted, ready, hasTrack]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const player = playerRef.current;
      if (!player) return;
      setProgress(player.getCurrentTime());
      const current = broadcastRef.current;
      if (current) {
        const target = liveTarget(current);
        if (Math.abs(player.getCurrentTime() - target) > DRIFT_THRESHOLD) {
          player.seekTo(target, true);
        }
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const setVolume = useCallback((value: number) => {
    const clamped = Math.min(100, Math.max(0, Math.round(value)));
    setVolumeState(clamped);
    window.localStorage.setItem(VOLUME_KEY, String(clamped));
    if (clamped > 0 && mutedRef.current) {
      setMuted(false);
      window.localStorage.setItem(MUTED_KEY, "false");
    }
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((previous) => {
      const next = !previous;
      window.localStorage.setItem(MUTED_KEY, String(next));
      return next;
    });
  }, []);

  return {
    ready,
    playing,
    progress,
    error,
    muted,
    volume,
    track: broadcast?.track ?? null,
    toggleMute,
    setVolume,
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- useYouTubePlayer`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat(player): join broadcast at offset with mute/volume controls"
```

---

## Task 7: Rewrite `RadioPage` and styles

**Files:**
- Rewrite: `frontend/src/pages/RadioPage.tsx`
- Rewrite: `frontend/src/pages/RadioPage.dom.test.tsx`
- Modify: `frontend/src/styles/vintage.css`

- [ ] **Step 1: Write the failing test**

Replace `frontend/src/pages/RadioPage.dom.test.tsx` with:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Track } from "../types";
import { api } from "../api/client";
import { RadioPage } from "./RadioPage";

vi.mock("../api/client", () => ({
  api: { now: vi.fn() },
}));

const mocked = api as unknown as { now: ReturnType<typeof vi.fn> };

function track(id: string): Track {
  return {
    youtube_video_id: id,
    title: id,
    artist: "",
    thumbnail_url: "",
    duration_seconds: 200,
    position: 0,
  };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(_url: string) {
    FakeWebSocket.instances.push(this);
  }
}

class FakePlayer {
  opts: { videoId: string };
  loadVideoById = vi.fn();
  playVideo = vi.fn();
  pauseVideo = vi.fn();
  mute = vi.fn();
  unMute = vi.fn();
  setVolume = vi.fn();
  seekTo = vi.fn();
  getPlayerState = vi.fn(() => 1);
  getCurrentTime = vi.fn(() => 0);
  destroy = vi.fn();
  constructor(_el: string, opts: { videoId: string }) {
    this.opts = opts;
  }
}

beforeEach(() => {
  window.localStorage.clear();
  FakeWebSocket.instances = [];
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  (window as unknown as { YT: unknown }).YT = {
    PlayerState: { PLAYING: 1, ENDED: 8 },
    Player: FakePlayer,
  };
  mocked.now.mockResolvedValue({
    station: {
      id: 1,
      name: "Morning",
      slug: "morning",
      is_default: true,
      track_count: 1,
    },
    track: track("live"),
    offset_seconds: 0,
    server_time: "2026-01-01T00:00:00+00:00",
    source: "schedule",
  });
});

afterEach(() => {
  vi.clearAllMocks();
  delete (globalThis as unknown as { WebSocket?: unknown }).WebSocket;
  delete (window as unknown as { YT?: unknown }).YT;
});

describe("RadioPage", () => {
  it("shows the live broadcast track and station", async () => {
    render(<RadioPage />);
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(await screen.findByText(/Tuned: Morning/)).toBeInTheDocument();
  });

  it("starts muted and offers an UNMUTE control", async () => {
    render(<RadioPage />);
    expect(
      await screen.findByRole("button", { name: "UNMUTE" }),
    ).toBeInTheDocument();
  });

  it("toggles the mute control", async () => {
    render(<RadioPage />);
    fireEvent.click(await screen.findByRole("button", { name: "UNMUTE" }));
    expect(
      await screen.findByRole("button", { name: "MUTE" }),
    ).toBeInTheDocument();
  });

  it("shows off air when nothing is broadcasting", async () => {
    mocked.now.mockResolvedValue({
      station: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
    });
    render(<RadioPage />);
    expect(await screen.findByText(/Off air/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- RadioPage`
Expected: FAIL — the current page renders a station dial and a `TUNE IN` button.

- [ ] **Step 3: Rewrite the page**

Replace `frontend/src/pages/RadioPage.tsx` with:

```tsx
import { NowPlaying } from "../components/NowPlaying";
import { VUMeter } from "../components/VUMeter";
import { useBroadcast } from "../hooks/useBroadcast";
import { useListenerCount } from "../hooks/useListenerCount";
import { useYouTubePlayer } from "../hooks/useYouTubePlayer";

export function RadioPage() {
  const listeners = useListenerCount();
  const { state, refresh } = useBroadcast();
  const player = useYouTubePlayer("yt-player", state, refresh);

  return (
    <div className="radio-cabinet">
      <header className="radio-header">
        <h1>Nakout Radio</h1>
        <span className="listeners">{listeners} listening</span>
      </header>

      <div id="yt-player" className="hidden-player" />

      <NowPlaying
        track={player.error ? null : player.track}
        progress={player.progress}
      />
      <VUMeter playing={player.playing} seed={0} />

      <div className="station-row">
        <span className="tuned-label">
          {state?.station ? `Tuned: ${state.station.name}` : "Off air"}
        </span>
      </div>

      <div className="controls">
        {player.error ? (
          <button type="button" className="tune-in" onClick={refresh}>
            RETRY
          </button>
        ) : (
          <button
            type="button"
            className="tune-in"
            onClick={player.toggleMute}
          >
            {player.muted ? "UNMUTE" : "MUTE"}
          </button>
        )}
        <label className="volume">
          Volume
          <input
            type="range"
            min={0}
            max={100}
            value={player.volume}
            onChange={(event) => player.setVolume(Number(event.target.value))}
            aria-label="Volume"
          />
        </label>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Style the volume control**

Append to `frontend/src/styles/vintage.css`:

```css
.volume {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px;
  color: var(--cream);
  font-size: 0.8rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.volume input[type="range"] {
  width: 120px;
  accent-color: var(--amber);
  cursor: pointer;
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- RadioPage`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx frontend/src/styles/vintage.css
git commit -m "feat(page): broadcast radio with mute and volume controls"
```

---

## Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the backend suite**

Run: `python -m pytest -q` (from `backend/`)
Expected: all tests pass.

- [ ] **Step 2: Run the frontend tests**

Run: `npm test` (from `frontend/`)
Expected: all tests pass.

- [ ] **Step 3: Typecheck the frontend**

Run: `npm run typecheck` (from `frontend/`)
Expected: no errors.

- [ ] **Step 4: Build the frontend**

Run: `npm run build` (from `frontend/`)
Expected: build succeeds.

- [ ] **Step 5: Manual verification (browser)**

Start the backend (`uvicorn app.main:app --reload`) and frontend (`npm run dev`). With a station + playlist configured:
- Open the page in two browser windows at different times; both should show the same track and roughly the same progress.
- The page should start playing muted with no click.
- Clicking UNMUTE should produce sound; the volume slider should change loudness and persist after reload.
- Reload a window a few minutes in; it should jump to the live position, not start the song from 0:00.

- [ ] **Step 6: Commit any test/doc adjustments**

```bash
git add -A
git commit -m "test: verify live broadcast sync end to end"
```

---

## Self-Review Notes

- **Spec coverage:** broadcast engine (Task 1–2), `/api/now` + schedule compatibility (Task 2–3), muted autoplay + mute/volume + persistence (Task 6–7), poll + drift correction (Task 5–6), removing dial/prev/next/shuffle (Task 7), off-air + error handling (Task 2, 7), testing (Tasks 1–8). All covered.
- **Type consistency:** `BroadcastState` fields (`track`, `station`, `source`, `offset`, `fetchedAt`, `rttMs`) are defined in Task 5 and consumed unchanged in Task 6. `NowState` (`station`, `track`, `offset_seconds`, `source`) is defined in Task 2 and used by both `now.py` and `schedule.py`. `liveTarget`/`storedVolume`/`storedMuted` are defined once in Task 6.
- **Placeholder scan:** no TBD/TODO; every code step contains complete code.
