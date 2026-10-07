from datetime import datetime, timedelta

from app.broadcast import BroadcastState, advance


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
