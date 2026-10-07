# Admin Live Control & Playlist Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin take over the live broadcast from the Now Playing tab — play any track now, skip next/prev, return to the schedule, and reorder/shuffle a station's persistent queue.

**Architecture:** Manual mode becomes a first-class field on the stored `BroadcastState`. When manual, `advance()` walks the station snapshot and ignores the schedule; `Auto` re-initializes from the schedule. Per-station play order is stored as a JSON list of `youtube_video_id`s in the `Setting` table, so it survives playlist re-syncs. The admin panel reuses `useBroadcast` (`/api/now`, whose `source` can now be `"manual"`) plus new admin endpoints.

**Tech Stack:** FastAPI, SQLModel, pytest (backend); React 18, TypeScript, Vitest + Testing Library (frontend); native HTML5 drag-and-drop (no new dependency).

> **Note:** This workspace is **not** a git repository. The `Commit` steps below will fail; skip them unless you initialize a repo. They are kept for when the project is under version control.

> **Spec refinement:** The approved spec listed a redundant `GET /api/admin/playback`. `GET /api/now` already returns the live station, track, offset, and `source` (including `"manual"`), so the panel computes the current index itself and this endpoint is dropped (YAGNI).

---

## File Structure

**Backend**
- Modify `backend/app/routers/stations.py` — order load/save + `ordered_tracks_for_station`.
- Modify `backend/app/broadcast.py` — `manual` state, manual advance, order-aware snapshot, control functions.
- Modify `backend/app/schemas.py` — `PlayIn`, `StationRefIn`, `OrderIn`.
- Modify `backend/app/routers/admin.py` — new endpoints.
- Tests: `backend/tests/test_stations.py`, `backend/tests/test_broadcast.py`, `backend/tests/test_live_control.py` (new), `backend/tests/test_admin.py`.

**Frontend**
- Create `frontend/src/utils/queue.ts` + `queue.test.ts`.
- Modify `frontend/src/api/client.ts`.
- Modify `frontend/src/pages/AdminPage.tsx` — pass `stations` to the panel.
- Rewrite `frontend/src/components/admin/NowPlayingPanel.tsx` + its test.
- Modify `frontend/src/styles/vintage.css`.

**Ops**
- Rebuild/redeploy the backend and frontend containers and verify.

---

## Task 1: Per-station order storage & ordered track list

**Files:**
- Modify: `backend/app/routers/stations.py`
- Test: `backend/tests/test_stations.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_stations.py`:

```python
from app.models import Setting
from app.routers.stations import ordered_tracks_for_station


def _seed_ordered(session):
    station = Station(name="Order", slug="order")
    session.add(station)
    session.commit()
    session.refresh(station)
    for pl_idx, vids in enumerate((["a", "b"], ["c", "d"])):
        pl = Playlist(station_id=station.id, youtube_playlist_id=f"PL{pl_idx}")
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
                )
            )
        session.commit()
    return station


def test_default_order_used_without_saved_order(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        station = _seed_ordered(s)
        ids = [t.youtube_video_id for t in ordered_tracks_for_station(s, station.id)]
        assert ids == ["a", "b", "c", "d"]


def test_saved_order_is_applied(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        station = _seed_ordered(s)
        s.merge(Setting(key=f"station_order:{station.id}", value='["d", "b"]'))
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_station(s, station.id)]
        assert ids == ["d", "b", "a", "c"]


def test_new_tracks_append_and_removed_tracks_drop(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        station = _seed_ordered(s)
        s.merge(Setting(key=f"station_order:{station.id}", value='["d", "zz", "a"]'))
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_station(s, station.id)]
        assert ids == ["d", "a", "b", "c"]


def test_corrupt_order_falls_back_to_default(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        station = _seed_ordered(s)
        s.merge(Setting(key=f"station_order:{station.id}", value="{not json"))
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_station(s, station.id)]
        assert ids == ["a", "b", "c", "d"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stations.py -v` (from `backend/`)
Expected: FAIL — `ImportError: cannot import name 'ordered_tracks_for_station'`.

- [ ] **Step 3: Implement the helpers**

In `backend/app/routers/stations.py`, update the imports and add the helpers:

```python
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import Playlist, Setting, Station, TrackCache
from app.queue import encode_cursor
from app.schemas import StationDetail, StationOut, TrackOut

router = APIRouter(prefix="/api/stations", tags=["stations"])

ORDER_KEY_PREFIX = "station_order:"


def load_order(session: Session, station_id: int) -> list[str]:
    row = session.get(Setting, f"{ORDER_KEY_PREFIX}{station_id}")
    if row is None or not row.value:
        return []
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(v) for v in data]


def save_order(session: Session, station_id: int, video_ids: list[str]) -> None:
    payload = json.dumps([str(v) for v in video_ids])
    session.merge(Setting(key=f"{ORDER_KEY_PREFIX}{station_id}", value=payload))
    session.commit()
```

Then add before `first_track_response`:

