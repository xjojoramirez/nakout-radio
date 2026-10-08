from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, delete

from app.broadcast import get_current, play_now, set_auto, set_order, skip, stop
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


def test_skip_from_auto_moves_to_adjacent_track(tmp_path):
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


def test_set_order_after_time_advances_preserves_current(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed(s, "chill", ["a", "b", "c"])
        play_now(s, st.id, "a", now=NOW)
        later = NOW + timedelta(seconds=150)
        set_order(s, st.id, ["c", "b", "a"], now=later)
        now_state = get_current(s, later)
        assert now_state.track.youtube_video_id == "b"
        assert now_state.offset_seconds == 50


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


def test_stop_then_auto_resumes(tmp_path):
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
