# Preload the next song ahead of the boundary (issue #6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second hidden player pre-rolls the next track muted during a configurable lead window (default 20 s), then swaps in at the boundary so song starts have a warm buffer; every failure path falls back to today's 2 s gap preload.

**Architecture:** Backend exposes `next_track` + `seconds_until_start` while playing and a tunable `PRELOAD_LEAD_SECONDS` (in `NowOut`). `useYouTubePlayer` gains a lazily-created second player (preload role) that ping-pongs with the active player on each boundary.

**Tech Stack:** FastAPI + SQLModel + pytest; React 18 + TypeScript + Vitest (jsdom) + Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-14-preload-next-song-design.md`

**Branch:** `feat/preload-next-song` (already checked out; spec committed there).

**File structure (what changes and why):**

- `backend/app/config.py` — `preload_lead_seconds` setting (+ validator).
- `backend/.env.example` — document `PRELOAD_LEAD_SECONDS`.
- `backend/app/broadcast.py` — extract `_peek_next()`; expose next track while playing.
- `backend/app/schemas.py` — `NowOut.preload_lead_seconds`.
- `backend/app/routers/now.py` — `build_now` passes the setting.
- `backend/tests/test_config.py`, `backend/tests/test_now.py` — new/updated tests.
- `frontend/src/types.ts`, `frontend/src/hooks/useBroadcast.ts` — carry `preloadLead`.
- `frontend/src/pages/RadioPage.tsx` — `#yt-preload` container div.
- `frontend/src/hooks/useYouTubePlayer.ts` — dual-player pre-roll (lazy creation, arm, swap, fallback, cancel, teardown).
- `frontend/src/hooks/useBroadcast.dom.test.ts`, `frontend/src/pages/RadioPage.dom.test.tsx`, `frontend/src/hooks/useYouTubePlayer.dom.test.ts` — tests.

Backend test command (from `backend/`): `python -m pytest -q`.
Frontend (from `frontend/`): `npm test -- <file>`, full suite `npm test`.

---

### Task 1: Backend — `PRELOAD_LEAD_SECONDS` setting

**Files:**
- Test: `backend/tests/test_config.py`
- Modify: `backend/app/config.py`, `backend/.env.example`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_config.py`:

```python
def test_preload_lead_default(monkeypatch):
    monkeypatch.delenv("PRELOAD_LEAD_SECONDS", raising=False)
    assert Settings(_env_file=None).preload_lead_seconds == 20.0


def test_preload_lead_rejects_out_of_range():
    with pytest.raises(Exception):
        Settings(_env_file=None, preload_lead_seconds=-1)
    with pytest.raises(Exception):
        Settings(_env_file=None, preload_lead_seconds=301)


def test_preload_lead_accepts_zero_and_fraction():
    assert Settings(_env_file=None, preload_lead_seconds=0).preload_lead_seconds == 0
    assert Settings(_env_file=None, preload_lead_seconds=12.5).preload_lead_seconds == 12.5
```

- [ ] **Step 2: Run to verify it fails**

```
python -m pytest -q tests/test_config.py
```

Expected: FAIL — `TypeError`/validation error for the unknown `preload_lead_seconds`.

- [ ] **Step 3: Implement**

In `backend/app/config.py`, add the field after `track_gap_seconds`:

```python
    track_gap_seconds: float = 2.0
    preload_lead_seconds: float = 20.0
```

and the validator after `_valid_gap`:

```python
    @field_validator("preload_lead_seconds")
    @classmethod
    def _valid_preload_lead(cls, v: float) -> float:
        if not 0 <= v <= 300:
            raise ValueError("preload_lead_seconds must be between 0 and 300")
        return v
```

In `backend/.env.example`, after `TRACK_GAP_SECONDS=2`:

```
PRELOAD_LEAD_SECONDS=20
```

- [ ] **Step 4: Run to verify it passes**

```
python -m pytest -q tests/test_config.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add backend/app/config.py backend/.env.example backend/tests/test_config.py
git commit -m "feat: add PRELOAD_LEAD_SECONDS setting for next-song pre-roll (issue #6)"
```

---

### Task 2: Backend — expose the next track while playing

**Files:**
- Test: `backend/tests/test_now.py`
- Modify: `backend/app/broadcast.py:231-297`

- [ ] **Step 1: Update the two stale tests and add the new one**

In `backend/tests/test_now.py`, replace lines 66-68 of
`test_now_returns_track_offset_and_server_time`:

```python
    assert body["phase"] == "playing"
    assert body["next_track"]["youtube_video_id"] == "vid"  # one track, wraps
    assert 201 < body["seconds_until_start"] <= 202  # 200 s + 2 s gap
