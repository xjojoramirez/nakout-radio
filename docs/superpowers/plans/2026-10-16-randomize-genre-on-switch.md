# Randomize Genre Queue on Run Start — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the broadcast automatically starts a genre run, shuffle that genre's tracks for the live queue, without persisting the order or touching manual operator controls.

**Architecture:** Add small pure shuffle helpers to `backend/app/broadcast.py` and an optional `randomize` hook on `advance()`. The hook is invoked only at automatic queue-rebuild points (initial fill, genre change, loop wrap) and in `_init`; the seed is derived from `(genre_id, run start time)` so `_peek_next` reproduces the same order the committed run plays. Backend-only; no API, DB, or frontend changes.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-randomize-genre-on-switch-design.md`

**Branch:** `feat/randomize-genre-on-switch-14` (base `main`; `main` is protected, land via PR).

**Test command for every step in this plan:** `cd backend && python -m pytest -q`

---

## File Structure

- `backend/app/broadcast.py` — the only production file. Gains `_run_seed`, `_rng_factory`, `_shuffle_pairs`, `_auto_randomize`, an optional `randomize` parameter on `advance()`, shuffle in `_init()`, and the `randomize=_auto_randomize` argument at the three production `advance()` call sites (`get_current`, `_load_and_advance`, `_peek_next`). Manual paths are untouched.
- `backend/tests/test_broadcast.py` — pure/engine tests for the helpers and the `advance()` hook.
- `backend/tests/test_live_control.py` — integration tests: `_init` shuffles, manual play does not, and `_peek_next` matches the committed run.
- `docs/changelog.md` — entry per AGENTS.md.

---

### Task 1: Shuffle helpers

**Files:**
- Modify: `backend/app/broadcast.py` (imports near line 1-20; new functions before `BroadcastState` at line 28)
- Test: `backend/tests/test_broadcast.py` (imports at line 3; append tests at end)

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_broadcast.py`, change the import line 3 from:

```python
from app.broadcast import BroadcastState, advance
```

to:

```python
from app.broadcast import (
    BroadcastState,
    _auto_randomize,
    _run_seed,
    _shuffle_pairs,
    advance,
)
```

Then append these tests at the end of the file:

```python
def test_shuffle_pairs_is_a_permutation_and_keeps_pairing():
    ids = [10, 11, 12, 13]
    durations = [1, 2, 3, 4]
    out_ids, out_durations = _shuffle_pairs(ids, durations, "seed-a")
    assert sorted(out_ids) == ids
    assert dict(zip(out_ids, out_durations)) == dict(zip(ids, durations))


def test_shuffle_pairs_is_deterministic_per_seed():
    ids = [10, 11, 12, 13]
    durations = [1, 2, 3, 4]
    first = _shuffle_pairs(ids, durations, "seed-a")
    again = _shuffle_pairs(ids, durations, "seed-a")
    assert first == again


def test_run_seed_changes_with_genre_and_time():
    assert _run_seed(1, START) == "1:2026-01-01T00:00:00"
    assert _run_seed(1, START) != _run_seed(2, START)
    assert _run_seed(1, START) != _run_seed(1, START + timedelta(seconds=1))


def test_auto_randomize_is_stable_for_the_same_run():
    ids = [20, 21, 22, 23, 24, 25]
    durations = [100] * 6
    first = _auto_randomize(2, START, ids, durations)
    again = _auto_randomize(2, START, ids, durations)
    assert first == again


def test_auto_randomize_is_a_noop_for_small_lists():
    assert _auto_randomize(2, START, [10], [100]) == ([10], [100])
    assert _auto_randomize(2, START, [], []) == ([], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_broadcast.py -q`
Expected: FAIL — `ImportError: cannot import name '_auto_randomize' from 'app.broadcast'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/broadcast.py`, add `import random` to the stdlib imports (after `import json`):

```python
import json
import random
```

Then, immediately before `@dataclass` preceding `class BroadcastState:` (currently line 28), insert:

