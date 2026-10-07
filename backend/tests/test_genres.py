from sqlmodel import Session, SQLModel, create_engine, delete, select

from app.db import get_session
from app.main import create_app
from app.models import Playlist, ScheduleSlot, Setting, Genre, TrackCache
from app.routers.genres import ordered_tracks_for_genre


def _seed(session: Session) -> None:
    genre = Genre(name="Morning", slug="morning", is_default=True)
    session.add(genre)
    session.commit()
    session.refresh(genre)
    pl = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
    session.add(pl)
    session.commit()
    session.refresh(pl)
    session.add(
        TrackCache(
            playlist_id=pl.id,
            youtube_video_id="vid1",
            title="Song",
            artist="Artist",
            position=0,
        )
    )
    session.commit()


def _client_with_db(tmp_path):
    from fastapi.testclient import TestClient

    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        _seed(s)

    def override():
        with Session(engine) as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_list_genres(tmp_path):
    client = _client_with_db(tmp_path)
    resp = client.get("/api/genres")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["slug"] == "morning"
    assert body[0]["track_count"] == 1


def test_genre_detail_returns_single_track_and_cursor(tmp_path):
    client = _client_with_db(tmp_path)
    resp = client.get("/api/genres/morning")
    assert resp.status_code == 200
    body = resp.json()
    assert body["track"]["youtube_video_id"] == "vid1"
    assert isinstance(body["cursor"], str) and body["cursor"]
    assert "tracks" not in body


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _client_from_engine(engine):
    from fastapi.testclient import TestClient

    def override():
        with Session(engine) as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_schedule_now_uses_matching_slot(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        night = Genre(name="Night", slug="night")
        s.add(night)
        s.commit()
        s.refresh(night)
        pl = Playlist(genre_id=night.id, youtube_playlist_id="PLN")
        s.add(pl)
        s.commit()
        s.refresh(pl)
        s.add(
            TrackCache(
                playlist_id=pl.id,
                youtube_video_id="nv",
                title="Night Song",
                artist="Artist",
                position=0,
            )
        )
        # One slot at midnight keeps Night playing all week.
        s.add(
            ScheduleSlot(
                genre_id=night.id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                start_time="00:00",
            )
        )
        s.commit()
    client = _client_from_engine(engine)
    body = client.get("/api/schedule/now").json()
    assert body["source"] == "schedule"
    assert body["genre"]["slug"] == "night"
    assert body["track"]["youtube_video_id"] == "nv"
    assert "tracks" not in body


def test_schedule_now_falls_back_to_default(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed(s)
    client = _client_from_engine(engine)
    body = client.get("/api/schedule/now").json()
    assert body["source"] == "default"
    assert body["genre"]["slug"] == "morning"
    assert body["track"]["youtube_video_id"] == "vid1"


def test_schedule_now_no_genre(tmp_path):
    engine = _engine(tmp_path)
    client = _client_from_engine(engine)
    body = client.get("/api/schedule/now").json()
    assert body["source"] == "none"
    assert body["genre"] is None
    assert body["track"] is None


def _seed_ordered(session):
    genre = Genre(name="Order", slug="order")
    session.add(genre)
    session.commit()
    session.refresh(genre)
    for pl_idx, vids in enumerate((["a", "b"], ["c", "d"])):
        pl = Playlist(genre_id=genre.id, youtube_playlist_id=f"PL{pl_idx}")
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
                )
            )
        session.commit()
    return genre


def test_default_order_used_without_saved_order(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = _seed_ordered(s)
        ids = [t.youtube_video_id for t in ordered_tracks_for_genre(s, genre.id)]
        assert ids == ["a", "b", "c", "d"]


def test_saved_order_is_applied(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = _seed_ordered(s)
        s.merge(Setting(key=f"genre_order:{genre.id}", value='["d", "b"]'))
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_genre(s, genre.id)]
        assert ids == ["d", "b", "a", "c"]


def test_new_tracks_append_and_removed_tracks_drop(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = _seed_ordered(s)
        s.merge(Setting(key=f"genre_order:{genre.id}", value='["d", "zz", "a"]'))
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_genre(s, genre.id)]
        assert ids == ["d", "a", "b", "c"]


def test_corrupt_order_falls_back_to_default(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = _seed_ordered(s)
        s.merge(Setting(key=f"genre_order:{genre.id}", value="{not json"))
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_genre(s, genre.id)]
        assert ids == ["a", "b", "c", "d"]


def test_order_survives_resync(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = _seed_ordered(s)
        s.merge(Setting(key=f"genre_order:{genre.id}", value='["c", "a", "d", "b"]'))
        s.commit()
        # Re-sync: drop and recreate all tracks for the genre.
        pls = s.exec(select(Playlist).where(Playlist.genre_id == genre.id)).all()
        s.exec(delete(TrackCache).where(TrackCache.playlist_id.in_([p.id for p in pls])))
        s.commit()
        for pl, vids in zip(pls, (["a", "b"], ["c", "d"])):
            for pos, vid in enumerate(vids):
                s.add(
                    TrackCache(
                        playlist_id=pl.id,
                        youtube_video_id=vid,
                        title=vid.upper(),
                        artist="A",
                        position=pos,
                    )
                )
        s.commit()
        ids = [t.youtube_video_id for t in ordered_tracks_for_genre(s, genre.id)]
        assert ids == ["c", "a", "d", "b"]