```

In `test_now_reports_gap_between_songs`, replace lines 273-275:

```python
        assert first.phase == "playing"
        assert first.next_track.youtube_video_id == "vid"  # wraps on one track
        assert first.seconds_until_start == 202  # 200 s + 2 s gap
```

Append the new test:

```python
def test_now_reports_next_track_while_playing(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed_genre(s, "morning", default=True, video="first", duration=200)
        pl = s.exec(select(Playlist).where(Playlist.genre_id == st.id)).one()
        s.add(
            TrackCache(
                playlist_id=pl.id,
                youtube_video_id="second",
                title="T2",
                artist="A",
                position=1,
                duration_seconds=120,
            )
        )
        s.commit()
    with Session(engine) as s:
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        first = get_current(s, t0)
        assert first.phase == "playing"
        assert first.track.youtube_video_id == "first"
        assert first.next_track.youtube_video_id == "second"
        assert first.seconds_until_start == 202

        later = get_current(s, t0 + timedelta(seconds=30))
        assert later.next_track.youtube_video_id == "second"
        assert later.seconds_until_start == 172
```

- [ ] **Step 2: Run to verify RED**

```
python -m pytest -q tests/test_now.py
```

Expected: 3 FAILs (`next_track` is `None` while playing) / others pass.

- [ ] **Step 3: Implement the peek**

In `backend/app/broadcast.py`, add this helper directly above `get_current`:

```python
def _peek_next(
    session: Session, state: BroadcastState, now: datetime
) -> tuple[TrackCache | None, float]:
    """The track that starts after the current one, and seconds until it starts.

    Evaluated at the current track's boundary (track end + gap), which also
    covers schedule genre changes and manual queues.
    """
    gap = get_settings().track_gap_seconds
    duration = state.durations[state.index] or 1
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
        next_track = session.get(TrackCache, following.track_ids[following.index])
    return next_track, max(0.0, (end - now).total_seconds())
```

Then replace the tail of `get_current` (the `if now >= state.started_at + ...` gap
branch and the final `return NowState(genre, track, offset, source)`) with:

```python
        if now >= state.started_at + timedelta(seconds=duration):
            next_track, until = _peek_next(session, state, now)
            return NowState(
                genre, track, offset, source, "gap", next_track, until
            )
        next_track, until = _peek_next(session, state, now)
        return NowState(
            genre, track, offset, source, "playing", next_track, until
        )
```

- [ ] **Step 4: Run the focused suites, expect GREEN**

```
python -m pytest -q tests/test_now.py tests/test_broadcast.py
```

Expected: all pass. Then the full backend suite:

```
python -m pytest -q
```

Expected: all pass (any other failure means a test asserted the old null
fields — update it the same way).

- [ ] **Step 5: Commit**

```
git add backend/app/broadcast.py backend/tests/test_now.py
git commit -m "feat: report the next track while playing so clients can pre-roll (issue #6)"
```

---

### Task 3: Backend — `NowOut.preload_lead_seconds`

**Files:**
- Test: `backend/tests/test_now.py`
- Modify: `backend/app/schemas.py`, `backend/app/routers/now.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_now.py`:

```python
def test_now_endpoint_reports_preload_lead(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True)
    body = _client(engine).get("/api/now").json()
    assert body["preload_lead_seconds"] == 20.0
```

- [ ] **Step 2: Run to verify RED**

```
python -m pytest -q tests/test_now.py
```

Expected: FAIL — `KeyError: 'preload_lead_seconds'`.

- [ ] **Step 3: Implement**

`backend/app/schemas.py`, in `NowOut` after `seconds_until_start`:

```python
    preload_lead_seconds: float = 20.0
```

`backend/app/routers/now.py`: add the import

```python
from app.config import get_settings
```

and extend the `NowOut(...)` call in `build_now`:

```python
        seconds_until_start=state.seconds_until_start,
        preload_lead_seconds=get_settings().preload_lead_seconds,
```

- [ ] **Step 4: Run to verify GREEN**

```
python -m pytest -q tests/test_now.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```
git add backend/app/schemas.py backend/app/routers/now.py backend/tests/test_now.py
git commit -m "feat: expose preload_lead_seconds in /api/now (issue #6)"
```

---

### Task 4: Frontend — carry `preloadLead` through the client state

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/hooks/useBroadcast.ts`
- Test: `frontend/src/hooks/useBroadcast.dom.test.ts`

- [ ] **Step 1: Write the failing test**

Append inside `describe("useBroadcast", ...)` in
`frontend/src/hooks/useBroadcast.dom.test.ts`:

```tsx
  it("maps the preload lead from a poll", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(nowResponse({ preload_lead_seconds: 15 })),
    );
    const { result } = renderHook(() => useBroadcast());
    await waitFor(() => expect(result.current.state?.preloadLead).toBe(15));
  });
