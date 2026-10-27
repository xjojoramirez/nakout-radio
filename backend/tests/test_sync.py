from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Playlist, Genre, TrackCache
from app.sync import sync_playlist
from app.youtube import TrackData


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _genre_and_playlist(engine, slug="a", yt_id="PL1") -> None:
    with Session(engine) as s:
        st = Genre(name=slug.title(), slug=slug)
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(genre_id=st.id, youtube_playlist_id=yt_id)
        s.add(pl)
        s.commit()


def test_sync_detaches_removed_tracks():
    engine = _engine()
    _genre_and_playlist(engine)
    fetch = lambda pl_id: [
        TrackData("v1", "One", "Art", "u1", 0),
        TrackData("v2", "Two", "Art", "u2", 1),
    ]

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, fetch)
        rows = s.exec(select(TrackCache).order_by(TrackCache.position)).all()
        assert [r.youtube_video_id for r in rows] == ["v1", "v2"]

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v3", "Three", "Art", "u3", 0)])

    with Session(engine) as s:
        rows = s.exec(select(TrackCache).order_by(TrackCache.id)).all()
        by_video = {r.youtube_video_id: r for r in rows}
        assert set(by_video) == {"v1", "v2", "v3"}
        assert by_video["v1"].playlist_id is None
        assert by_video["v2"].playlist_id is None
        assert by_video["v1"].position == 0
        assert by_video["v3"].playlist_id is not None


def test_sync_preserves_row_ids_for_surviving_tracks():
    engine = _engine()
    _genre_and_playlist(engine)
    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u1", 0)])
    with Session(engine) as s:
        original = s.exec(select(TrackCache)).one().id

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(
            s,
            pl,
            lambda _id: [
                TrackData("v1", "One", "Art", "u1", 0),
                TrackData("v2", "Two", "Art", "u2", 1),
            ],
        )

    with Session(engine) as s:
        rows = s.exec(select(TrackCache).order_by(TrackCache.id)).all()
        assert rows[0].id == original
        assert rows[0].youtube_video_id == "v1"


def test_sync_reattaches_a_detached_track():
    engine = _engine()
    _genre_and_playlist(engine)
    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u1", 0)])
    with Session(engine) as s:
        original = s.exec(select(TrackCache)).one().id
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [])
    with Session(engine) as s:
        detached = s.exec(select(TrackCache)).one()
        assert detached.playlist_id is None
        assert detached.id == original

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u1", 0)])

    with Session(engine) as s:
        rows = s.exec(select(TrackCache)).all()
        assert len(rows) == 1
        assert rows[0].id == original
        assert rows[0].playlist_id is not None


def test_sync_removing_one_membership_keeps_the_other():
    engine = _engine()
    _genre_and_playlist(engine, "a", "PL1")
    _genre_and_playlist(engine, "b", "PL2")
    with Session(engine) as s:
        first = s.exec(select(Playlist).where(Playlist.youtube_playlist_id == "PL1")).one()
        second = s.exec(select(Playlist).where(Playlist.youtube_playlist_id == "PL2")).one()
        sync_playlist(s, first, lambda _id: [TrackData("v1", "One", "Art", "u1", 0)])
        sync_playlist(s, second, lambda _id: [TrackData("v1", "One", "Art", "u1", 0)])

    with Session(engine) as s:
        first = s.exec(select(Playlist).where(Playlist.youtube_playlist_id == "PL1")).one()
        first_id = first.id
        sync_playlist(s, first, lambda _id: [])

    with Session(engine) as s:
        rows = s.exec(select(TrackCache)).all()
        assert len(rows) == 1
        assert rows[0].playlist_id is not None
        assert rows[0].playlist_id != first_id


def test_sync_fetch_error_preserves_cache():
    engine = _engine()
    _genre_and_playlist(engine)

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
    _genre_and_playlist(engine)

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u1", 0, 245)])
        row = s.exec(select(TrackCache)).one()
        assert row.duration_seconds == 245


def test_sync_preserves_loudness_for_unchanged_tracks():
    engine = _engine()
    _genre_and_playlist(engine)
    fetched = lambda _id: [TrackData("v1", "One", "Art", "u1", 0)]  # noqa: E731
    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, fetched)
    checked_at = datetime(2026, 10, 17, 0, 0, 0)
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        row.gain_db = -9.0
        row.gain_checked_at = checked_at
        s.add(row)
        s.commit()

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, fetched)
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        assert row.gain_db == -9.0
        assert row.gain_checked_at == checked_at


def test_sync_resets_loudness_when_title_changes():
    engine = _engine()
    _genre_and_playlist(engine)
    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, lambda _id: [TrackData("v1", "One", "Art", "u1", 0)])
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        row.gain_db = -9.0
        row.gain_checked_at = datetime(2026, 10, 17, 0, 0, 0)
        s.add(row)
        s.commit()

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(
            s, pl, lambda _id: [TrackData("v1", "One (Remaster)", "Art", "u1", 0)]
        )
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        assert row.gain_db is None
        assert row.gain_checked_at is None
