from datetime import datetime, timedelta

import pytest

from app.broadcast import (
    BroadcastState,
    _auto_randomize,
    _avoid_immediate_repeat,
    _run_seed,
    _shuffle_pairs,
    advance,
)


def _state(genre_id, track_ids, durations, index, started_at):
    return BroadcastState(
        genre_id=genre_id,
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


class _ReverseRNG:
    """Deterministic stand-in for random.Random used to pin thread order."""

    def shuffle(self, seq):
        seq.reverse()


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


def test_genre_switch_waits_for_song_end():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=50), 2)])
    table = {1: ([10], [100]), 2: ([20, 21], [100, 100])}
    result = advance(
        state, START + timedelta(seconds=120), desired, lambda sid: table[sid]
    )
    assert result.genre_id == 2
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=100)


def test_empty_genre_stays_off_air():
    state = _state(1, [], [], 0, START)
    result = advance(
        state, START + timedelta(seconds=10), lambda at: 1, lambda sid: ([], [])
    )
    assert result.track_ids == []


def test_off_air_recovers_when_tracks_appear():
    state = _state(1, [], [], 0, START)
    now = START + timedelta(hours=3)
    result = advance(state, now, lambda at: 1, lambda sid: ([10, 11], [100, 100]))
    assert result.track_ids == [10, 11]
    assert result.index == 0
    assert result.started_at == now


def test_zero_duration_treated_as_one_second():
    state = _state(1, [10, 11], [0, 100], 0, START)
    result = advance(
        state,
        START + timedelta(seconds=1),
        lambda at: 1,
        lambda sid: ([10, 11], [0, 100]),
    )
    assert result.index == 1
    assert result.started_at == START + timedelta(seconds=1)


def test_does_not_mutate_input():
    state = _state(1, [10, 11], [100, 100], 0, START)
    result = advance(
        state,
        START + timedelta(seconds=150),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
    )
    assert state.track_ids == [10, 11]
    assert state.index == 0
    assert state.started_at == START
    assert result.index == 1


def test_manual_advance_ignores_schedule_and_wraps():
    state = BroadcastState(
        genre_id=1,
        track_ids=[10, 11],
        durations=[100, 100],
        index=0,
        started_at=START,
        manual=True,
    )
    calls = []

    def desired(at):
        calls.append("desired")
        return _desired_at([(START, 2)])(at)

    def snapshot(sid):
        calls.append("snapshot")
        return ([99], [100])

    result = advance(
        state,
        START + timedelta(seconds=150),
        desired,
        snapshot,
    )
    assert result.genre_id == 1
    assert result.track_ids == [10, 11]
    assert result.index == 1
    assert result.started_at == START + timedelta(seconds=100)
    assert calls == []


def test_manual_advance_wraps_to_first_track():
    state = BroadcastState(
        genre_id=1,
        track_ids=[10, 11],
        durations=[100, 100],
        index=1,
        started_at=START,
        manual=True,
    )
    calls = []

    def desired(at):
        calls.append("desired")
        return 1

    def snapshot(sid):
        calls.append("snapshot")
        return ([10, 11], [100, 100])

    result = advance(state, START + timedelta(seconds=100), desired, snapshot)
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=100)
    assert calls == []


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


def test_shuffle_pairs_is_a_permutation_and_keeps_pairing():
    ids = [10, 11, 12, 13]
    durations = [1, 2, 3, 4]
    out_ids, out_durations = _shuffle_pairs(ids, durations, "seed-a")
    # Pins determinism (not just "is a permutation"); tied to CPython's
    # random.Random shuffle, which is stable for the Python version we pin.
    assert out_ids == [11, 13, 10, 12]
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


def test_shuffle_pairs_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        _shuffle_pairs([1, 2, 3], [10, 20], "seed-a")


def test_auto_randomize_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        _auto_randomize(2, START, [1], [10, 20])


def test_avoid_immediate_repeat_swaps_a_replayed_head():
    ids, durations = _avoid_immediate_repeat([10, 11, 12], [1, 2, 3], 10)
    assert ids == [11, 10, 12]
    assert durations == [2, 1, 3]

    ids, durations = _avoid_immediate_repeat([10, 11], [1, 2], 10)
    assert ids == [11, 10]
    assert durations == [2, 1]


def test_avoid_immediate_repeat_leaves_other_queues_alone():
    assert _avoid_immediate_repeat([11, 10, 12], [1, 2, 3], 10) == (
        [11, 10, 12],
        [1, 2, 3],
    )
    assert _avoid_immediate_repeat([10, 11, 12], [1, 2, 3], None) == (
        [10, 11, 12],
        [1, 2, 3],
    )
    # A single-track genre cannot avoid replaying its only track.
    assert _avoid_immediate_repeat([10], [1], 10) == ([10], [1])


def test_auto_randomize_avoids_replaying_the_previous_track(monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _ReverseRNG())
    ids, durations = _auto_randomize(
        1, START, [10, 11, 12], [1, 2, 3], previous_id=12
    )
    # The reverse shuffle alone would open the new pass with 12 again.
    assert ids == [11, 12, 10]
    assert durations == [2, 3, 1]


def test_auto_randomize_keeps_the_shuffle_when_no_repeat_would_happen(monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _ReverseRNG())
    assert _auto_randomize(1, START, [10, 11, 12], [1, 2, 3], previous_id=10) == (
        [12, 11, 10],
        [3, 2, 1],
    )


def test_advance_randomizes_on_genre_switch():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=50), 2)])
    table = {1: ([10], [100]), 2: ([20, 21, 22], [100, 100, 100])}

    def randomize(genre_id, started_at, ids, durations, previous_id):
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

    def randomize(genre_id, started_at, ids, durations, previous_id):
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

    def randomize(genre_id, started_at, ids, durations, previous_id):
        seen.append((genre_id, started_at, previous_id))
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
    assert seen == [(1, START + timedelta(seconds=300), 12)]


def test_advance_randomize_receives_the_finished_track_on_switch():
    state = _state(1, [10], [100], 0, START)
    desired = _desired_at([(START, 1), (START + timedelta(seconds=50), 2)])
    table = {1: ([10], [100]), 2: ([20, 21], [100, 100])}
    seen = []

    def randomize(genre_id, started_at, ids, durations, previous_id):
        seen.append(previous_id)
        return ids, durations

    advance(
        state,
        START + timedelta(seconds=120),
        desired,
        lambda sid: table[sid],
        randomize=randomize,
    )
    assert seen == [10]


def test_advance_randomize_receives_no_previous_on_first_fill():
    state = _state(1, [], [], 0, START)
    seen = []

    def randomize(genre_id, started_at, ids, durations, previous_id):
        seen.append(previous_id)
        return ids, durations

    result = advance(
        state,
        START + timedelta(hours=3),
        lambda at: 1,
        lambda sid: ([10, 11], [100, 100]),
        randomize=randomize,
    )
    assert seen == [None]
    assert result.track_ids == [10, 11]


def test_advance_wrap_does_not_replay_the_finished_track(monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _ReverseRNG())
    state = _state(1, [10, 11], [50, 100], 1, START + timedelta(seconds=50))
    result = advance(
        state,
        START + timedelta(seconds=150),
        lambda at: 1,
        lambda sid: ([10, 11], [50, 100]),
        randomize=_auto_randomize,
    )
    # Track 11 (the last of the pass) finishes; the reverse shuffle alone
    # would open the next pass with it again.
    assert result.track_ids[0] != 11
    assert result.track_ids == [10, 11]
    assert result.durations == [50, 100]
    assert result.index == 0
    assert result.started_at == START + timedelta(seconds=150)


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