```

- [ ] **Step 2: Run to verify RED**

```
npm test -- src/hooks/useBroadcast.dom.test.ts
```

Expected: FAIL — `preloadLead` is `undefined`.

- [ ] **Step 3: Implement**

`frontend/src/types.ts` — extend `BroadcastNow` (optional so existing test
mocks keep type-checking):

```ts
  seconds_until_start: number | null;
  preload_lead_seconds?: number;
```

`frontend/src/hooks/useBroadcast.ts` — add to `BroadcastState` after
`secondsUntilStart`:

```ts
  /** Lead seconds for pre-rolling the next track (0 disables pre-roll). */
  preloadLead: number;
```

and in `toState`:

```ts
    secondsUntilStart: data.seconds_until_start ?? null,
    preloadLead: data.preload_lead_seconds ?? 0,
```

- [ ] **Step 4: Run to verify GREEN**

```
npm test -- src/hooks/useBroadcast.dom.test.ts
```

Expected: all pass.

- [ ] **Step 5: Commit**

```
git add frontend/src/types.ts frontend/src/hooks/useBroadcast.ts frontend/src/hooks/useBroadcast.dom.test.ts
git commit -m "feat: map preload_lead_seconds into the broadcast state (issue #6)"
```

---

### Task 5: Frontend — the `#yt-preload` container

**Files:**
- Modify: `frontend/src/pages/RadioPage.tsx:45`
- Test: `frontend/src/pages/RadioPage.dom.test.tsx`

- [ ] **Step 1: Write the failing test**

Append inside `describe("RadioPage", ...)`:

```tsx
  it("renders the hidden preload player container", async () => {
    const { container } = render(<RadioPage />);
    await screen.findByText("live");
    expect(container.querySelector("#yt-preload")).not.toBeNull();
  });
```

- [ ] **Step 2: Run to verify RED**

```
npm test -- src/pages/RadioPage.dom.test.tsx
```

Expected: the new test FAILS (`null`).

- [ ] **Step 3: Implement**

In `frontend/src/pages/RadioPage.tsx`, directly after the existing player div:

```tsx
      <div id="yt-player" className="hidden-player" />
      <div id="yt-preload" className="hidden-player" />
```

- [ ] **Step 4: Run to verify GREEN**

```
npm test -- src/pages/RadioPage.dom.test.tsx
```

Expected: all pass.

- [ ] **Step 5: Commit**

```
git add frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx
git commit -m "feat: render the hidden preload player container (issue #6)"
```

---

### Task 6: Frontend — dual-player pre-roll in `useYouTubePlayer`

All steps in this task edit `frontend/src/hooks/useYouTubePlayer.ts` and
`frontend/src/hooks/useYouTubePlayer.dom.test.ts`, and run:

```
npm test -- src/hooks/useYouTubePlayer.dom.test.ts
```

**Shared test scaffolding (do first):**

- Add `preloadLead: 0,` to the `broadcast()` helper's defaults (keeps every
  existing test byte-identical in behavior).
- In the existing `beforeEach`, after `players = [];`, add:

```ts
    if (!document.getElementById("yt-preload")) {
      const preloadEl = document.createElement("div");
      preloadEl.id = "yt-preload";
      document.body.appendChild(preloadEl);
    }
```

