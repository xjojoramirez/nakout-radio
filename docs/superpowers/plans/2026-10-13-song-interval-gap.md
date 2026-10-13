# Song Interval Gap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert a server-authoritative 2-second silence gap (configurable via `TRACK_GAP_SECONDS`) between automatically-advanced songs so every listener can preload the next video and start it together.

**Architecture:** The gap is folded into the broadcast boundary math: a track's end becomes `started_at + duration + gap`. `get_current` reports a new `"gap"` phase (previous track + upcoming track + countdown) during the silent window. The listener client preloads the upcoming video, muted and paused, and starts it with a local timer at the boundary.

**Tech Stack:** FastAPI + SQLModel + pytest (backend), React 18 + TypeScript + Vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-10-13-song-interval-gap-design.md`

**Branch:** `feat/song-interval-gap` (already checked out; main is protected).

---

### Task 1: Backend — `TRACK_GAP_SECONDS` setting

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_config.py`:

```python
def test_track_gap_default(monkeypatch):
    monkeypatch.delenv("TRACK_GAP_SECONDS", raising=False)
    assert Settings(_env_file=None).track_gap_seconds == 2.0


def test_track_gap_rejects_out_of_range():
    import pytest

    with pytest.raises(Exception):
        Settings(_env_file=None, track_gap_seconds=-1)
    with pytest.raises(Exception):
        Settings(_env_file=None, track_gap_seconds=31)


def test_track_gap_accepts_zero_and_fraction():
    assert Settings(_env_file=None, track_gap_seconds=0).track_gap_seconds == 0
    assert Settings(_env_file=None, track_gap_seconds=1.5).track_gap_seconds == 1.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL — `track_gap_seconds` missing / validation absent.

- [ ] **Step 3: Implement the setting**

In `backend/app/config.py`, add the field after `cache_ttl_minutes`:

```python
    track_gap_seconds: float = 2.0
```

Add the validator next to `_valid_tz`:

```python
    @field_validator("track_gap_seconds")
    @classmethod
    def _valid_gap(cls, v: float) -> float:
        if not 0 <= v <= 30:
            raise ValueError("track_gap_seconds must be between 0 and 30")
        return v
```

In `backend/.env.example`, after `CACHE_TTL_MINUTES=60`:

```
TRACK_GAP_SECONDS=2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py backend/.env.example
git commit -m "feat: TRACK_GAP_SECONDS setting for the between-song gap"
```

---

### Task 2: Backend — gap in the boundary math

**Files:**
- Modify: `backend/app/broadcast.py` (`advance`, `_advance_manual`)
- Modify: `backend/tests/test_broadcast.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_broadcast.py`:

```python
def test_gap_holds_previous_track_after_boundary():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state,
        START + timedelta(seconds=101),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        gap_seconds=2.0,
    )
    assert result.index == 0
    assert result.started_at == START


def test_gap_shifts_next_track_start():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state,
        START + timedelta(seconds=102),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        gap_seconds=2.0,
    )
    assert result.index == 1
    assert result.started_at == START + timedelta(seconds=102)


def test_gaps_accumulate_across_catch_up():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state,
        START + timedelta(seconds=204),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        gap_seconds=2.0,
    )
    # 100s song + 2s gap + 100s song + 2s gap = 204s
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=204)


def test_zero_gap_matches_previous_behavior():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state,
        START + timedelta(seconds=100),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        gap_seconds=0.0,
    )
    assert result.index == 1
    assert result.started_at == START + timedelta(seconds=100)


def test_genre_switch_lands_after_the_gap():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=101), 2)])
    table = {1: ([10], [100]), 2: ([20, 21], [100, 100])}
    result = advance(
        state,
        START + timedelta(seconds=150),
        desired,
        lambda sid: table[sid],
        gap_seconds=2.0,
    )
    assert result.genre_id == 2
    assert result.index == 0
    # Song ends at 100s, the 2s gap runs to 102s, the new genre starts there.
    assert result.started_at == START + timedelta(seconds=102)


