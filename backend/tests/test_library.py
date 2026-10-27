from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings
from app.db import get_session
from app.main import create_app
from app.models import (
    Genre,
    Playlist,
    TrackCache,
    TrackChartEntry,
    TrackDetail,
)


@pytest.fixture(autouse=True)
def _library_settings(monkeypatch):
    monkeypatch.setenv("LIBRARY_API_KEY", "test-library-key")
    monkeypatch.setenv("LIBRARY_IMPORT_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/library.db",
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


def _headers(key="test-library-key"):
    return {"Authorization": f"Bearer {key}"}


def _seed(engine):
    with Session(engine) as s:
        rock = Genre(name="Rock", slug="rock", color="#e0654a", sort_order=1)
        chill = Genre(name="Chill", slug="chill", color="#5fb3b3", sort_order=2)
        s.add(rock)
        s.add(chill)
        s.commit()
        s.refresh(rock)
        s.refresh(chill)
        rock_one = Playlist(
            genre_id=rock.id, youtube_playlist_id="PL-ROCK-1", label="Rock"
        )
        rock_two = Playlist(
            genre_id=rock.id, youtube_playlist_id="PL-ROCK-2", label="Rock B"
        )
        chill_one = Playlist(
            genre_id=chill.id, youtube_playlist_id="PL-CHILL", label="Chill"
        )
        empty = Playlist(
            genre_id=chill.id, youtube_playlist_id="PL-EMPTY", label="Empty"
        )
        s.add(rock_one)
        s.add(rock_two)
        s.add(chill_one)
        s.add(empty)
        s.commit()
        s.refresh(rock_one)
        s.refresh(rock_two)
        s.refresh(chill_one)
        s.refresh(empty)
        s.add(
            TrackCache(
                playlist_id=rock_one.id,
                youtube_video_id="shared",
                title="Shared",
                artist="Artist",
                position=0,
                duration_seconds=200,
                thumbnail_url="https://img/shared",
            )
        )
        s.add(
            TrackCache(
                playlist_id=rock_two.id,
                youtube_video_id="shared",
                title="Shared",
                artist="Artist",
                position=2,
                duration_seconds=200,
                thumbnail_url="https://img/shared",
            )
        )
        s.add(
            TrackCache(
                playlist_id=chill_one.id,
                youtube_video_id="chill-one",
                title="Chill",
                artist="Other",
                position=1,
                duration_seconds=180,
            )
        )
        s.add(
            TrackCache(
                playlist_id=None,
                youtube_video_id="orphan",
                title="Orphan",
                artist="Nobody",
                position=0,
                duration_seconds=120,
                gain_db=-2.5,
            )
        )
        s.add(
            TrackDetail(
                youtube_video_id="shared",
                album="Album",
                summary="A summary",
                story="A story",
                locked_fields=["story"],
                sources={"summary": {"provider": "wikipedia"}},
            )
        )
        s.add(
            TrackChartEntry(
                youtube_video_id="shared",
                chart_name="Test Chart",
                peak=3,
                year=1999,
            )
        )
        s.commit()


def test_library_requires_bearer_key(tmp_path):
    engine = _engine(tmp_path)
    client = _client(engine)
    assert client.get("/api/library/meta").status_code == 401
    assert client.get(
        "/api/library/meta", headers=_headers("wrong")
    ).status_code == 401
    assert client.get(
        "/api/library/meta", headers=_headers()
    ).status_code == 200


def test_library_disabled_without_configured_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_API_KEY", "")
    get_settings.cache_clear()
    engine = _engine(tmp_path)
    client = _client(engine)
    response = client.get("/api/library/meta")
    assert response.status_code == 503


def test_meta_counts(tmp_path):
    engine = _engine(tmp_path)
    _seed(engine)
    client = _client(engine)
    body = client.get("/api/library/meta", headers=_headers()).json()
    assert body["schema_version"] == 1
    assert body["version"] == "2.0.0"
    assert body["tracks"] == 3
    assert body["standalone_tracks"] == 1
    assert body["details"] == 1
    assert body["playlists"] == 4
    assert body["genres"] == 2


def test_tracks_are_grouped_by_video_with_all_memberships(tmp_path):
    engine = _engine(tmp_path)
    _seed(engine)
    client = _client(engine)
    body = client.get(
        "/api/library/tracks", headers=_headers()
    ).json()
    assert body["total"] == 3
    shared = next(
        item for item in body["items"] if item["youtube_video_id"] == "shared"
    )
    assert [
        membership["youtube_playlist_id"]
        for membership in shared["playlists"]
    ] == ["PL-ROCK-1", "PL-ROCK-2"]
    assert shared["detail"]["album"] == "Album"
    assert shared["detail"]["charts"][0]["peak"] == 3


def test_unassigned_group_contains_standalone_tracks(tmp_path):
    engine = _engine(tmp_path)
    _seed(engine)
    client = _client(engine)
    body = client.get(
        "/api/library/tracks?group=unassigned", headers=_headers()
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["youtube_video_id"] == "orphan"
    assert body["items"][0]["playlists"] == []
    assert body["items"][0]["gain_db"] == -2.5


def test_track_endpoint_returns_detail_and_404(tmp_path):
    engine = _engine(tmp_path)
    _seed(engine)
    client = _client(engine)
    response = client.get(
        "/api/library/tracks/shared", headers=_headers()
    )
    assert response.status_code == 200
    assert response.json()["playlists"][0]["genre"]["slug"] == "rock"
    assert client.get(
        "/api/library/tracks/missing", headers=_headers()
    ).status_code == 404


def test_export_groups_tracks_and_includes_empty_playlists(tmp_path):
    engine = _engine(tmp_path)
    _seed(engine)
    client = _client(engine)
    body = client.get("/api/library/export", headers=_headers()).json()
    assert body["schema_version"] == 1
    assert [
        playlist["youtube_playlist_id"] for playlist in body["playlists"]
    ] == ["PL-ROCK-1", "PL-ROCK-2", "PL-CHILL", "PL-EMPTY"]
    empty = next(
        playlist
        for playlist in body["playlists"]
        if playlist["youtube_playlist_id"] == "PL-EMPTY"
    )
    assert empty["track_count"] == 0
    assert len(body["tracks"]) == 3
    shared = next(
        track
        for track in body["tracks"]
        if track["youtube_video_id"] == "shared"
    )
    assert len(shared["playlists"]) == 2
    assert shared["detail"]["locked_fields"] == ["story"]


def test_import_requires_enabled_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_IMPORT_ENABLED", "false")
    get_settings.cache_clear()
    engine = _engine(tmp_path)
    client = _client(engine)
    body = client.get("/api/library/export", headers=_headers()).json()
    response = client.post(
        "/api/library/import", json=body, headers=_headers()
    )
    assert response.status_code == 404