---

#### Task 6a: Arm the pre-roll inside the lead window

- [ ] **Step 1: Write the failing tests**

```tsx
  it("pre-rolls the next track muted inside the lead window", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(players.length).toBe(1);
    act(() => {
      vi.advanceTimersByTime(5000); // crosses boundaryAt - 20 s
    });
    expect(players.length).toBe(2);
    expect(players[1].loadVideoById).toHaveBeenCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
    expect(players[1].mute).toHaveBeenCalled();
    expect(players[1].playVideo).toHaveBeenCalled();
    expect(players[0].loadVideoById).not.toHaveBeenCalled();
  });

  it("does not pre-roll when the lead is disabled", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 5,
          preloadLead: 0,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(players.length).toBe(1);
  });
```

- [ ] **Step 2: Run to verify RED**

Expected: the first test FAILS (`players.length` stays 1 — no second player);
the second is a regression pin and passes.

- [ ] **Step 3: Implement**

In `useYouTubePlayer.ts`, add after the `YTNamespace` interface:

```ts
const PRELOAD_CONTAINER_ID = "yt-preload";
```

In the hook, after `lastResumeAtRef`, add the preload refs:

```ts
  const preloadRef = useRef<YTPlayer | null>(null);
  const preloadVideoRef = useRef<string | null>(null);
  const preloadBoundaryRef = useRef<number | null>(null);
  const preloadFailedRef = useRef(false);
  const preloadTimerRef = useRef<number | null>(null);
```

After `clearRetry`, add:

```ts
  const clearPreloadTimer = useCallback(() => {
    if (preloadTimerRef.current !== null) {
      window.clearTimeout(preloadTimerRef.current);
      preloadTimerRef.current = null;
    }
  }, []);

  const resetPreload = useCallback(() => {
    const preload = preloadRef.current;
    if (preload && isPlayerReady(preload)) {
      try {
        preload.pauseVideo();
      } catch {
        // The iframe may still be initialising.
      }
    }
    preloadVideoRef.current = null;
    preloadBoundaryRef.current = null;
  }, []);

  const ensurePreloadPlayer = useCallback((): YTPlayer | null => {
    if (preloadRef.current) return preloadRef.current;
    const yt = window.YT;
    if (!yt || !document.getElementById(PRELOAD_CONTAINER_ID)) return null;
    const player = new yt.Player(PRELOAD_CONTAINER_ID, {
      height: "1",
      width: "1",
      playerVars: {
        autoplay: 1,
        mute: 1,
        controls: 0,
        disablekb: 1,
        playsinline: 1,
      },
    });
    preloadRef.current = player;
    return player;
  }, []);
```

Then `maybeArmPreload` + the ref that makes it visible to the 1 s tick (place
after `scheduleGapStart`):

```ts
  const maybeArmPreload = useCallback(
    (current: BroadcastState) => {
      if (current.phase !== "playing") return;
      if (!current.track || !current.nextTrack) return;
      if (current.preloadLead <= 0 || preloadFailedRef.current) return;
      if (current.secondsUntilStart === null) return;
      const boundaryAt =
        current.fetchedAt +
        current.rttMs / 2 +
        Math.max(0, current.secondsUntilStart) * 1000;
      if (Date.now() < boundaryAt - current.preloadLead * 1000) return;
      const preload = ensurePreloadPlayer();
      if (!preload || !isPlayerReady(preload)) return;
      const nextId = current.nextTrack.youtube_video_id;
      try {
        if (
          preloadVideoRef.current !== nextId ||
          preloadBoundaryRef.current !== boundaryAt
        ) {
          preload.mute();
          preload.loadVideoById({ videoId: nextId, startSeconds: 0 });
          preload.playVideo();
          preloadVideoRef.current = nextId;
          preloadBoundaryRef.current = boundaryAt;
        } else if (
          window.YT &&
          preload.getPlayerState() !== window.YT.PlayerState.PLAYING
        ) {
          preload.mute();
          preload.playVideo();
        }
      } catch {
        preloadFailedRef.current = true;
      }
    },
    [ensurePreloadPlayer],
  );

  const armPreloadRef = useRef(maybeArmPreload);
  armPreloadRef.current = maybeArmPreload;
```