def test_manual_advance_includes_gap():
    state = BroadcastState(
        genre_id=1,
        track_ids=[10, 11],
        durations=[100, 100],
        index=0,
        started_at=START,
        manual=True,
    )
    mid_gap = advance(
        state,
        START + timedelta(seconds=101),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        gap_seconds=2.0,
    )
    assert mid_gap.index == 0
    after = advance(
        state,
        START + timedelta(seconds=102),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        gap_seconds=2.0,
    )
    assert after.index == 1
    assert after.started_at == START + timedelta(seconds=102)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_broadcast.py -v`
Expected: FAIL — `advance() got an unexpected keyword argument 'gap_seconds'`.

- [ ] **Step 3: Implement the gap math**

In `backend/app/broadcast.py`:

`advance` signature and docstring:

```python
def advance(
    state: BroadcastState,
    now: datetime,
    desired: Callable[[datetime], int | None],
    snapshot: Callable[[int], tuple[list[int], list[int]]],
    gap_seconds: float = 0.0,
) -> BroadcastState:
    """Advance ``state`` forward through finished tracks.

    ``desired(at)`` returns the genre that should be live at time ``at``.
    ``snapshot(genre_id)`` returns that genre's ``(track_ids, durations)``.
    Each track occupies ``duration + gap_seconds``: the extra seconds are a
    silent interval after the song, before the next one starts. Boundary times
    are evaluated at the boundary itself so the result is correct even after a
    long gap with no requests. Does not mutate the input.
    """
```

Change the manual delegation inside `advance`:

```python
    if state.manual:
        return _advance_manual(state, now, gap_seconds)
```

Change the scheduled boundary (previously `timedelta(seconds=duration)`):

```python
        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration + gap_seconds)
```

`_advance_manual`:

```python
def _advance_manual(
    state: BroadcastState, now: datetime, gap_seconds: float
) -> BroadcastState:
    for _ in range(10000):
        if not state.track_ids:
            return state
        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration + gap_seconds)
        if now < end:
            return state
        state.index += 1
        state.started_at = end
        if state.index >= len(state.track_ids):
            state.index = 0
    return state
```

Leave `advance`'s remaining lines unchanged; `get_current` will pass the configured gap in Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_broadcast.py -v`
Expected: PASS (old + new tests; old ones call `advance` without `gap_seconds` and get the `0.0` default).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_broadcast.py
git commit -m "feat: gap-aware broadcast boundaries in advance()"
```

---

### Task 3: Backend — gap phase in `get_current` and the API

**Files:**
- Modify: `backend/app/broadcast.py` (`NowState`, `get_current`, `_load_and_advance`)
- Modify: `backend/app/schemas.py` (`NowOut`)
- Modify: `backend/app/routers/now.py` (`build_now`)
- Modify: `backend/tests/test_now.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_now.py`, extend the imports on line 2 with `timezone`:

```python
from datetime import datetime, timedelta, timezone
```

and extend the `app.broadcast` import with `play_now`:

```python
from app.broadcast import _load, get_current, play_now
```

Add these tests:

```python
def test_now_reports_gap_between_songs(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True, duration=200)
    with Session(engine) as s:
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        first = get_current(s, t0)
        assert first.phase == "playing"
        assert first.next_track is None
        assert first.seconds_until_start is None

        during = get_current(s, t0 + timedelta(seconds=201))
        assert during.phase == "gap"
        assert during.track.youtube_video_id == "vid"       # previous track stays
        assert during.next_track.youtube_video_id == "vid"  # single-track genres wrap
        assert 0 < during.seconds_until_start <= 2
        assert during.offset_seconds == 199

        after = get_current(s, t0 + timedelta(seconds=202))
        assert after.phase == "playing"
        assert after.offset_seconds == 0