```python
def _run_seed(genre_id: int | None, started_at: datetime) -> str:
    """Stable seed for one automatic genre run.

    Keyed on the genre and the run's start time so that ``_peek_next``, which
    advances a *copy* of the state to the boundary, reproduces the same order
    the committed run will play.
    """
    return f"{genre_id}:{started_at.isoformat()}"


def _rng_factory(seed: str) -> random.Random:
    """Indirection over the RNG so tests can inject a deterministic one."""
    return random.Random(seed)


def _shuffle_pairs(
    ids: list[int], durations: list[int], seed: str
) -> tuple[list[int], list[int]]:
    """Fisher-Yates shuffle of ``(id, duration)`` pairs, kept in lockstep."""
    pairs = list(zip(ids, durations))
    _rng_factory(seed).shuffle(pairs)
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _auto_randomize(
    genre_id: int | None,
    started_at: datetime,
    ids: list[int],
    durations: list[int],
) -> tuple[list[int], list[int]]:
    """Shuffle one automatic genre run's queue (no-op for < 2 tracks)."""
    if len(ids) < 2:
        return ids, durations
    return _shuffle_pairs(ids, durations, _run_seed(genre_id, started_at))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_broadcast.py -q`
Expected: PASS (all tests in the file, including the five new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_broadcast.py
git commit -m "feat: deterministic per-run shuffle helpers (issue #14)"
```

---

### Task 2: Optional `randomize` hook on `advance()`

**Files:**
- Modify: `backend/app/broadcast.py:38-102` (`advance`)
- Test: `backend/tests/test_broadcast.py` (append tests at end)

- [ ] **Step 1: Write the failing tests**

Append these tests at the end of `backend/tests/test_broadcast.py`:

```python
def test_advance_randomizes_on_genre_switch():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=50), 2)])
    table = {1: ([10], [100]), 2: ([20, 21, 22], [100, 100, 100])}

    def randomize(genre_id, started_at, ids, durations):
        assert genre_id == 2
        return list(reversed(ids)), list(reversed(durations))

    result = advance(
        state,
        START + timedelta(seconds=120),
        desired,
        lambda sid: table[sid],
        randomize=randomize,
    )
    assert result.genre_id == 2
    assert result.track_ids == [22, 21, 20]
    assert result.index == 0


def test_advance_randomize_receives_the_boundary_start_time():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=50), 2)])
    table = {1: ([10], [100]), 2: ([20, 21], [100, 100])}
    seen = []

    def randomize(genre_id, started_at, ids, durations):
        seen.append((genre_id, started_at))
        return ids, durations

    advance(
        state,
        START + timedelta(seconds=120),
        desired,
        lambda sid: table[sid],
        randomize=randomize,
    )
    assert seen == [(2, START + timedelta(seconds=100))]


def test_advance_randomizes_on_wrap():
    state = _state(1, [10, 11, 12], [100, 100, 100], 2, START + timedelta(seconds=200))
    seen = []

    def randomize(genre_id, started_at, ids, durations):
        seen.append((genre_id, started_at))
        return list(reversed(ids)), list(reversed(durations))

    result = advance(
        state,
        START + timedelta(seconds=300),
        lambda at: 1,
        lambda sid: ([10, 11, 12], [100, 100, 100]),
        randomize=randomize,
    )
    assert result.index == 0
    assert result.track_ids == [12, 11, 10]
    assert seen == [(1, START + timedelta(seconds=300))]


def test_manual_advance_never_randomizes():
    state = BroadcastState(
        genre_id=1,
        track_ids=[10, 11],
        durations=[100, 100],
        index=0,
        started_at=START,
        manual=True,
    )
    calls = []

    def randomize(*args):
        calls.append(args)
        return args[2], args[3]

    advance(
        state,
        START + timedelta(seconds=250),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        randomize=randomize,
    )
    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_broadcast.py -q`
Expected: FAIL — `TypeError: advance() got an unexpected keyword argument 'randomize'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/broadcast.py`, change the `advance()` signature (currently lines 38-44) from:

```python
def advance(
    state: BroadcastState,
    now: datetime,
    desired: Callable[[datetime], int | None],
    snapshot: Callable[[int], tuple[list[int], list[int]]],
    gap_seconds: float = 0.0,
) -> BroadcastState:
```

to:

```python
def advance(
    state: BroadcastState,
    now: datetime,
    desired: Callable[[datetime], int | None],
    snapshot: Callable[[int], tuple[list[int], list[int]]],
    gap_seconds: float = 0.0,
    randomize: (
        Callable[
            [int | None, datetime, list[int], list[int]],
            tuple[list[int], list[int]],
        ]
        | None
    ) = None,
) -> BroadcastState:
```

Add one sentence to the docstring, after the `snapshot(genre_id)` line:

```python
    ``randomize(genre_id, started_at, ids, durations)``, when given, reshuffles
    the queue each time it is (re)built, including genre switches and wraps.