```python
def ordered_tracks_for_station(session: Session, station_id: int) -> list[TrackCache]:
    tracks = tracks_for_station(session, station_id)
    order = load_order(session, station_id)
    if not order:
        return tracks
    by_video: dict[str, list[TrackCache]] = {}
    for t in tracks:
        by_video.setdefault(t.youtube_video_id, []).append(t)
    result: list[TrackCache] = []
    used: set[int] = set()
    for vid in order:
        chosen = next(
            (t for t in by_video.get(vid, []) if t.id not in used),
            None,
        )
        if chosen is not None:
            result.append(chosen)
            used.add(chosen.id)
    for t in tracks:
        if t.id not in used:
            result.append(t)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stations.py -v` (from `backend/`)
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/stations.py backend/tests/test_stations.py
git commit -m "feat: per-station play order storage"
```

---

## Task 2: Manual mode in the broadcast engine

**Files:**
- Modify: `backend/app/broadcast.py`
- Test: `backend/tests/test_broadcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_broadcast.py`:

```python
def test_manual_advance_ignores_schedule_and_wraps():
    state = BroadcastState(
        station_id=1,
        track_ids=[10, 11],
        durations=[100, 100],
        index=0,
        started_at=START,
        manual=True,
    )
    desired = _desired_at([(START, 2)])
    result = advance(
        state,
        START + timedelta(seconds=150),
        desired,
        lambda sid: ([99], [100]),
    )
    assert result.station_id == 1
    assert result.track_ids == [10, 11]
    assert result.index == 1
    assert result.started_at == START + timedelta(seconds=100)


def test_manual_advance_wraps_to_first_track():
    state = BroadcastState(
        station_id=1,
        track_ids=[10, 11],
        durations=[100, 100],
        index=1,
        started_at=START,
        manual=True,
    )
    result = advance(
        state,
        START + timedelta(seconds=100),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
    )
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=100)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_broadcast.py -v` (from `backend/`)
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'manual'`.

- [ ] **Step 3: Add the `manual` field and manual advance**

In `backend/app/broadcast.py`, update the dataclass:

```python
@dataclass
class BroadcastState:
    station_id: int | None
    track_ids: list[int]
    durations: list[int]
    index: int
    started_at: datetime
    manual: bool = False
```

At the end of the `advance` normalization block, before the main `for _ in range(10000):` loop, add:

```python
    if state.manual:
        return _advance_manual(state, now)
```

Add this function directly after `advance`:

```python
def _advance_manual(state: BroadcastState, now: datetime) -> BroadcastState:
    for _ in range(10000):
        if not state.track_ids:
            return state
        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration)
        if now < end:
            return state
        state.index += 1
        state.started_at = end
        if state.index >= len(state.track_ids):
            state.index = 0
    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_broadcast.py -v` (from `backend/`)
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_broadcast.py
git commit -m "feat: manual mode in broadcast advance"
```

---

## Task 3: Control functions + order-aware snapshot + `source: manual`

**Files:**
- Modify: `backend/app/broadcast.py`
- Test: `backend/tests/test_live_control.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_live_control.py`:

```python
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.broadcast import get_current, play_now, set_auto, set_order, skip
from app.models import Playlist, Station, TrackCache


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session, slug, vids, *, default=False):
    st = Station(name=slug.title(), slug=slug, is_default=default)
    session.add(st)
    session.commit()
    session.refresh(st)
    pl = Playlist(station_id=st.id, youtube_playlist_id=f"PL-{slug}")
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


NOW = datetime(2026, 1, 1, 0, 0, 0)


