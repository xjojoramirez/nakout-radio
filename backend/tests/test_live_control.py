from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, delete

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
from app.models import Playlist, Genre, TrackCache


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session, slug, vids, *, default=False):
    st = Genre(name=slug.title(), slug=slug, is_default=default)
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
        with pytest.raises(ValueError):
            play_now(s, st.id, "nope", now=NOW)


def test_skip_next_and_prev_move_within_genre(tmp_path):
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


def test_skip_switches_to_requested_genre(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        one = _seed(s, "one", ["a"], default=True)
        two = _seed(s, "two", ["x", "y"])
        set_auto(s, now=NOW)
        assert get_current(s, NOW).genre.id == one.id
        skip(s, two.id, "next", now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.genre.id == two.id
        assert now_state.track.youtube_video_id == "x"


def test_skip_from_auto_moves_to_adjacent_track(tmp_path, monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _KeepOrderRNG())
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"], default=True)
        set_auto(s, now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "a"
        skip(s, st.id, "next", now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.track.youtube_video_id == "b"
        assert now_state.source == "manual"
        skip(s, st.id, "prev", now=NOW)
        assert get_current(s, NOW).track.youtube_video_id == "a"


def test_set_auto_returns_to_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _KeepOrderRNG())
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


def test_set_order_after_time_advances_preserves_current(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "a", now=NOW)
        later = NOW + timedelta(seconds=150)
        set_order(s, st.id, ["c", "b", "a"], now=later)
        now_state = get_current(s, later)
        assert now_state.track.youtube_video_id == "b"
        # Track a ends at 100s, the 2s gap runs to 102s, so b is at 48s.
        assert now_state.offset_seconds == 48


def test_set_order_when_current_track_removed_resets_offset(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "b", now=NOW)
        later = NOW + timedelta(seconds=50)
        s.exec(delete(TrackCache).where(TrackCache.youtube_video_id == "b"))
        s.commit()
        set_order(s, st.id, ["c", "a"], now=later)
        now_state = get_current(s, later)
        assert now_state.track.youtube_video_id in {"a", "c"}
        assert now_state.offset_seconds == 0


def test_stop_goes_off_air_and_stays(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed(s, "chill", ["a", "b"], default=True)
        set_auto(s, now=NOW)
        assert get_current(s, NOW).source == "default"
        stop(s, now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.source == "none"
        assert now_state.track is None
        # Time passing must not silently resume the schedule.
        later = NOW + timedelta(seconds=500)
        assert get_current(s, later).source == "none"


def test_stop_then_auto_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr("app.broadcast._rng_factory", lambda seed: _KeepOrderRNG())
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed(s, "chill", ["a", "b"], default=True)
        set_auto(s, now=NOW)
        stop(s, now=NOW)
        assert get_current(s, NOW).source == "none"
        set_auto(s, now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.source == "default"
        assert now_state.track.youtube_video_id == "a"


def test_stop_then_play_resumes(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b"], default=True)
        stop(s, now=NOW)
        play_now(s, st.id, "b", now=NOW)
        now_state = get_current(s, NOW)
        assert now_state.source == "manual"
        assert now_state.track.youtube_video_id == "b"


class _KeepOrderRNG:
    """No-op RNG so tests unrelated to shuffling keep the saved order."""

    def shuffle(self, seq):
        return None


class _ReverseRNG:
    """Deterministic stand-in for random.Random used to pin thread order."""

    def shuffle(self, seq):
        seq.reverse()


class _SeedSensitiveRNG:
    """Stub whose order depends on the seed it was constructed with."""

    def __init__(self, seed):
        self.seed = seed

    def shuffle(self, seq):
        if not seq:
            return None
        k = sum(ord(c) for c in self.seed) % len(seq)
        seq[:] = seq[k:] + seq[:k]
        return None


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
    # The fixed timestamps below assume no inter-track gap; pin it to 0 so the
    # last track's boundary lands exactly at t=300 (default gap is 2s, which
    # would put the live track at t=200 at "b" and shift the boundary).
    from app.config import get_settings as _get_settings

    monkeypatch.setattr(
        "app.broadcast.get_settings",
        lambda: _get_settings().model_copy(update={"track_gap_seconds": 0.0}),
    )
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


def test_peek_and_commit_use_the_same_seed_on_wrap(tmp_path, monkeypatch):
    from app.config import get_settings as _get_settings

    seeds = []

    def factory(seed):
        seeds.append(seed)
        return _SeedSensitiveRNG(seed)

    monkeypatch.setattr("app.broadcast._rng_factory", factory)
    monkeypatch.setattr(
        "app.broadcast.get_settings",
        lambda: _get_settings().model_copy(update={"track_gap_seconds": 0.0}),
    )
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed(s, "chill", ["a", "b", "c"], default=True)
        set_auto(s, now=NOW)
        get_current(s, NOW + timedelta(seconds=200))
        state = _load(s)
        seeds.clear()
        predicted, _ = _peek_next(s, state, NOW + timedelta(seconds=200), 0.0)
        peek_seeds = list(seeds)
        seeds.clear()
        committed = get_current(s, NOW + timedelta(seconds=300))
        commit_seeds = list(seeds)
        assert peek_seeds == commit_seeds
        assert predicted.youtube_video_id == committed.track.youtube_video_id


def test_peek_and_commit_use_the_same_seed_on_genre_switch(tmp_path, monkeypatch):
    seeds = []

    def factory(seed):
        seeds.append(seed)
        return _SeedSensitiveRNG(seed)

    monkeypatch.setattr("app.broadcast._rng_factory", factory)
    engine = _engine(tmp_path)
    with Session(engine) as s:
        one = _seed(s, "one", ["a1"], default=True)
        two = _seed(s, "two", ["b1", "b2", "b3", "b4"])
        switch_at = NOW + timedelta(seconds=100)
        monkeypatch.setattr(
            "app.broadcast._desired",
            lambda session, at: two.id if at >= switch_at else one.id,
        )
        set_auto(s, now=NOW)
        get_current(s, NOW)
        state = _load(s)
        seeds.clear()
        # Default gap is 2s, so the single 100s track's boundary is at t=102.
        predicted, _ = _peek_next(s, state, NOW, 2.0)
        peek_seeds = list(seeds)
        seeds.clear()
        committed = get_current(s, NOW + timedelta(seconds=102))
        commit_seeds = list(seeds)
        assert peek_seeds == commit_seeds
        assert predicted.youtube_video_id == committed.track.youtube_video_id