```

Then insert the `build` helper right after the input-copy block (after the `elif not 0 <= state.index ...` lines, before `if state.manual:`):

```python
    def build(genre_id: int, started_at: datetime) -> tuple[list[int], list[int]]:
        ids, durations = snapshot(genre_id)
        if randomize is not None:
            ids, durations = randomize(genre_id, started_at, ids, durations)
        return ids, durations
```

Then replace the three rebuild calls:

- Line 72 `ids, durations = snapshot(target)` becomes `ids, durations = build(target, now)`
- Line 93 `state.track_ids, state.durations = snapshot(target)` becomes `state.track_ids, state.durations = build(target, end)`
- Line 101 `state.track_ids, state.durations = snapshot(state.genre_id)` becomes `state.track_ids, state.durations = build(state.genre_id, end)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_broadcast.py -q`
Expected: PASS — the four new tests pass and every pre-existing test in the file is unchanged (they call `advance()` without `randomize`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_broadcast.py
git commit -m "feat: optional randomize hook on advance (issue #14)"
```

---

### Task 3: Wire shuffling into `_init` and production call sites

**Files:**
- Modify: `backend/app/broadcast.py:223-228` (`_init`), `:241-247` (`_peek_next`), `:263-269` (`get_current`), `:315-321` (`_load_and_advance`)
- Test: `backend/tests/test_live_control.py` (imports at line 6; append tests at end)

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_live_control.py`, change the import line 6 from:

```python
from app.broadcast import get_current, play_now, set_auto, set_order, skip, stop
```

to:

```python
from app.broadcast import (
    _load,
    _peek_next,
    get_current,
    play_now,
    set_auto,
    set_order,
    skip,
    stop,
)
```

Then append these tests at the end of the file:

```python
class _ReverseRNG:
    """Deterministic stand-in for random.Random used to pin thread order."""

    def shuffle(self, seq):
        seq.reverse()


def test_set_auto_randomizes_the_genre_run(tmp_path, monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _ReverseRNG())
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed(s, "chill", ["a", "b", "c"], default=True)
        set_auto(s, now=NOW)
        # seed order a,b,c reversed to c,b,a -> first track is c.
        assert get_current(s, NOW).track.youtube_video_id == "c"


