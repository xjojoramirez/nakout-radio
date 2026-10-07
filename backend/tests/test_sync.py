import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Playlist, Genre, TrackCache
from app.sync import sync_playlist
from app.youtube import TrackData


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_sync_replaces_tracks():
    engine = _engine()
    with Session(engine) as s:
        st = Genre(name="A", slug="a")
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(genre_id=st.id, youtube_playlist_id="PL1")
        s.add(pl)
        s.commit()
        s.refresh(pl)

    fetch = lambda pl_id: [
        TrackData("v1", "One", "Art", "u1", 0),
        TrackData("v2", "Two", "Art", "u2", 1),
    ]

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, fetch)
        rows = s.exec(select(TrackCache).order_by(TrackCache.position)).all()
        assert [r.youtube_video_id for r in rows] == ["v1", "v2"]
        sync_playlist(s, pl, lambda _id: [TrackData("v3", "Three", "Art", "u3", 0)])
        rows = s.exec(select(TrackCache)).all()
        assert [r.youtube_video_id for r in rows] == ["v3"]


def test_sync_fetch_error_preserves_cache():
    engine = _engine()
    with Session(engine) as s:
        st = Genre(name="A", slug="a")
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(genre_id=st.id, youtube_playlist_id="PL1")
        s.add(pl)
        s.commit()
        s.refresh(pl)

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        assert sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u", 0)]) == 1

        def boom(_id):
            raise RuntimeError("network down")

        with pytest.raises(RuntimeError):
            sync_playlist(s, pl, boom)
        rows = s.exec(select(TrackCache)).all()
        assert [r.youtube_video_id for r in rows] == ["v1"]


def test_sync_stores_duration():
    engine = _engine()
    with Session(engine) as s:
        st = Genre(name="A", slug="a")
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(genre_id=st.id, youtube_playlist_id="PL1")
        s.add(pl)
        s.commit()
        s.refresh(pl)

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u1", 0, 245)])
        row = s.exec(select(TrackCache)).one()
        assert row.duration_seconds == 245
