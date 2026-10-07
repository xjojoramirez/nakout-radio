import json
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine, delete, select

from app.broadcast import _load, get_current
from app.db import get_session
from app.main import create_app
from app.models import Playlist, ScheduleSlot, Setting, Genre, TrackCache


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


def _seed_genre(session, slug, *, default=False, video="vid", duration=200):
    st = Genre(name=slug.title(), slug=slug, is_default=default)
    session.add(st)
    session.commit()
    session.refresh(st)
    pl = Playlist(genre_id=st.id, youtube_playlist_id=f"PL-{slug}")
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
        _seed_genre(s, "morning", default=True)
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "default"
    assert body["genre"]["slug"] == "morning"
    assert body["track"]["youtube_video_id"] == "vid"
    assert 0 <= body["offset_seconds"] < 200
    assert body["server_time"]


def test_now_off_air(tmp_path):
    engine = _engine(tmp_path)
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "none"
    assert body["genre"] is None
    assert body["track"] is None
    assert body["offset_seconds"] == 0


def test_now_uses_matching_slot(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        night = _seed_genre(s, "night", video="nv")
        s.add(
            ScheduleSlot(
                genre_id=night.id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                start_time="00:00",
            )
        )
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "schedule"
    assert body["genre"]["slug"] == "night"


def test_now_falls_back_to_default_when_slot_genre_empty(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True, video="mv")
        empty = Genre(name="Empty", slug="empty")
        s.add(empty)
        s.commit()
        s.refresh(empty)
        s.add(
            ScheduleSlot(
                genre_id=empty.id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                start_time="00:00",
            )
        )
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["genre"]["slug"] == "morning"
    assert body["source"] == "default"


def test_now_switches_between_scheduled_genres(tmp_path):
    engine = _engine(tmp_path)
    every_day = [0, 1, 2, 3, 4, 5, 6]
    with Session(engine) as s:
        alpha = _seed_genre(s, "alpha", video="av")
        beta = _seed_genre(s, "beta", video="bv")
        s.add(
            ScheduleSlot(
                genre_id=alpha.id, days_of_week=every_day, start_time="06:00"
            )
        )
        s.add(
            ScheduleSlot(genre_id=beta.id, days_of_week=every_day, start_time="12:00")
        )
        s.commit()
    with Session(engine) as s:
        morning = get_current(s, datetime(2026, 1, 4, 22, 30))  # Mon 06:30 Manila
        assert morning.genre.slug == "alpha"
        afternoon = get_current(s, datetime(2026, 1, 5, 5, 0))  # Mon 13:00 Manila
        assert afternoon.genre.slug == "beta"


def test_get_current_advances_and_persists(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True, duration=200)
    with Session(engine) as s:
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        first = get_current(s, t0)
        assert first.offset_seconds == 0
        second = get_current(s, t0 + timedelta(seconds=30))
        assert second.offset_seconds == 30
        assert s.get(Setting, "broadcast_state") is not None


def test_corrupt_state_is_discarded(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True)
        s.merge(Setting(key="broadcast_state", value="{not json"))
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "default"
    assert body["genre"]["slug"] == "morning"


def test_load_discards_valid_json_non_object(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        s.merge(Setting(key="broadcast_state", value="[]"))
        s.commit()
        assert _load(s) is None


def test_load_normalizes_aware_timestamp(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        s.merge(
            Setting(
                key="broadcast_state",
                value=json.dumps(
                    {
                        "genre_id": 1,
                        "track_ids": [1],
                        "durations": [200],
                        "index": 0,
                        "started_at_utc": "2026-01-01T00:00:00+00:00",
                    }
                ),
            )
        )
        s.commit()
        state = _load(s)
        assert state is not None
        assert state.started_at.tzinfo is None


def test_load_discards_non_int_genre_id(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        s.merge(
            Setting(
                key="broadcast_state",
                value=json.dumps(
                    {
                        "genre_id": "abc",
                        "track_ids": [1],
                        "durations": [200],
                        "index": 0,
                        "started_at_utc": "2026-01-01T00:00:00",
                    }
                ),
            )
        )
        s.commit()
        assert _load(s) is None


def test_now_recovers_when_snapshot_track_is_gone(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        st = _seed_genre(s, "morning", default=True, video="old")
        pl = s.exec(select(Playlist).where(Playlist.genre_id == st.id)).one()
        s.add(
            TrackCache(
                playlist_id=pl.id,
                youtube_video_id="keep",
                title="T",
                artist="A",
                position=1,
                duration_seconds=200,
            )
        )
        s.commit()
        old_id = s.exec(
            select(TrackCache).where(TrackCache.youtube_video_id == "old")
        ).one().id

    client = _client(engine)
    first = client.get("/api/now").json()
    assert first["track"]["youtube_video_id"] == "old"

    with Session(engine) as s:
        s.exec(delete(TrackCache).where(TrackCache.id == old_id))
        s.commit()

    second = client.get("/api/now").json()
    assert second["track"]["youtube_video_id"] == "keep"


def test_build_now_matches_endpoint_shape(tmp_path):
    from datetime import datetime

    from app.routers.now import build_now

    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True, video="bv", duration=200)
        body = build_now(s, datetime(2026, 1, 1, 0, 0, 0))
    assert body.source == "default"
    assert body.genre is not None and body.genre.slug == "morning"
    assert body.track is not None and body.track.youtube_video_id == "bv"
    assert body.offset_seconds == 0
    assert body.server_time