def test_play_now_and_skip_are_not_randomized(tmp_path, monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _ReverseRNG())
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "a", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "a"
        skip(s, st.id, "next", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "b"


def test_peek_matches_the_committed_wrap_reshuffle(tmp_path, monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _ReverseRNG())
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed(s, "chill", ["a", "b", "c"], default=True)
        set_auto(s, now=NOW)
        # Order after the initial shuffle is c,b,a. At t=200 the last track (a)
        # is live; its boundary (t=300) wraps and reshuffles to c,b,a again.
        at_last = get_current(s, NOW + timedelta(seconds=200))
        assert at_last.track.youtube_video_id == "a"
        state = _load(s)
        predicted, _ = _peek_next(s, state, NOW + timedelta(seconds=200), 0.0)
        committed = get_current(s, NOW + timedelta(seconds=300))
        assert predicted.youtube_video_id == committed.track.youtube_video_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_live_control.py -q`
Expected: FAIL — before the wiring, `set_auto` keeps the saved order, so
`test_set_auto_randomizes_the_genre_run` gets `"a"` (not `"c"`), and
`test_peek_matches_the_committed_wrap_reshuffle` fails at
`at_last.track.youtube_video_id == "a"` because the unshuffled order `a,b,c` is
at `"c"` at t=200.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/broadcast.py`, update `_init` (currently lines 223-228) from:

```python
def _init(session: Session, now: datetime) -> BroadcastState:
    genre_id = _desired(session, now)
    if genre_id is None:
        return BroadcastState(None, [], [], 0, now)
    ids, durations = _snapshot(session, genre_id)
    return BroadcastState(genre_id, ids, durations, 0, now)
```

to:

```python
def _init(session: Session, now: datetime) -> BroadcastState:
    genre_id = _desired(session, now)
    if genre_id is None:
        return BroadcastState(None, [], [], 0, now)
    ids, durations = _snapshot(session, genre_id)
    ids, durations = _auto_randomize(genre_id, now, ids, durations)
    return BroadcastState(genre_id, ids, durations, 0, now)
```

In `_peek_next`, add `randomize=_auto_randomize` to the `advance(...)` call (currently the call ends with `gap,` at line 246):

```python
    following = advance(
        state,
        end,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
        gap,
        randomize=_auto_randomize,
    )
```

In `get_current`, add `randomize=_auto_randomize` to the `advance(...)` call (currently ends with `gap,` at line 268):

```python
        state = advance(
            state,
            now,
            lambda at: _desired(session, at),
            lambda sid: _snapshot(session, sid),
            gap,
            randomize=_auto_randomize,
        )
```

In `_load_and_advance`, add `randomize=_auto_randomize` to the `advance(...)` call (currently the call ends with `get_settings().track_gap_seconds,` at line 320):

```python
    return advance(
        state,
        now,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
        get_settings().track_gap_seconds,
        randomize=_auto_randomize,
    )
```

Leave `_build_manual`, `play_now`, `skip`, and `set_order` unchanged — they call `_snapshot` directly and must not shuffle.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_live_control.py tests/test_broadcast.py -q`
Expected: PASS (all tests in both files).

- [ ] **Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/tests/test_live_control.py
git commit -m "feat: randomize genre queue on automatic run start (issue #14)"
```

---

### Task 4: Full backend verification + changelog

**Files:**
- Modify: `docs/changelog.md` (insert after the `# Changelog` header block, before the first `## 2026-10-15` entry)

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS — the full suite green, including the previously existing broadcast/live-control tests.

- [ ] **Step 2: Add the changelog entry**

In `docs/changelog.md`, insert immediately after the intro paragraph (before the first `## 2026-10-15` entry):

```markdown
## 2026-10-16 — randomize the genre queue on automatic run start (issue #14)

The broadcast replayed each genre's tracks in the same saved order every time
the scheduler switched to it. Now, whenever an **automatic** genre run starts —
initial start, Auto/resume, a scheduler genre-to-genre switch, or a loop wrap —
the queue is shuffled for that run only. The shuffle is seeded from
`(genre_id, run start time)`, so the listener's "up next" preload matches what
actually plays. Nothing is persisted: the saved `genre_order:<id>` and the
admin's manual arrangement are untouched, and manual transport (Play a track,
Next/Prev, Shuffle/drag-reorder) stays deterministic.

- Files touched:
  - `backend/app/broadcast.py`
  - `backend/tests/test_broadcast.py`
  - `backend/tests/test_live_control.py`
  - `docs/changelog.md` (docs)
- **Container restart required?** Yes — `backend` only:
  `docker compose up -d --build backend`
- Verification: `cd backend && python -m pytest -q` — all tests pass.
```

- [ ] **Step 3: Confirm no other files changed**

Run: `git status --short`
Expected: only `docs/changelog.md` listed (Tasks 1-3 already committed).

- [ ] **Step 4: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: changelog for genre-run randomization (issue #14)"
```

---

## Self-Review

- **Spec coverage:** Automatic triggers (initial `_init`, genre switch, empty→desired fill, loop wrap) → Task 2 (`advance` hook) and Task 3 (`_init` + production call sites). Ephemeral (no `save_order` calls added) → confirmed, `set_order`/`_build_manual` untouched. Determinism for `_peek_next` → `_run_seed` (Task 1) + `test_advance_randomize_receives_the_boundary_start_time` and `test_peek_matches_the_committed_wrap_reshuffle`. Edge cases (empty/single no-op, duration pairing) → `test_auto_randomize_is_a_noop_for_small_lists`, `test_shuffle_pairs_is_a_permutation_and_keeps_pairing`. Manual unaffected → `test_manual_advance_never_randomizes`, `test_play_now_and_skip_are_not_randomized`. Changelog per AGENTS.md → Task 4. No gaps.
- **Placeholder scan:** No TBD/TODO; every step shows exact code and commands.
- **Type consistency:** `randomize` is `Callable[[int | None, datetime, list[int], list[int]], tuple[list[int], list[int]]] | None` in `advance()` and matches `_auto_randomize`'s signature and the test stubs (4 args → 2-tuple). `_rng_factory(seed)` returns an object with `.shuffle(seq)`, satisfied by `random.Random` and `_ReverseRNG`. Helper names (`_run_seed`, `_shuffle_pairs`, `_auto_randomize`) are identical across tasks.