Finally, in the 1 s interval tick, inside the existing
`if (current.phase !== "gap") {` block (first line):

```ts
        if (current.phase !== "gap") {
          armPreloadRef.current(current);
          if (playerState === yt.PlayerState.PLAYING) {
```

- [ ] **Step 4: Run to verify GREEN**

Expected: both tests pass, and the full existing suite for this file still
passes.

- [ ] **Step 5: Commit**

```
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat: pre-roll the next track muted inside the lead window (issue #6)"
```

---

#### Task 6b: Swap to the preload player at the boundary

- [ ] **Step 1: Write the failing tests**

```tsx
  it("swaps to the preloaded player at the boundary", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 1 }); // on air
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    act(() => {
      vi.advanceTimersByTime(20000); // reach the boundary
    });
    expect(players[1].seekTo).toHaveBeenCalled();
    expect(players[1].playVideo).toHaveBeenCalled();
    expect(players[1].setVolume).toHaveBeenCalledWith(70);
    expect(players[0].pauseVideo).toHaveBeenCalled();
    expect(result.current.playing).toBe(true);
  });

  it("ignores state events from the demoted player after a swap", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 1 });
    });
    act(() => {
      vi.advanceTimersByTime(25000); // arm + swap
    });
    act(() => {
      players[0].opts.events.onStateChange({ data: 2 }); // late PAUSED
    });
    expect(result.current.playing).toBe(true);
  });
```

- [ ] **Step 2: Run to verify RED**

Expected: both FAIL (no swap; the late PAUSED flips `playing` to false).

- [ ] **Step 3: Implement**

**Ordering (important):** the preload helpers added in Task 6a must sit in this
file order, or the `useCallback` dependency arrays will reference
not-yet-initialised constants:

1. `resetRetry` → 2. `handleStateChange` (new) → 3. `clearPreloadTimer` →
4. `resetPreload` → 5. `ensurePreloadPlayer` → 6. `clearStartTimer` →
7. `startPreloaded` → 8. `scheduleGapStart` → 9. `scheduleSwap` (new) →
10. `maybeArmPreload` → 11. `armPreloadRef`

In practice: in Task 6b, move the three helpers added in 6a
(`clearPreloadTimer`, `resetPreload`, `ensurePreloadPlayer`) from their 6a spot
to just after the new `handleStateChange`, and add `scheduleSwap` after
`scheduleGapStart`.

In `useYouTubePlayer.ts`, after `resetRetry`, add the shared, identity-gated
state handler:

```ts
  const handleStateChange = useCallback(
    (player: YTPlayer, data: number) => {
      if (playerRef.current !== player) return;
      const yt = window.YT;
      const isPlaying = yt != null && data === yt.PlayerState.PLAYING;
      setPlaying(isPlaying);
      if (isPlaying) {
        endedRef.current = false;
        resetRetry();
      }
      if (yt != null && data === yt.PlayerState.ENDED) {
        endedRef.current = true;
        onEndedRef.current();
      }
    },
    [resetRetry],
  );
```

In the main player-creation effect, replace the inline `onStateChange` body:

```ts
        onStateChange: (e: { data: number }) => {
          handleStateChange(player, e.data);
        },
```