def test_play_now_switches_to_manual(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "b", now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.source == "manual"
        assert now_state.track.youtube_video_id == "b"
        assert now_state.offset_seconds == 0


def test_play_now_unknown_track_raises(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a"])
        try:
            play_now(s, st.id, "nope", now=NOW)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_skip_next_and_prev_move_within_station(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "a", now=NOW)
        skip(s, st.id, "next", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "b"
        skip(s, st.id, "prev", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "a"
        skip(s, st.id, "prev", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "c"


def test_skip_switches_to_requested_station(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        one = _seed(s, "one", ["a"])
        two = _seed(s, "two", ["x", "y"], default=True)
        set_auto(s, now=NOW)
        skip(s, two.id, "next", now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.station.id == two.id
        assert now_state.track.youtube_video_id == "x"


def test_set_auto_returns_to_schedule(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b"], default=True)
        play_now(s, st.id, "b", now=NOW)
        assert get_current(s, NOW).source == "manual"
        set_auto(s, now=NOW)
        assert get_current(s, NOW).source == "default"
        assert get_current(s, NOW).track.youtube_video_id == "a"


def test_set_order_preserves_current_track(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "b", now=NOW)
        set_order(s, st.id, ["c", "b", "a"], now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.track.youtube_video_id == "b"
        assert now_state.offset_seconds == 0


def test_order_applies_to_next_skip(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        set_order(s, st.id, ["c", "b", "a"], now=NOW)
        play_now(s, st.id, "c", now=NOW)
        skip(s, st.id, "next", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_live_control.py -v` (from `backend/`)
Expected: FAIL — `ImportError: cannot import name 'play_now'`.

- [ ] **Step 3: Implement the engine changes**

In `backend/app/broadcast.py`, update the stations import:

```python
from app.routers.stations import (
    ordered_tracks_for_station,
    save_order,
    tracks_for_station,
)
```

Change `_snapshot` to use the ordered list:

```python
def _snapshot(session: Session, station_id: int) -> tuple[list[int], list[int]]:
    tracks = ordered_tracks_for_station(session, station_id)
    return [int(t.id) for t in tracks], [t.duration_seconds or 1 for t in tracks]
```

In `_load`, parse the new field and pass it through:

```python
        index = int(data["index"])
        started_at = datetime.fromisoformat(data["started_at_utc"])
        manual = bool(data.get("manual", False))
```

and in the returned `BroadcastState`:

```python
    return BroadcastState(
        station_id=station_id,
        track_ids=track_ids,
        durations=durations,
        index=index,
        started_at=started_at,
        manual=manual,
    )
```

In `_save`, add the field to the payload:

```python
            "index": state.index,
            "started_at_utc": state.started_at.isoformat(),
            "manual": state.manual,
```

Add a source helper after `_snapshot`:

```python
def _source(session: Session, state: BroadcastState, now: datetime) -> str:
    if state.manual:
        return "manual"
    resolved_id, matched = _resolve(session, now)
    return "schedule" if (matched and resolved_id == state.station_id) else "default"
```

In `get_current`, replace the recovered-branch source computation and the final return. The recovered block becomes:

```python
        if track is None or station is None:
            if state.manual and state.station_id is not None:
                ids, durations = _snapshot(session, state.station_id)
                state = BroadcastState(
                    state.station_id, ids, durations, 0, now, True
                )
            else:
                state = _init(session, now)
            _save(session, state)
            if state.station_id is None or not state.track_ids:
                return NowState(None, None, 0, "none")
            track = session.get(TrackCache, state.track_ids[state.index])
            station = session.get(Station, state.station_id)
            if track is None or station is None:
                return NowState(None, None, 0, "none")
            return NowState(station, track, 0, _source(session, state, now))
        duration = state.durations[state.index] or 1
        offset = int((now - state.started_at).total_seconds())
        offset = max(0, min(offset, duration - 1))
        return NowState(station, track, offset, _source(session, state, now))
```

Add the control functions at the end of the file:

```python
def _load_and_advance(session: Session, now: datetime) -> BroadcastState:
    state = _load(session)
    if state is None:
        state = _init(session, now)
    return advance(
        state,
        now,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
    )


def _build_manual(
    session: Session, station_id: int, index: int, now: datetime
) -> BroadcastState:
    ids, durations = _snapshot(session, station_id)
    return BroadcastState(station_id, ids, durations, index, now, True)


def play_now(
    session: Session, station_id: int, video_id: str, now: datetime | None = None
) -> None:
    now = now or utcnow()
    with _lock:
        tracks = ordered_tracks_for_station(session, station_id)
        index = next(
            (i for i, t in enumerate(tracks) if t.youtube_video_id == video_id),
            None,
        )
        if index is None:
            raise ValueError("track not found")
        _save(session, _build_manual(session, station_id, index, now))


def skip(
    session: Session, station_id: int, direction: str, now: datetime | None = None
) -> None:
    now = now or utcnow()
    with _lock:
        state = _load_and_advance(session, now)
        if not state.manual or state.station_id != station_id or not state.track_ids:
            tracks = ordered_tracks_for_station(session, station_id)
            if not tracks:
                raise ValueError("station has no tracks")
            index = 0 if direction == "next" else len(tracks) - 1
            _save(session, _build_manual(session, station_id, index, now))
            return
        total = len(state.track_ids)
        delta = 1 if direction == "next" else -1
        state.index = (state.index + delta) % total
        state.started_at = now
        _save(session, state)


def set_auto(session: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    with _lock:
        state = _init(session, now)
        _save(session, state)


def set_order(
    session: Session,
    station_id: int,
    video_ids: list[str],
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    with _lock:
        save_order(session, station_id, video_ids)
        state = _load(session)
        if state is None or not state.manual or state.station_id != station_id:
            return
        current_id = state.track_ids[state.index] if state.track_ids else None
        ids, durations = _snapshot(session, station_id)
        if not ids:
            return
        try:
            new_index = ids.index(current_id) if current_id is not None else 0
        except ValueError:
            new_index = 0
        _save(
            session,
            BroadcastState(
                station_id, ids, durations, new_index, state.started_at, True
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_live_control.py tests/test_broadcast.py tests/test_now.py -v` (from `backend/`)
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_live_control.py
git commit -m "feat: live-control engine functions"
```

---

## Task 4: Admin endpoints

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin.py` (it already defines `_client` and imports `Session, SQLModel, create_engine, select`):

```python
def _seed_station_with_tracks(engine, slug="chill", vids=("a", "b", "c")):
    from app.models import Playlist, Station, TrackCache

    with Session(engine) as s:
        st = Station(name=slug.title(), slug=slug, is_default=True)
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(station_id=st.id, youtube_playlist_id=f"PL-{slug}")
        s.add(pl)
        s.commit()
        s.refresh(pl)
        for pos, vid in enumerate(vids):
            s.add(
                TrackCache(
                    playlist_id=pl.id,
                    youtube_video_id=vid,
                    title=vid.upper(),
                    artist="A",
                    position=pos,
                    duration_seconds=100,
                )
            )
        s.commit()
        return st.id


def test_station_tracks_requires_auth(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_station_with_tracks(engine)
    assert client.get(f"/api/admin/stations/{sid}/tracks").status_code == 401


def test_station_tracks_returns_ordered_list(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_station_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.put(f"/api/admin/stations/{sid}/order", json={"video_ids": ["c", "a"]})
    body = client.get(f"/api/admin/stations/{sid}/tracks").json()
    assert [t["youtube_video_id"] for t in body] == ["c", "a", "b"]


def test_play_and_auto_endpoints(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_station_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/playback/play",
        json={"station_id": sid, "youtube_video_id": "b"},
    )
    assert resp.status_code == 200
    assert client.get("/api/now").json()["source"] == "manual"
    assert client.get("/api/now").json()["track"]["youtube_video_id"] == "b"
    assert client.post("/api/admin/playback/auto").status_code == 200
    assert client.get("/api/now").json()["source"] == "default"


def test_next_prev_endpoints(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_station_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post(
        "/api/admin/playback/play",
        json={"station_id": sid, "youtube_video_id": "a"},
    )
    client.post("/api/admin/playback/next", json={"station_id": sid})
    assert client.get("/api/now").json()["track"]["youtube_video_id"] == "b"
    client.post("/api/admin/playback/prev", json={"station_id": sid})
    assert client.get("/api/now").json()["track"]["youtube_video_id"] == "a"


def test_play_unknown_track_returns_404(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_station_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/playback/play",
        json={"station_id": sid, "youtube_video_id": "nope"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin.py -v` (from `backend/`)
Expected: FAIL — new tests get 404 (routes missing).

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas.py`:

```python
class PlayIn(BaseModel):
    station_id: int
    youtube_video_id: str


class StationRefIn(BaseModel):
    station_id: int


class OrderIn(BaseModel):
    video_ids: list[str]
```

- [ ] **Step 4: Add the endpoints**

In `backend/app/routers/admin.py`, update imports. Add to the `app.broadcast` import:

```python
from app.broadcast import play_now, set_auto, set_order, skip
```

Add `from app.routers.stations import ordered_tracks_for_station` after the `app.models` import. Extend the `app.schemas` import with `OrderIn, PlayIn, StationRefIn, TrackOut` (keep existing names).

Add these endpoints at the end of the file:

```python
@router.get(
    "/stations/{station_id}/tracks",
    response_model=list[TrackOut],
    dependencies=[Depends(require_admin)],
)
def station_tracks(
    station_id: int, session: Session = Depends(get_session)
) -> list[TrackOut]:
    if session.get(Station, station_id) is None:
        raise HTTPException(status_code=404, detail="station not found")
    return [
        TrackOut.model_validate(t)
        for t in ordered_tracks_for_station(session, station_id)
    ]


@router.post("/playback/play", dependencies=[Depends(require_admin)])
def playback_play(body: PlayIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Station, body.station_id) is None:
        raise HTTPException(status_code=404, detail="station not found")
    try:
        play_now(session, body.station_id, body.youtube_video_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/playback/next", dependencies=[Depends(require_admin)])
def playback_next(body: StationRefIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Station, body.station_id) is None:
        raise HTTPException(status_code=404, detail="station not found")
    try:
        skip(session, body.station_id, "next")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/playback/prev", dependencies=[Depends(require_admin)])
def playback_prev(body: StationRefIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Station, body.station_id) is None:
        raise HTTPException(status_code=404, detail="station not found")
    try:
        skip(session, body.station_id, "prev")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/playback/auto", dependencies=[Depends(require_admin)])
def playback_auto(session: Session = Depends(get_session)) -> dict:
    set_auto(session)
    return {"status": "ok"}


@router.put("/stations/{station_id}/order", dependencies=[Depends(require_admin)])
def set_station_order(
    station_id: int, body: OrderIn, session: Session = Depends(get_session)
) -> dict:
    if session.get(Station, station_id) is None:
        raise HTTPException(status_code=404, detail="station not found")
    set_order(session, station_id, body.video_ids)
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v` (from `backend/`)
Expected: PASS (all, including existing tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/admin.py backend/tests/test_admin.py
git commit -m "feat: admin live-control endpoints"
```

---

## Task 5: Frontend queue helpers

**Files:**
- Create: `frontend/src/utils/queue.ts`
- Test: `frontend/src/utils/queue.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/queue.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { reorder, shuffle } from "./queue";

describe("reorder", () => {
  it("moves an item forward", () => {
    expect(reorder(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
  });

  it("moves an item backward", () => {
    expect(reorder(["a", "b", "c", "d"], 3, 1)).toEqual(["a", "d", "b", "c"]);
  });

  it("clamps the destination and ignores bad sources", () => {
    expect(reorder(["a", "b"], 0, 99)).toEqual(["b", "a"]);
    expect(reorder(["a", "b"], 5, 0)).toEqual(["a", "b"]);
  });
});

describe("shuffle", () => {
  it("permutes deterministically with a fixed random source", () => {
    expect(shuffle(["a", "b", "c"], () => 0)).toEqual(["b", "c", "a"]);
  });

  it("keeps every element", () => {
    const out = shuffle([1, 2, 3, 4, 5]);
    expect(out.slice().sort()).toEqual([1, 2, 3, 4, 5]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/utils/queue.test.ts` (from `frontend/`)
Expected: FAIL — cannot resolve `./queue`.

- [ ] **Step 3: Implement the helpers**

Create `frontend/src/utils/queue.ts`:

```ts
export function reorder<T>(list: T[], from: number, to: number): T[] {
  const next = list.slice();
  if (from < 0 || from >= next.length) return next;
  const clampedTo = Math.max(0, Math.min(to, next.length - 1));
  const [item] = next.splice(from, 1);
  next.splice(clampedTo, 0, item);
  return next;
}

export function shuffle<T>(list: T[], rand: () => number = Math.random): T[] {
  const next = list.slice();
  for (let i = next.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [next[i], next[j]] = [next[j], next[i]];
  }
  return next;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/utils/queue.test.ts` (from `frontend/`)
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/queue.ts frontend/src/utils/queue.test.ts
git commit -m "feat: queue reorder and shuffle helpers"
```

---

## Task 6: Frontend API client methods

**Files:**
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write the failing test**

Append inside the `describe("api client", ...)` block in `frontend/src/api/client.test.ts`:

```ts
  it("PUTs a station order", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    await api.setStationOrder(3, ["a", "b"]);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/admin/stations/3/order");
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(JSON.stringify({ video_ids: ["a", "b"] }));
  });

  it("POSTs a play-now request", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    await api.play(3, "vid");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/admin/playback/play");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(
      JSON.stringify({ station_id: 3, youtube_video_id: "vid" }),
    );
  });

  it("POSTs next and prev", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );
    await api.playbackNext(3);
    await api.playbackPrev(3);
    expect(spy.mock.calls[0][0]).toBe("/api/admin/playback/next");
    expect(spy.mock.calls[1][0]).toBe("/api/admin/playback/prev");
  });

  it("GETs a station's ordered tracks", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    await api.stationTracks(3);
    expect(spy.mock.calls[0][0]).toBe("/api/admin/stations/3/tracks");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/api/client.test.ts` (from `frontend/`)
Expected: FAIL — `api.setStationOrder is not a function`.

- [ ] **Step 3: Implement the methods**

In `frontend/src/api/client.ts`, add to the `api` object (after `session`):

```ts
  stationTracks: (stationId: number) =>
    request<Track[]>(`/admin/stations/${stationId}/tracks`),
  play: (stationId: number, youtubeVideoId: string) =>
    request<{ status: string }>("/admin/playback/play", {
      method: "POST",
      body: JSON.stringify({
        station_id: stationId,
        youtube_video_id: youtubeVideoId,
      }),
    }),
  playbackNext: (stationId: number) =>
    request<{ status: string }>("/admin/playback/next", {
      method: "POST",
      body: JSON.stringify({ station_id: stationId }),
    }),
  playbackPrev: (stationId: number) =>
    request<{ status: string }>("/admin/playback/prev", {
      method: "POST",
      body: JSON.stringify({ station_id: stationId }),
    }),
  playbackAuto: () =>
    request<{ status: string }>("/admin/playback/auto", { method: "POST" }),
  setStationOrder: (stationId: number, videoIds: string[]) =>
    request<{ status: string }>(`/admin/stations/${stationId}/order`, {
      method: "PUT",
      body: JSON.stringify({ video_ids: videoIds }),
    }),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/api/client.test.ts` (from `frontend/`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat: admin live-control API client methods"
```

---

## Task 7: Now Playing panel rewrite

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`
- Rewrite: `frontend/src/components/admin/NowPlayingPanel.tsx`
- Rewrite: `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`

- [ ] **Step 1: Pass stations into the panel**

In `frontend/src/pages/AdminPage.tsx`, change the Now Playing panel usage:

```tsx
        {tab === "now" && (
          <NowPlayingPanel
            stations={stations}
            onNotice={onNotice}
            onError={onError}
          />
        )}
```

- [ ] **Step 2: Rewrite the panel test**

Replace `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` with:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { Station, Track } from "../../types";
import { NowPlayingPanel } from "./NowPlayingPanel";

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return {
    ...actual,
    api: {
      now: vi.fn(),
      syncAll: vi.fn(),
      stationTracks: vi.fn(),
      play: vi.fn(),
      playbackNext: vi.fn(),
      playbackPrev: vi.fn(),
      playbackAuto: vi.fn(),
      setStationOrder: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const STATION: Station = {
  id: 1,
  name: "Chill",
  slug: "chill",
  is_default: true,
  track_count: 2,
};

const track = (id: string, title: string, position: number): Track => ({
  youtube_video_id: id,
  title,
  artist: "Artist",
  thumbnail_url: "",
  duration_seconds: 200,
  position,
});

const TRACK_A = track("a", "Alpha", 0);
const TRACK_B = track("b", "Beta", 1);

beforeEach(() => {
  mocked.stationTracks.mockResolvedValue([TRACK_A, TRACK_B]);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function renderPanel(stations: Station[] = [STATION]) {
  return render(
    <NowPlayingPanel
      stations={stations}
      onNotice={vi.fn()}
      onError={vi.fn()}
    />,
  );
}

describe("NowPlayingPanel", () => {
  it("shows the on-air track, up next, and the queue", async () => {
    mocked.now.mockResolvedValue({
      station: STATION,
      track: TRACK_A,
      offset_seconds: 5,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    renderPanel();
    expect((await screen.findAllByText("Alpha")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Beta")).length).toBeGreaterThan(0);
    expect(screen.getByText("Up next")).toBeInTheDocument();
    expect(screen.getByText("On air")).toBeInTheDocument();
  });

  it("shows an empty state when nothing is scheduled", async () => {
    mocked.now.mockResolvedValue({
      station: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
    });
    renderPanel([]);
    expect(await screen.findByText("Nothing scheduled.")).toBeInTheDocument();
  });

  it("shows an error state when playback status cannot be loaded", async () => {
    mocked.now.mockRejectedValue(new Error("boom"));
    renderPanel([]);
    expect(
      await screen.findByText("Could not load playback status."),
    ).toBeInTheDocument();
  });

  it("asks for confirmation before cutting over, then plays", async () => {
    mocked.now.mockResolvedValue({
      station: STATION,
      track: TRACK_A,
      offset_seconds: 5,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    mocked.play.mockResolvedValue({ status: "ok" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPanel();
    const playButtons = await screen.findAllByText("Play");
    fireEvent.click(playButtons[1]);
    await waitFor(() => expect(confirm).toHaveBeenCalled());
    await waitFor(() => expect(mocked.play).toHaveBeenCalledWith(1, "b"));
  });

  it("calls next and prev for the selected station", async () => {
    mocked.now.mockResolvedValue({
      station: STATION,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.playbackNext.mockResolvedValue({ status: "ok" });
    mocked.playbackPrev.mockResolvedValue({ status: "ok" });
    renderPanel();
    fireEvent.click(await screen.findByText("Next"));
    await waitFor(() => expect(mocked.playbackNext).toHaveBeenCalledWith(1));
    fireEvent.click(screen.getByText("Prev"));
    await waitFor(() => expect(mocked.playbackPrev).toHaveBeenCalledWith(1));
  });

  it("enables Auto only in manual mode and returns to schedule", async () => {
    mocked.now.mockResolvedValue({
      station: STATION,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "manual",
    });
    mocked.playbackAuto.mockResolvedValue({ status: "ok" });
    renderPanel();
    const auto = await screen.findByText("Auto");
    expect(auto).not.toBeDisabled();
    fireEvent.click(auto);
    await waitFor(() => expect(mocked.playbackAuto).toHaveBeenCalled());
  });

  it("disables Auto in automatic mode", async () => {
    mocked.now.mockResolvedValue({
      station: STATION,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    renderPanel();
    expect(await screen.findByText("Auto")).toBeDisabled();
  });

  it("shuffles and saves the new order", async () => {
    mocked.now.mockResolvedValue({
      station: STATION,
      track: TRACK_A,
      offset_seconds: 0,
      server_time: "x",
      source: "schedule",
    });
    mocked.setStationOrder.mockResolvedValue({ status: "ok" });
    vi.spyOn(Math, "random").mockReturnValue(0);
    renderPanel();
    fireEvent.click(await screen.findByText("Shuffle"));
    await waitFor(() =>
      expect(mocked.setStationOrder).toHaveBeenCalledWith(1, ["b", "a"]),
    );
  });

  it("syncs all playlists and reports the summary", async () => {
    mocked.now.mockResolvedValue({
      station: null,
      track: null,
      offset_seconds: 0,
      server_time: "x",
      source: "none",
    });
    mocked.syncAll.mockResolvedValue({
      results: [
        { id: 1, synced: 2, error: null },
        { id: 2, synced: 0, error: "nope" },
      ],
    });
    const onNotice = vi.fn();
    render(
      <NowPlayingPanel
        stations={[]}
        onNotice={onNotice}
        onError={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByText("Sync all playlists"));
    await waitFor(() =>
      expect(onNotice).toHaveBeenCalledWith(
        "Synced 1 of 2 playlist(s); 1 failed.",
      ),
    );
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npx vitest run src/components/admin/NowPlayingPanel.dom.test.tsx` (from `frontend/`)
Expected: FAIL — `stations` prop not accepted / missing controls.

- [ ] **Step 4: Rewrite the panel**

Replace `frontend/src/components/admin/NowPlayingPanel.tsx` with:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { useBroadcast } from "../../hooks/useBroadcast";
import { messageFor } from "../../utils/errors";
import { reorder, shuffle } from "../../utils/queue";
import type { Station, Track } from "../../types";

interface Props {
  stations: Station[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

const UP_NEXT_COUNT = 5;

export function NowPlayingPanel({ stations, onNotice, onError }: Props) {
  const { state, failed, refresh } = useBroadcast();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const liveStation = state?.station ?? null;
  const knownLiveId =
    liveStation && stations.some((s) => s.id === liveStation.id)
      ? liveStation.id
      : null;

  useEffect(() => {
    if (selectedId !== null) return;
    const initial = knownLiveId ?? stations[0]?.id ?? null;
    if (initial !== null) setSelectedId(initial);
  }, [selectedId, knownLiveId, stations]);

  useEffect(() => {
    if (selectedId === null) {
      setTracks([]);
      return;
    }
    let active = true;
    setLoading(true);
    api
      .stationTracks(selectedId)
      .then((rows) => {
        if (active) setTracks(rows);
      })
      .catch((err) => {
        if (active) onErrorRef.current(messageFor(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  const currentVideoId =
    state?.station?.id === selectedId
      ? (state?.track?.youtube_video_id ?? null)
      : null;
  const currentIndex = currentVideoId
    ? tracks.findIndex((t) => t.youtube_video_id === currentVideoId)
    : -1;

  const upNext = useMemo(() => {
    if (currentIndex < 0 || tracks.length < 2) return [];
    const count = Math.min(UP_NEXT_COUNT, tracks.length - 1);
    return Array.from(
      { length: count },
      (_, k) => tracks[(currentIndex + 1 + k) % tracks.length],
    );
  }, [tracks, currentIndex]);

  const syncAll = async () => {
    try {
      const result = await api.syncAll();
      const failedSync = result.results.filter((r) => r.error).length;
      onNotice(
        failedSync === 0
          ? `Synced ${result.results.length} playlist(s).`
          : `Synced ${result.results.length - failedSync} of ${result.results.length} playlist(s); ${failedSync} failed.`,
      );
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const saveOrder = async (next: Track[]) => {
    if (selectedId === null) return;
    setTracks(next);
    try {
      await api.setStationOrder(
        selectedId,
        next.map((t) => t.youtube_video_id),
      );
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const playTrack = async (track: Track) => {
    if (selectedId === null) return;
    if (state?.track) {
      const ok = window.confirm(
        `A song is playing — play "${track.title}" now?`,
      );
      if (!ok) return;
    }
    try {
      await api.play(selectedId, track.youtube_video_id);
      onNotice(`Now playing "${track.title}".`);
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const transport = async (direction: "next" | "prev") => {
    if (selectedId === null) return;
    try {
      await (direction === "next"
        ? api.playbackNext(selectedId)
        : api.playbackPrev(selectedId));
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const goAuto = async () => {
    try {
      await api.playbackAuto();
      onNotice("Returned to the schedule.");
      refresh();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const syncButton = (
    <button type="button" className="btn btn-secondary" onClick={syncAll}>
      Sync all playlists
    </button>
  );

  return (
    <section className="admin-panel" aria-label="Now playing">
      <div className="panel-head">
        <h2>Now playing</h2>
        {syncButton}
      </div>

      {stations.length > 0 && (
        <label className="field">
          Station
          <select
            aria-label="Station to control"
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(Number(e.target.value))}
          >
            {stations.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {state?.station && state.track ? (
        <div className="now-playing">
          {state.track.thumbnail_url && (
            <img className="art" src={state.track.thumbnail_url} alt="" />
          )}
          <div className="meta">
            <div className="title">{state.track.title}</div>
            <div className="artist">{state.track.artist}</div>
            <div className="source">
              Station: {state.station.name} · Source: {state.source}
            </div>
          </div>
        </div>
      ) : (
        <p>
          {failed ? "Could not load playback status." : "Nothing scheduled."}
        </p>
      )}

      <div className="transport">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => transport("prev")}
          disabled={tracks.length === 0}
        >
          Prev
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => transport("next")}
          disabled={tracks.length === 0}
        >
          Next
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={goAuto}
          disabled={state?.source !== "manual"}
        >
          Auto
        </button>
      </div>

      {upNext.length > 0 && (
        <div className="up-next">
          <h3>Up next</h3>
          <ul>
            {upNext.map((t) => (
              <li key={t.youtube_video_id}>
                {t.title} — {t.artist}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="queue-head">
        <h3>Queue</h3>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => saveOrder(shuffle(tracks))}
          disabled={tracks.length < 2}
        >
          Shuffle
        </button>
      </div>

      {loading ? (
        <p>Loading…</p>
      ) : (
        <ol className="queue-list">
          {tracks.map((t, i) => {
            const isCurrent = i === currentIndex;
            return (
              <li
                key={`${t.youtube_video_id}-${i}`}
                className={isCurrent ? "queue-row current" : "queue-row"}
                draggable
                onDragStart={() => setDragIndex(i)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (dragIndex !== null && dragIndex !== i) {
                    saveOrder(reorder(tracks, dragIndex, i));
                  }
                  setDragIndex(null);
                }}
              >
                <span className="drag-handle" aria-hidden="true">
                  ⋮⋮
                </span>
                {t.thumbnail_url && (
                  <img className="art small" src={t.thumbnail_url} alt="" />
                )}
                <span className="queue-title">{t.title}</span>
                <span className="queue-artist">{t.artist}</span>
                {isCurrent && <span className="badge">On air</span>}
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => playTrack(t)}
                >
                  Play
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run src/components/admin/NowPlayingPanel.dom.test.tsx src/pages/AdminPage.dom.test.tsx` (from `frontend/`)
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx frontend/src/components/admin/NowPlayingPanel.tsx frontend/src/components/admin/NowPlayingPanel.dom.test.tsx
git commit -m "feat: admin now-playing live controls"
```

---

## Task 8: Styles

**Files:**
- Modify: `frontend/src/styles/vintage.css`

- [ ] **Step 1: Add the styles**

Append to `frontend/src/styles/vintage.css`:

```css
.transport {
  display: flex;
  gap: 8px;
  margin: 12px 0;
}

.up-next {
  margin: 8px 0 16px;
}

.up-next h3,
.queue-head h3 {
  font-size: 1rem;
  margin-bottom: 6px;
}

.up-next ul {
  list-style: none;
  padding: 0;
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
}

.queue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.queue-list {
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
  max-height: 420px;
  overflow-y: auto;
}

.queue-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  cursor: grab;
}

.queue-row.current {
  background: rgba(59, 36, 23, 0.06);
  border-radius: var(--radius-sm);
}

.drag-handle {
  color: var(--muted);
  letter-spacing: -2px;
}

.queue-title {
  font-weight: 600;
}

.queue-artist {
  color: var(--muted);
  flex: 1;
}

.badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--ink);
  color: var(--cream);
}

.art.small {
  width: 36px;
  height: 36px;
}
```

- [ ] **Step 2: Typecheck and run the full frontend suite**

Run: `npm run typecheck` then `npm test` (from `frontend/`)
Expected: typecheck clean; all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/vintage.css
git commit -m "style: admin queue rows and transport controls"
```

---

## Task 9: Run full backend tests, rebuild containers, verify

**Files:** none (verification)

- [ ] **Step 1: Run the full backend suite**

Run: `python -m pytest -q` (from `backend/`)
Expected: PASS (all tests, no failures).

- [ ] **Step 2: Rebuild and redeploy the changed services**

Run: `docker compose up -d --build backend frontend` (from repo root)
Expected: images build; `backend` and `frontend` containers recreated.

- [ ] **Step 3: Verify the new endpoint exists and auth is enforced**

Run:
```
curl.exe -s -o NUL -w "tracks(no auth): %{http_code}`n" http://127.0.0.1:8011/api/admin/stations/1/tracks
curl.exe -s -o NUL -w "health: %{http_code}`n" http://127.0.0.1:8011/api/health
```
Expected: `tracks(no auth): 401`, `health: 200`.

- [ ] **Step 4: Confirm containers are healthy**

Run: `docker compose ps`
Expected: `backend` and `frontend` show `(healthy)`.

- [ ] **Step 5: Commit** — none (verification only).

---

## Self-Review Notes

- **Spec coverage:** order storage (Task 1), manual engine (Tasks 2–3), play/next/prev/auto (Tasks 3–4), reorder + shuffle (Tasks 3, 5, 7), station picker (Task 7), confirmation prompt (Task 7), up-next + full list (Task 7), testing (Tasks 1–7), no migration/deps (all tasks), listener UI unchanged (no task touches `RadioPage`).
- **Intentional deviation:** `GET /api/admin/playback` is dropped as redundant with `/api/now` (documented in the header).
- **Type consistency:** control functions use `play_now` / `skip(session, station_id, direction)` / `set_auto` / `set_order(session, station_id, video_ids)`; admin endpoints and tests use the same names. Frontend methods `stationTracks` / `play` / `playbackNext` / `playbackPrev` / `playbackAuto` / `setStationOrder` are used identically in the panel and its tests.