def test_gap_after_manual_play_but_placement_is_instant(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed_genre(s, "morning", default=True, duration=200)

    with Session(engine) as s:
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        play_now(s, st.id, "vid", now=t0)
        assert get_current(s, t0).phase == "playing"
        assert get_current(s, t0 + timedelta(seconds=199)).phase == "playing"
        assert get_current(s, t0 + timedelta(seconds=200)).phase == "gap"
        started = get_current(s, t0 + timedelta(seconds=202))
        assert started.phase == "playing"
        assert started.offset_seconds == 0


def test_now_endpoint_serves_gap_fields(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed_genre(s, "morning", default=True, duration=200)
        track_id = s.exec(
            select(TrackCache).where(TrackCache.youtube_video_id == "vid")
        ).one().id
        anchor = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=201
        )
        s.merge(
            Setting(
                key="broadcast_state",
                value=json.dumps(
                    {
                        "genre_id": st.id,
                        "track_ids": [track_id],
                        "durations": [200],
                        "index": 0,
                        "started_at_utc": anchor.isoformat(),
                    }
                ),
            )
        )
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["phase"] == "gap"
    assert body["track"]["youtube_video_id"] == "vid"
    assert body["next_track"]["youtube_video_id"] == "vid"
    assert 0 < body["seconds_until_start"] <= 2
```

Also add three assertions to the existing `test_now_returns_track_offset_and_server_time` after the `server_time` check:

```python
    assert body["phase"] == "playing"
    assert body["next_track"] is None
    assert body["seconds_until_start"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_now.py -v`
Expected: FAIL — `NowState` has no `phase`; response lacks the new keys.

- [ ] **Step 3: Implement the backend changes**

`backend/app/schemas.py` — `NowOut`:

```python
class NowOut(BaseModel):
    genre: GenreOut | None
    track: TrackOut | None
    offset_seconds: int
    server_time: str
    source: str
    phase: Literal["playing", "gap"] = "playing"
    next_track: TrackOut | None = None
    seconds_until_start: float | None = None
```

`backend/app/broadcast.py` — `NowState`:

```python
class NowState(NamedTuple):
    genre: Genre | None
    track: TrackCache | None
    offset_seconds: int
    source: str
    phase: str = "playing"
    next_track: TrackCache | None = None
    seconds_until_start: float | None = None
```

`backend/app/broadcast.py` — `_load_and_advance` passes the configured gap:

```python
    return advance(
        state,
        now,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
        get_settings().track_gap_seconds,
    )
```

`backend/app/broadcast.py` — `get_current`: add `gap = get_settings().track_gap_seconds`
right after `now = now or utcnow()`, pass `gap` as the fifth argument of the
first `advance(...)` call, and replace the tail after the `track is None or
genre is None` recovery block with:

```python
        duration = state.durations[state.index] or 1
        offset = int((now - state.started_at).total_seconds())
        offset = max(0, min(offset, duration - 1))
        source = _source(session, state, now)
        if now >= state.started_at + timedelta(seconds=duration):
            end = state.started_at + timedelta(seconds=duration + gap)
            following = advance(
                state,
                end,
                lambda at: _desired(session, at),
                lambda sid: _snapshot(session, sid),
                gap,
            )
            next_track = None
            if following.genre_id is not None and following.track_ids:
                next_track = session.get(
                    TrackCache, following.track_ids[following.index]
                )
            return NowState(
                genre,
                track,
                offset,
                source,
                "gap",
                next_track,
                max(0.0, (end - now).total_seconds()),
            )
        return NowState(genre, track, offset, source)
```

`backend/app/routers/now.py` — `build_now` return:

```python
    return NowOut(
        genre=genre_out,
        track=TrackOut.model_validate(state.track) if state.track else None,
        offset_seconds=state.offset_seconds,
        server_time=ts.replace(tzinfo=timezone.utc).isoformat(),
        source=state.source,
        phase=state.phase,
        next_track=(
            TrackOut.model_validate(state.next_track) if state.next_track else None
        ),
        seconds_until_start=state.seconds_until_start,
    )
```

- [ ] **Step 4: Run the backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (full suite, no regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/app/schemas.py backend/app/routers/now.py backend/tests/test_now.py
git commit -m "feat: expose the between-song gap phase from /api/now"
```

---

### Task 4: Frontend — types and `useBroadcast` carry the gap fields

**Files:**
- Modify: `frontend/src/types.ts` (`BroadcastNow`)
- Modify: `frontend/src/hooks/useBroadcast.ts` (`BroadcastState`, `toState`)
- Modify: `frontend/src/hooks/useBroadcast.dom.test.ts`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/hooks/useBroadcast.dom.test.ts`, extend `nowResponse`'s defaults:

```ts
      source: "none",
      phase: "playing",
      next_track: null,
      seconds_until_start: null,
      ...overrides,
```

Add a poll test inside `describe("useBroadcast", ...)`:

```ts
  it("maps the gap fields from a poll", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        nowResponse({
          source: "default",
          track: {
            youtube_video_id: "a",
            title: "A",
            artist: "",
            thumbnail_url: "",
            duration_seconds: 200,
            position: 0,
          },
          phase: "gap",
          next_track: {
            youtube_video_id: "b",
            title: "B",
            artist: "",
            thumbnail_url: "",
            duration_seconds: 180,
            position: 1,
          },
          seconds_until_start: 1.5,
        }),
      ),
    );
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state?.phase).toBe("gap"));
    expect(result.current.state?.nextTrack?.youtube_video_id).toBe("b");
    expect(result.current.state?.secondsUntilStart).toBe(1.5);
  });