(add `handleStateChange` to that effect's dependency array).

Add the swap scheduler **after** `scheduleGapStart` (before
`maybeArmPreload`, since the latter's dependency array references it):

```ts
  const scheduleSwap = useCallback(
    (nextId: string, boundaryAt: number) => {
      clearPreloadTimer();
      preloadTimerRef.current = window.setTimeout(() => {
        preloadTimerRef.current = null;
        const preload = preloadRef.current;
        if (!preload || !isPlayerReady(preload)) return;
        if (preloadVideoRef.current !== nextId) return;
        const position = Math.max(0, (Date.now() - boundaryAt) / 1000);
        const previous = playerRef.current;
        try {
          preload.seekTo(position, true);
          preload.setVolume(volumeRef.current);
          if (mutedRef.current || volumeRef.current === 0) preload.mute();
          else preload.unMute();
          preload.playVideo();
        } catch {
          return;
        }
        playerRef.current = preload;
        preloadRef.current = previous;
        preloadVideoRef.current = null;
        preloadBoundaryRef.current = null;
        preloadedVideoRef.current = null;
        currentVideoRef.current = nextId;
        endedRef.current = false;
        resetRetry();
        if (previous && isPlayerReady(previous)) {
          try {
            previous.pauseVideo();
            previous.mute();
          } catch {
            // Demoting the old player is best-effort.
          }
        }
      }, Math.max(0, boundaryAt - Date.now()));
    },
    [clearPreloadTimer, resetRetry],
  );
```

Extend `maybeArmPreload`'s final lines (and its dependency array):

```ts
      } catch {
        preloadFailedRef.current = true;
      }
      scheduleSwap(nextId, boundaryAt);
    },
    [ensurePreloadPlayer, scheduleSwap],
  );
```

Give the lazily-created preload player the same gated handler in
`ensurePreloadPlayer` (and add `handleStateChange` to its dependency array):

```ts
    const player = new yt.Player(PRELOAD_CONTAINER_ID, {
      height: "1",
      width: "1",
      playerVars: {
        autoplay: 1,
        mute: 1,
        controls: 0,
        disablekb: 1,
        playsinline: 1,
      },
      events: {
        onStateChange: (e: { data: number }) => {
          handleStateChange(player, e.data);
        },
      },
    });
```

- [ ] **Step 4: Run to verify GREEN**

Expected: both new tests pass; existing suite passes.

- [ ] **Step 5: Commit**

```
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat: swap to the preloaded player at the song boundary (issue #6)"
```

---

#### Task 6c: Keep the gap path idle when the preload is healthy

- [ ] **Step 1: Write the failing test**

```tsx
  it("keeps the active player idle during a gap when the preload is healthy", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      {
        initialProps: {
          b: broadcast({
            nextTrack: nextTrack(),
            secondsUntilStart: 25,
            preloadLead: 20,
          }),
        },
      },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    players[0].loadVideoById.mockClear();
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          preloadLead: 20,
          fetchedAt: Date.now(),
        }),
      });
    });
    expect(players[0].loadVideoById).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(players[1].playVideo).toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run to verify RED**

Expected: FAIL — the gap path loads `"b"` into the active player.

- [ ] **Step 3: Implement**

In the broadcast effect's gap branch, after the existing pause line, insert the
healthy check before the fallback:

```ts
    if (broadcast.phase === "gap") {
      if (yt && player.getPlayerState() === yt.PlayerState.PLAYING) {
        player.pauseVideo();
      }
      if (!broadcast.nextTrack) return;
      const nextId = broadcast.nextTrack.youtube_video_id;
      const preloadHealthy =
        preloadRef.current !== null &&
        isPlayerReady(preloadRef.current) &&
        preloadVideoRef.current === nextId;
      if (preloadHealthy) {
        clearStartTimer();
        const boundaryAt =
          broadcast.fetchedAt +
          broadcast.rttMs / 2 +
          Math.max(0, broadcast.secondsUntilStart ?? 0) * 1000;
        scheduleSwap(nextId, boundaryAt);
        return;
      }
      if (preloadedVideoRef.current !== nextId) {
        preloadNext(broadcast.nextTrack);
      }
      scheduleGapStart(broadcast);
      return;
    }
```

(add `scheduleSwap` to the effect's dependency array).

- [ ] **Step 4: Run to verify GREEN**

Expected: pass, and the existing gap-fallback tests (which run with
`preloadLead: 0`) still pass.

- [ ] **Step 5: Commit**

```
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat: skip the gap preload when the pre-roll is healthy (issue #6)"
```

---

#### Task 6d: Fall back when the pre-roll player errors

- [ ] **Step 1: Write the failing test**

```tsx
  it("falls back to the gap preload when the pre-roll player errors", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      {
        initialProps: {
          b: broadcast({
            nextTrack: nextTrack(),
            secondsUntilStart: 25,
            preloadLead: 20,
          }),
        },
      },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    act(() => {
      players[1].opts.events.onError();
    });
    players[0].loadVideoById.mockClear();
    act(() => {
      rerender({
        b: broadcast({
          phase: "gap",
          nextTrack: nextTrack(),
          secondsUntilStart: 2,
          preloadLead: 20,
          fetchedAt: Date.now(),
        }),
      });
    });
    expect(players[0].loadVideoById).toHaveBeenCalledWith({
      videoId: "b",
      startSeconds: 0,
    });
  });
```

- [ ] **Step 2: Run to verify RED**

Expected: FAIL — nothing marks the preload as failed, so the healthy branch
skips the fallback.

- [ ] **Step 3: Implement**

In `ensurePreloadPlayer`, add the error handler to the player options:

```ts
      events: {
        onError: () => {
          preloadFailedRef.current = true;
          resetPreload();
        },
        onStateChange: (e: { data: number }) => {
          handleStateChange(player, e.data);
        },
      },
```

(add `resetPreload` to `ensurePreloadPlayer`'s dependency array). Also guard the
healthy check in the gap branch by adding `!preloadFailedRef.current &&`.

- [ ] **Step 4: Run to verify GREEN**

Expected: pass.

- [ ] **Step 5: Commit**

```
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "fix: fall back to the gap preload when the pre-roll player errors (issue #6)"
```

---

#### Task 6e: Cancel the pre-roll when the track changes

- [ ] **Step 1: Write the failing test**

```tsx
  it("cancels the pre-roll when the current track changes", async () => {
    vi.useFakeTimers();
    const { rerender } = renderHook(
      ({ b }: { b: BroadcastState }) =>
        useYouTubePlayer("yt-player", b, vi.fn()),
      {
        initialProps: {
          b: broadcast({
            nextTrack: nextTrack(),
            secondsUntilStart: 25,
            preloadLead: 20,
          }),
        },
      },
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    act(() => {
      rerender({
        b: broadcast({
          track: { ...broadcast().track!, youtube_video_id: "c", title: "c" },
          offset: 0,
          fetchedAt: Date.now(),
        }),
      });
    });
    expect(players[1].pauseVideo).toHaveBeenCalled();
    expect(players[0].loadVideoById).toHaveBeenCalledWith({
      videoId: "c",
      startSeconds: expect.any(Number),
    });
    players[1].playVideo.mockClear();
    act(() => {
      vi.advanceTimersByTime(25000); // the stale swap timer would have fired
    });
    expect(players[1].playVideo).not.toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run to verify RED**

Expected: FAIL — the preload player is neither paused nor cleared.

- [ ] **Step 3: Implement**

In the broadcast effect's playing branch, extend the track-change block:

```ts
    if (currentVideoRef.current !== videoId) {
      clearPreloadTimer();
      resetPreload();
      preloadFailedRef.current = false;
      if (preloadedVideoRef.current === videoId) {
```

(keep the rest of the existing block unchanged; add `clearPreloadTimer` and
`resetPreload` to the effect's dependency array).

- [ ] **Step 4: Run to verify GREEN**

Expected: pass.

- [ ] **Step 5: Commit**

```
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "feat: cancel the pre-roll when the track changes (issue #6)"
```

---

#### Task 6f: Tear down both players

- [ ] **Step 1: Write the failing test**

```tsx
  it("destroys both players and clears timers on unmount", async () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() =>
      useYouTubePlayer(
        "yt-player",
        broadcast({
          nextTrack: nextTrack(),
          secondsUntilStart: 25,
          preloadLead: 20,
        }),
        vi.fn(),
      ),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      vi.advanceTimersByTime(5000); // arm
    });
    expect(players.length).toBe(2);
    unmount();
    expect(players[0].destroy).toHaveBeenCalled();
    expect(players[1].destroy).toHaveBeenCalled();
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(60000);
      });
    }).not.toThrow();
  });
```

- [ ] **Step 2: Run to verify RED**

Expected: FAIL — the preload player is never destroyed.

- [ ] **Step 3: Implement**

In the main player-creation effect's cleanup (before `player.destroy()`), add:

```ts
      const preload = preloadRef.current;
      preloadRef.current = null;
      preloadVideoRef.current = null;
      preloadBoundaryRef.current = null;
      preloadFailedRef.current = false;
      clearPreloadTimer();
      if (preload) {
        try {
          preload.destroy();
        } catch {
          // The player may already have been torn down by the iframe API.
        }
      }
```

(add `clearPreloadTimer` to the effect's dependency array).

- [ ] **Step 4: Run to verify GREEN**

Expected: pass.

- [ ] **Step 5: Commit**

```
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.dom.test.ts
git commit -m "fix: tear down the preload player on unmount (issue #6)"
```

---

### Task 7: Full verification + changelog

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Run the full suites**

```
python -m pytest -q          # from backend/
npm test                     # from frontend/
npm run typecheck            # from frontend/
npm run build                # from frontend/
```

Expected: all backend tests pass; all frontend tests pass (the count grows
from the previous 251); typecheck clean; build succeeds. Record the actual
numbers for the changelog.

- [ ] **Step 2: Add the changelog entry (most recent first)**

```markdown
## 2026-10-14 — preload the next song ahead of the boundary (issue #6)

Listeners on weak connections started every song cold: the only preload was
the 2 s gap. The backend now reports `next_track` + `seconds_until_start`
while a song is playing, and the player keeps a second, hidden YouTube
player that pre-rolls the next track muted for `PRELOAD_LEAD_SECONDS`
(default 20, 0 disables) — the boundary then swaps the pre-rolled player in
with a warm buffer. Any preload failure falls back to the existing gap
preload; mid-gap joiners, skips, and admin actions keep working.

- `backend/app/config.py`, `backend/.env.example`: new `PRELOAD_LEAD_SECONDS`
  setting (float, default 20, 0–300; 0 disables).
- `backend/app/broadcast.py`: `_peek_next()` extracted; `get_current()`
  reports the next track and seconds-until-start while playing.
- `backend/app/schemas.py`, `backend/app/routers/now.py`: `NowOut` gains
  `preload_lead_seconds`.
- `frontend/src/types.ts`, `frontend/src/hooks/useBroadcast.ts`: carry
  `preloadLead` from poll + WebSocket frames.
- `frontend/src/hooks/useYouTubePlayer.ts`: lazy preload player, muted
  pre-roll in the lead window, boundary swap, healthy/failure branches,
  cancellation on track change, dual-player teardown.
- `frontend/src/pages/RadioPage.tsx`: hidden `#yt-preload` container.
- Design/plan: `docs/superpowers/specs/2026-10-14-preload-next-song-design.md`,
  `docs/superpowers/plans/2026-10-14-preload-next-song.md`.
- **Container restart required (backend + frontend):**
  `docker compose up -d --build backend frontend`, then hard-refresh the
  browser (Ctrl+Shift+R).
- Verification: `python -m pytest -q` — <N> passed; `npm test` — <N> passed;
  `npm run typecheck` — clean.
```

- [ ] **Step 3: Commit**

```
git add docs/changelog.md docs/superpowers/plans/2026-10-14-preload-next-song.md
git commit -m "docs: changelog + plan for the next-song pre-roll (issue #6)"
```

---

### Task 8: Manual verification + handoff

- [ ] **Step 1: Rebuild and test locally**

```
docker compose up -d --build backend frontend
```

Then, in the browser (hard-refresh) with DevTools → Network → throttling set
to "Slow 3G": confirm the pre-roll player buffers ahead (Media panel shows
two YouTube players once the lead window opens) and the next song starts
without the usual stall. Compare against `PRELOAD_LEAD_SECONDS=0` if needed.

- [ ] **Step 2: Push and open the PR**

```
git push -u origin feat/preload-next-song
gh auth switch --user xjojoramirez   # confirm the active account first
gh pr create --base main --title "feat: preload the next song ahead of the boundary (issue #6)" --body-file <body>
```

PR body must include `Closes #6`, the changed-files summary, verification
numbers, and the deploy command.

---

## Self-review notes

- Spec coverage: peek while playing (Task 2), `PRELOAD_LEAD_SECONDS` + exposure
  (Tasks 1, 3), client mapping (Task 4), container (Task 5), arm/swap/fallback/
  cancel/teardown (Tasks 6a–6f), tests for every behavior, traffic note covered
  by the lead = 0 path, manual throttled check (Task 8).
- The `preloadLead: 0` default in the test helper intentionally keeps every
  pre-existing test on the fallback path — they pin "nothing regresses".
- Single-track genres are handled by keying the pre-roll on
  `(video id, boundaryAt)`; re-arming is exercised implicitly in Task 6b's
  boundary test flow.
