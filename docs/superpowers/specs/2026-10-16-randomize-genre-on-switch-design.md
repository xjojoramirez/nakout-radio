# Randomize Genre Queue on Run Start — Design Specification

Date: 2026-10-16
Issue: #14 — Randomize tracks in playlist when starting
Approach: A — Deterministic per-run shuffle hook on the broadcast engine (approved)

## Goal

When the station starts a genre run on its own, the order of that genre's tracks
should be randomized, so the broadcast does not replay the same sequence every
time a genre comes around. Randomization is **automatic** (no operator action)
and **ephemeral** (it affects the live queue only; the saved genre order is not
modified).

## Context: what "playlist" means here

There is no listener-facing "playlist switch". The playable unit is a **Genre**,
which owns one or more playlists; the live queue is the concatenation of every
track in the genre, ordered by `ordered_tracks_for_genre` (default order
`playlist_id, position, id`, overridden by the `genre_order:<genre_id>` Setting
the admin arranges by hand). "Jumping from one playlist to another" therefore
maps to the broadcast **switching the active genre at a song boundary**.

The only shuffle today is the admin's manual Shuffle button in the Now Playing
panel, which *persists* a per-genre order (`NowPlayingPanel.tsx` →
`PUT /api/studio/genres/{id}/order` → `set_order`). That behaviour is unchanged.

## Scope

In scope (backend only):

- `backend/app/broadcast.py` — randomize the queue when an **automatic** genre
  run starts:
  - initial station start (`_init`),
  - genre-to-genre switch inside `advance()` at a song boundary,
  - the empty→desired fill path inside `advance()`,
  - loop wrap inside `advance()` (each pass through a genre reshuffles).
- `backend/tests/test_broadcast.py` — new coverage; existing tests unchanged.
- `docs/changelog.md` — entry per AGENTS.md.

Out of scope (unchanged, deliberate):

- Manual operator transport: `play_now` (Play a track), `skip` (Next/Prev), and
  `set_order` (Shuffle / drag-reorder) keep their deterministic order.
- Frontend: no changes. The admin Now Playing queue view continues to show the
  saved base order, not the ephemeral live order.
- Persistence: nothing is written to `genre_order`. Re-syncs and the admin's
  manual arrangement are untouched.

## Decisions

- **Automatic only.** Shuffling happens on run starts driven by the schedule /
  auto mode, never on explicit operator actions. This keeps the operator in full
  control when they deliberately pick a track or jump.
- **Ephemeral.** The shuffled order lives in `broadcast_state` for the duration
  of the run. On the next run the base order is read again and shuffled afresh.
- **Full shuffle, not a random start.** The whole `(id, duration)` list is
  permuted, so every cycle is a new arrangement.
- **Deterministic per run.** The shuffle is seeded from
  `(genre_id, run start time)`, so `_peek_next` — which predicts the next track
  by advancing a *copy* of the state to the boundary — reproduces exactly the
  order the committed run will play. Without this, the listener's "up next"
  preload (issue #6) would disagree with what actually plays.
- **Backend-only seam.** The shuffle is applied in the broadcast engine, which is
  the single source of truth for playback order; the listener has no client-side
  queue to shuffle.

## Architecture

Two small pure helpers plus one optional parameter:

```python
def _run_seed(genre_id: int | None, started_at: datetime) -> str:
    return f"{genre_id}:{started_at.isoformat()}"


def _shuffle_pairs(
    ids: list[int], durations: list[int], seed: str
) -> tuple[list[int], list[int]]:
    pairs = list(zip(ids, durations))
    _rng_factory(seed).shuffle(pairs)          # module-level, injectable for tests
    return [p[0] for p in pairs], [p[1] for p in pairs]
```

`advance()` gains an optional hook, so existing callers and tests that omit it
keep the current behaviour:

```python
def advance(
    state, now, desired, snapshot, gap_seconds=0.0, randomize=None
):
    ...
    def build(target, started_at):
        ids, durations = snapshot(target)
        if randomize is not None:
            ids, durations = randomize(target, started_at, ids, durations)
        return ids, durations
```

The three rebuild sites in `advance()` call `build(target, started_at)` with the
run's start time (the boundary `end` for a switch/wrap, `now` for the initial
fill). `_init()` shuffles directly with `now` as the run start.

Production closures in `get_current`, `_load_and_advance`, and `_peek_next` pass
a `randomize` that wraps `_shuffle_pairs` with `_run_seed`; because `_peek_next`
computes the identical boundary time, its prediction matches the committed run.
Manual paths (`_build_manual`, `set_order`, the manual-rebuild fallback in
`get_current`) continue to call the plain `_snapshot` with no randomization.

`_rng_factory` is a module-level indirection defaulting to `random.Random`, so
tests can substitute a fixed RNG.

## Data flow

```
scheduler/desired ──▶ advance(build) ──▶ snapshot(genre) ──▶ randomize(seed)
                                                            │
                            broadcast_state.track_ids/durations  ◀── stored, index=0
                                                            │
                            _peek_next ── advance on a copy ─┘  (same seed ⇒ same order)
```

## Edge cases

- Empty genre or a single track: the shuffle is a no-op; the empty→desired path
  still returns an empty list when there is nothing to play.
- `durations` are permuted in lockstep with `ids`, so the paired values never
  desync.
- Zero/absent durations are treated exactly as before (`or 1` at play time);
  randomizing does not change the gap logic.
- Manual states never route through `randomize`, so a mid-run `set_order` still
  preserves the currently playing track.
- Two runs of the same genre at different start times get different seeds;
  a wrap and a re-entry produce different arrangements.

## Testing

New tests in `backend/tests/test_broadcast.py`:

1. `_shuffle_pairs` returns a permutation of the input and keeps each id paired
   with its duration; the same seed is stable and different seeds generally
   differ.
2. `_init` with a stubbed `_rng_factory` produces the expected permuted order.
3. `advance()` with a `randomize` hook and a genre switch returns a permuted
   queue with `index == 0`.
4. Peek consistency: the track `_peek_next` predicts at a switch boundary equals
   the track that is live once the boundary passes.
5. Manual regression: `set_order` + `play_now` / `skip` preserve the exact order
   with no shuffling.
6. The existing `test_broadcast.py` suite passes unchanged (no `randomize`
   passed ⇒ no randomization).

Verification commands: `cd backend && python -m pytest -q` (the project's
documented invocation; see `docs/follow-ups.md`) — the whole backend suite must
stay green.

## Alternatives considered

- B. Random start index only — rejected: the issue asks for the list to be
  randomized; cycles would still follow the same saved sequence from a random
  offset.
- C. Persist the shuffled order to `genre_order` at run start — rejected: the
  design is explicitly ephemeral, and persisting would clobber the admin's
  manual arrangement and never restore the YouTube order.
- D. Shuffle client-side — rejected: the scheduler is server-side and the
  listener has no queue; a client shuffle would desync the preload/peek.