```

Add a push test inside `describe("useBroadcast (radio socket)", ...)`:

```ts
  it("maps the gap fields from a pushed frame", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nowResponse()));
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          genre: null,
          track: {
            youtube_video_id: "a",
            title: "A",
            artist: "",
            thumbnail_url: "",
            duration_seconds: 200,
            position: 0,
          },
          offset_seconds: 199,
          server_time: "2026-01-01T00:00:00+00:00",
          source: "default",
          phase: "gap",
          next_track: {
            youtube_video_id: "b",
            title: "B",
            artist: "",
            thumbnail_url: "",
            duration_seconds: 180,
            position: 1,
          },
          seconds_until_start: 2,
        }),
      });
    });
    await waitFor(() => expect(result.current.state?.phase).toBe("gap"));
    expect(result.current.state?.nextTrack?.youtube_video_id).toBe("b");
    expect(result.current.state?.secondsUntilStart).toBe(2);
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/hooks/useBroadcast.dom.test.ts`
Expected: FAIL — `phase` is undefined / TypeScript errors for the new fields.

- [ ] **Step 3: Implement the mapping**

`frontend/src/types.ts` — `BroadcastNow`:

```ts
export interface BroadcastNow {
  genre: Genre | null;
  track: Track | null;
  offset_seconds: number;
  server_time: string;
  source: string;
  phase: "playing" | "gap";
  next_track: Track | null;
  seconds_until_start: number | null;
}
```

`frontend/src/hooks/useBroadcast.ts` — `BroadcastState`:

```ts
export interface BroadcastState {
  track: Track | null;
  genre: Genre | null;
  source: string;
  /** Seconds into the current track as reported by the server. */
  offset: number;
  /** `Date.now()` when the state was received. */
  fetchedAt: number;
  /** Approximate round-trip time in milliseconds (0 for pushed frames). */
  rttMs: number;
  /** `"gap"` during the silent interval between songs. */
  phase: "playing" | "gap";
  /** The track that starts when the gap ends (null while playing). */
  nextTrack: Track | null;
  /** Seconds until `nextTrack` starts (null while playing). */
  secondsUntilStart: number | null;
}
```

and `toState`:

```ts
function toState(data: BroadcastNow, rttMs: number): BroadcastState {
  return {
    track: data.track,
    genre: data.genre,
    source: data.source,
    offset: data.offset_seconds,
    fetchedAt: Date.now(),
    rttMs,
    phase: data.phase ?? "playing",
    nextTrack: data.next_track ?? null,
    secondsUntilStart: data.seconds_until_start ?? null,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/hooks/useBroadcast.dom.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useBroadcast.ts frontend/src/hooks/useBroadcast.dom.test.ts
git commit -m "feat: carry the gap phase through the broadcast hook"
```

---

### Task 5: Frontend — preload the next track during the gap

**Files:**
- Modify: `frontend/src/hooks/useYouTubePlayer.ts`
- Modify: `frontend/src/hooks/useYouTubePlayer.dom.test.ts`

First update the test factory in `useYouTubePlayer.dom.test.ts` so the suite
compiles with the new `BroadcastState` fields:

```ts
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
    genre: null,
    source: "schedule",
    offset: 0,
    fetchedAt: Date.now(),
    rttMs: 0,
    phase: "playing",
    nextTrack: null,
    secondsUntilStart: null,
    ...overrides,
  };
}
```

- [ ] **Step 1: Write the failing tests**

In `useYouTubePlayer.dom.test.ts`, add a helper inside the `describe` (above the
first `it`) or at file scope:

```ts
function nextTrack() {
  return { ...broadcast().track!, youtube_video_id: "b", title: "b" };
}
```

Add these tests:

```ts
  it("preloads the next track muted and paused during a gap", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 2,
        fetchedAt: Date.now(),
      }),
    });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "b",
        startSeconds: 0,
      }),
    );
    expect(players[0].mute).toHaveBeenCalled();
    expect(players[0].pauseVideo).toHaveBeenCalled();
    expect(players[0].playVideo).not.toHaveBeenCalled();
  });

  it("does not drift-correct or auto-resume during a gap", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast({ offset: 10 }) } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 5,
        fetchedAt: Date.now(),
      }),
    });
    players[0].seekTo.mockClear();
    players[0].playVideo.mockClear();
    players[0].getPlayerState.mockReturnValue(2); // PAUSED during preload
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(players[0].seekTo).not.toHaveBeenCalled();
    expect(players[0].playVideo).not.toHaveBeenCalled();
  });

  it("stops requesting a resync while the gap is on", async () => {
    vi.useFakeTimers();
    const onEnded = vi.fn();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, onEnded),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      players[0].opts.events.onStateChange({ data: 8 });
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 5,
        fetchedAt: Date.now(),
      }),
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
  });

  it("retries the upcoming track when preloading fails during a gap", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 10,
        fetchedAt: Date.now(),
      }),
    });
    act(() => {
      players[0].opts.events.onError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(players[0].loadVideoById).toHaveBeenLastCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/hooks/useYouTubePlayer.dom.test.ts`
Expected: FAIL — during the gap the hook currently plays/loads the previous track; new assertions fail.

- [ ] **Step 3: Implement preload + gating**

In `frontend/src/hooks/useYouTubePlayer.ts`, add a ref next to `currentVideoRef`:

```ts
  const preloadedVideoRef = useRef<string | null>(null);
```

Add the preload helper between `clearRetry` and `reloadCurrent` (it must be
defined before `reloadCurrent`, which lists it in its dependency array):

```ts
  const preloadNext = useCallback((next: Track) => {
    const player = playerRef.current;
    if (!player || !isPlayerReady(player)) return;
    try {
      player.mute();
      player.loadVideoById({
        videoId: next.youtube_video_id,
        startSeconds: 0,
      });
      player.pauseVideo();
    } catch {
      return;
    }
    preloadedVideoRef.current = next.youtube_video_id;
  }, []);
```

Replace `reloadCurrent` so a retry during a gap preloads the upcoming track:

```ts
  const reloadCurrent = useCallback(() => {
    const player = playerRef.current;
    const current = broadcastRef.current;
    if (!player || !isPlayerReady(player)) return;
    if (current?.phase === "gap" && current.nextTrack) {
      preloadNext(current.nextTrack);
      return;
    }
    if (!current?.track) return;
    try {
      player.loadVideoById({
        videoId: current.track.youtube_video_id,
        startSeconds: targetFor(current),
      });
      player.playVideo();
    } catch {
      // The iframe may still be initialising; the next attempt retries.
    }
  }, [preloadNext]);
```

Replace the body of the `useEffect(..., [broadcast])` sync effect with:

```ts
  useEffect(() => {
    const player = playerRef.current;
    if (!player || !broadcast?.track) return;
    if (!isPlayerReady(player)) return;
    const yt = window.YT;

    if (broadcast.phase === "gap") {
      if (yt && player.getPlayerState() === yt.PlayerState.PLAYING) {
        player.pauseVideo();
      }
      if (!broadcast.nextTrack) return;
      if (preloadedVideoRef.current !== broadcast.nextTrack.youtube_video_id) {
        preloadNext(broadcast.nextTrack);
      }
      return;
    }

    const videoId = broadcast.track.youtube_video_id;
    const target = targetFor(broadcast);
    if (currentVideoRef.current !== videoId) {
      currentVideoRef.current = videoId;
      endedRef.current = false;
      resetRetry();
      player.loadVideoById({ videoId, startSeconds: target });
      return;
    }
    if (!yt) return;
    const state = player.getPlayerState();
    const drift = Math.abs(player.getCurrentTime() - target);
    if (state === yt.PlayerState.ENDED && drift > DRIFT_THRESHOLD) {
      player.loadVideoById({ videoId, startSeconds: target });
    } else if (state === yt.PlayerState.PLAYING && drift > DRIFT_THRESHOLD) {
      player.seekTo(target, true);
    }
  }, [broadcast, preloadNext, resetRetry]);
```

Gate the 1-second watch interval (replace its existing body):

```ts
  useEffect(() => {
    const timer = window.setInterval(() => {
      const player = playerRef.current;
      const yt = window.YT;
      if (!isPlayerReady(player) || !yt) return;
      const current = broadcastRef.current;
      if (current?.track) {
        setProgress(player.getCurrentTime());
        const playerState = player.getPlayerState();
        if (current.phase !== "gap") {
          if (playerState === yt.PlayerState.PLAYING) {
            lastResumeAtRef.current = 0;
            const target = targetFor(current);
            if (Math.abs(player.getCurrentTime() - target) > DRIFT_THRESHOLD) {
              player.seekTo(target, true);
            }
          } else if (
            playerState === yt.PlayerState.PAUSED ||
            playerState === yt.PlayerState.CUED
          ) {
            // Mobile OSes pause the iframe player when the page is suspended
            // (screen lock, app switch). Resume at the live position so the
            // listener rejoins the broadcast; throttled in case the browser
            // keeps blocking playback.
            const now = Date.now();
            if (now - lastResumeAtRef.current >= RESUME_THROTTLE_MS) {
              lastResumeAtRef.current = now;
              player.seekTo(targetFor(current), true);
              player.playVideo();
            }
          }
        }
      }
      if (endedRef.current && current?.phase !== "gap") onEndedRef.current();
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/hooks/useYouTubePlayer.dom.test.ts`
Expected: PASS (new gap tests and every pre-existing player test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat: preload the next track during the song gap"
```

---

### Task 6: Frontend — start the preloaded track at the exact boundary

**Files:**
- Modify: `frontend/src/hooks/useYouTubePlayer.ts`
- Modify: `frontend/src/hooks/useYouTubePlayer.dom.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `useYouTubePlayer.dom.test.ts`:

```ts
  it("starts the preloaded track when the gap ends", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          fetchedAt: Date.now(),
          rttMs: 0,
        }),
      });
    });
    expect(players[0].loadVideoById).toHaveBeenCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(players[0].seekTo).toHaveBeenCalledWith(0, true);
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("cancels a pending gap start when a playing frame arrives", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          fetchedAt: Date.now(),
        }),
      });
    });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    act(() => {
      rerender({
        b: broadcast({
          track: nextTrack(),
          offset: 0,
          fetchedAt: Date.now(),
        }),
      });
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("reuses the preloaded video instead of reloading it when it goes live", async () => {
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      { initialProps: { b: broadcast() } },
    );
    await waitFor(() => expect(players.length).toBe(1));
    rerender({
      b: broadcast({
        phase: "gap",
        nextTrack: nextTrack(),
        secondsUntilStart: 2,
        fetchedAt: Date.now(),
      }),
    });
    await waitFor(() =>
      expect(players[0].loadVideoById).toHaveBeenCalledWith({
        videoId: "b",
        startSeconds: 0,
      }),
    );
    rerender({
      b: broadcast({ track: nextTrack(), offset: 0, fetchedAt: Date.now() }),
    });
    await waitFor(() => expect(players[0].seekTo).toHaveBeenCalled());
    expect(players[0].loadVideoById).toHaveBeenCalledTimes(1);
  });

  it("joins mid-gap with the next video paused and starts it at the boundary", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          fetchedAt: Date.now(),
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    expect(players[0].opts.videoId).toBe("b");
    expect(players[0].opts.playerVars.start).toBe(0);
    act(() => {
      players[0].opts.events.onReady();
    });
    expect(players[0].pauseVideo).toHaveBeenCalled();
    expect(players[0].loadVideoById).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/hooks/useYouTubePlayer.dom.test.ts`
Expected: FAIL — no timer starts the preloaded track; a mid-gap join still uses the previous video.

- [ ] **Step 3: Implement the timed start**

In `frontend/src/hooks/useYouTubePlayer.ts`:

Add refs next to `preloadedVideoRef`:

```ts
  const preloadedVideoRef = useRef<string | null>(null);
  const startTimerRef = useRef<number | null>(null);
```

Add helpers after `resetRetry` (so their dependency arrays can reference it):

```ts
  const clearStartTimer = useCallback(() => {
    if (startTimerRef.current !== null) {
      window.clearTimeout(startTimerRef.current);
      startTimerRef.current = null;
    }
  }, []);

  const startPreloaded = useCallback(
    (videoId: string, target: number) => {
      const player = playerRef.current;
      if (!player || !isPlayerReady(player)) return;
      preloadedVideoRef.current = null;
      currentVideoRef.current = videoId;
      endedRef.current = false;
      resetRetry();
      try {
        player.seekTo(Math.max(0, target), true);
        player.setVolume(volumeRef.current);
        if (mutedRef.current || volumeRef.current === 0) player.mute();
        else player.unMute();
        player.playVideo();
      } catch {
        // The iframe may still be initialising; the next frame retries.
      }
    },
    [resetRetry],
  );

  const scheduleGapStart = useCallback(
    (broadcast: BroadcastState) => {
      clearStartTimer();
      if (!broadcast.nextTrack || broadcast.secondsUntilStart === null) return;
      const boundaryAt =
        broadcast.fetchedAt +
        broadcast.rttMs / 2 +
        Math.max(0, broadcast.secondsUntilStart) * 1000;
      const delay = Math.max(0, boundaryAt - Date.now());
      startTimerRef.current = window.setTimeout(() => {
        startTimerRef.current = null;
        const current = broadcastRef.current;
        if (!current || current.phase !== "gap" || !current.nextTrack) return;
        if (preloadedVideoRef.current !== current.nextTrack.youtube_video_id) {
          return;
        }
        const position = Math.max(0, (Date.now() - boundaryAt) / 1000);
        startPreloaded(current.nextTrack.youtube_video_id, position);
      }, delay);
    },
    [clearStartTimer, startPreloaded],
  );
```

In the player-creation effect `useEffect(() => { if (!apiReady || !hasTrack || ...`, replace the initial-video block:

```ts
    const current = broadcastRef.current;
    if (!current) return;
    const joinDuringGap = current.phase === "gap" && current.nextTrack !== null;
    const initial = joinDuringGap ? current.nextTrack! : current.track;
    if (!initial) return;
    const initialId = initial.youtube_video_id;
    const start = joinDuringGap ? 0 : targetFor(current);
```

Replace the start of `onReady`:

```ts
        onReady: () => {
          setReady(true);
          player.setVolume(volumeRef.current);
          const live = broadcastRef.current;
          if (live?.phase === "gap" && live.nextTrack) {
            preloadedVideoRef.current = live.nextTrack.youtube_video_id;
            player.mute();
            player.pauseVideo();
            scheduleGapStart(live);
            return;
          }
          if (mutedRef.current) {
```

(the rest of `onReady` is unchanged).

After the `events` object, keep the existing lines and add the preload marker:

```ts
    playerRef.current = player;
    currentVideoRef.current = initialId;
    if (joinDuringGap) {
      preloadedVideoRef.current = initialId;
    }
```

Extend the creation effect cleanup:

```ts
    return () => {
      if (fallbackTimer !== null) window.clearTimeout(fallbackTimer);
      clearRetry();
      clearStartTimer();
      preloadedVideoRef.current = null;
      playerRef.current = null;
      ...
```

and its dependency array:

```ts
  }, [
    apiReady,
    hasTrack,
    containerId,
    scheduleGapStart,
    clearStartTimer,
    resetRetry,
    clearRetry,
  ]);
```

In the `[broadcast]` sync effect, add the timer handling:

```ts
    if (broadcast.phase === "gap") {
      if (yt && player.getPlayerState() === yt.PlayerState.PLAYING) {
        player.pauseVideo();
      }
      if (!broadcast.nextTrack) return;
      if (preloadedVideoRef.current !== broadcast.nextTrack.youtube_video_id) {
        preloadNext(broadcast.nextTrack);
      }
      scheduleGapStart(broadcast);
      return;
    }

    clearStartTimer();
    const videoId = broadcast.track.youtube_video_id;
    const target = targetFor(broadcast);
    if (currentVideoRef.current !== videoId) {
      if (preloadedVideoRef.current === videoId) {
        startPreloaded(videoId, target);
        return;
      }
      currentVideoRef.current = videoId;
      endedRef.current = false;
      resetRetry();
      player.loadVideoById({ videoId, startSeconds: target });
      return;
    }
```

Update the effect's dependency array:

```ts
  }, [
    broadcast,
    clearStartTimer,
    preloadNext,
    scheduleGapStart,
    startPreloaded,
    resetRetry,
  ]);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/hooks/useYouTubePlayer.dom.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat: start the preloaded track at the exact gap boundary"
```

---

### Task 7: Frontend — gap presentation on the radio page

**Files:**
- Modify: `frontend/src/pages/RadioPage.tsx`
- Modify: `frontend/src/pages/RadioPage.dom.test.tsx`

- [ ] **Step 1: Write the failing test**

Append to `RadioPage.dom.test.tsx`:

```tsx
  it("keeps the previous track visible during the gap without a progress bar", async () => {
    mocked.now.mockResolvedValue({
      genre: {
        id: 1,
        name: "Morning",
        slug: "morning",
        is_default: true,
        track_count: 1,
      },
      track: track("prev"),
      offset_seconds: 199,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "default",
      phase: "gap",
      next_track: track("next"),
      seconds_until_start: 1.5,
    });
    render(<RadioPage />);
    expect(await screen.findByText("prev")).toBeInTheDocument();
    expect(screen.getByText("On air")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText("3:20")).not.toBeInTheDocument();
    expect(screen.queryByText("next")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/RadioPage.dom.test.tsx`
Expected: FAIL — the progress bar is rendered during the gap.

- [ ] **Step 3: Implement the gap presentation**

In `frontend/src/pages/RadioPage.tsx`, add below the `offline` const:

```tsx
  const gap = state?.phase === "gap";
```

Change the header status:

```tsx
          <span className={player.playing || gap ? "led on" : "led"} aria-hidden="true" />
          <span>{player.playing || gap ? "On air" : "Standing by"}</span>
```

Wrap the progress block so it is hidden during a gap:

```tsx
              {!gap && (
                <div>
                  <div className="np-bar">
                    <div
                      className="np-bar-fill"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(pct)}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <div className="np-times">
                    <span>{formatClock(player.progress)}</span>
                    <span>{formatClock(duration)}</span>
                  </div>
                </div>
              )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/RadioPage.dom.test.tsx`
Expected: PASS (including all existing RadioPage tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx
git commit -m "feat: show the previous track without a progress bar during the gap"
```

---

### Task 8: Full verification, changelog, final commit

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS, no failures.

- [ ] **Step 2: Run the full frontend suite and typecheck**

Run: `cd frontend && npm test`
Expected: PASS.
Run: `cd frontend && npm run typecheck`
Expected: clean.

- [ ] **Step 3: Add the changelog entry**

Prepend to `docs/changelog.md` (most recent first), following the existing
format:

```markdown
## 2026-10-13 — song interval: 2s gap between songs so everyone starts together (issue #7)

Listeners on weak connections missed the first seconds of every song because
the next video started loading only when it was already on air. The backend now
inserts a station-wide silence gap (default 2s, `TRACK_GAP_SECONDS`) after every
automatically-advanced song: the boundary is `started_at + duration + gap`.
`/api/now` reports `phase: "gap"` with the just-finished `track`, the upcoming
`next_track`, and `seconds_until_start`. Listeners preload the next video muted
and paused during the gap and start it with a local timer at the exact boundary;
admin SKIP / PLAY NOW / AUTO still start a track immediately.

- `backend/app/config.py`, `backend/.env.example`: new `TRACK_GAP_SECONDS`
  setting (float, default 2, 0–30; 0 disables the gap).
- `backend/app/broadcast.py`: gap folded into `advance()`/`_advance_manual()`
  boundaries; `get_current()` reports the gap phase and dry-runs the boundary
  to expose the next track.
- `backend/app/schemas.py`, `backend/app/routers/now.py`: `NowOut` gains
  `phase`, `next_track`, `seconds_until_start`.
- `frontend/src/types.ts`, `frontend/src/hooks/useBroadcast.ts`: gap fields
  carried through poll + WebSocket frames.
- `frontend/src/hooks/useYouTubePlayer.ts`: preload (mute + load + pause),
  boundary-timed start, drift/resume gating during the gap, preloaded-video
  reuse, gap-aware retry, mid-gap join.
- `frontend/src/pages/RadioPage.tsx`: previous track stays visible during the
  gap; progress bar and times hidden; header keeps "On air".
- **Container restart required (backend + frontend):**
  `docker compose up -d --build backend frontend`, then hard-refresh the
  browser (Ctrl+Shift+R).
- Verification: `python -m pytest -q` — <result>; `npm test` — <result>;
  `npm run typecheck` — <result>.
```

Fill the `<result>` placeholders with the actual outputs from Steps 1–2.

- [ ] **Step 4: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: changelog for the between-song gap (issue #7)"
```

- [ ] **Step 5: Push the branch and open the PR**

```bash
git push -u origin feat/song-interval-gap
gh pr create --title "feat: 2s gap between songs for synced starts (issue #7)" \
  --body "Implements #7. See docs/superpowers/specs/2026-10-13-song-interval-gap-design.md"
```

(Confirm `gh auth status` shows `xjojoramirez` active before creating the PR.)
