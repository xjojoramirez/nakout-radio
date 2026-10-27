from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings
from app.db import get_session
from app.library import apply_snapshot
from app.library_schemas import (
    LibraryDetailOut,
    LibraryGenreOut,
    LibraryPlaylistManifestOut,
    LibraryPlaylistOut,
    LibrarySnapshotOut,
    LibraryTrackOut,
)
from app.main import create_app
from app.models import (
    Genre,
    Playlist,
    TrackCache,
    TrackChartEntry,
    TrackDetail,
)
from app.schemas import ChartEntryOut


@pytest.fixture(autouse=True)
def _library_settings(monkeypatch):
    monkeypatch.setenv("LIBRARY_API_KEY", "test-library-key")
    monkeypatch.setenv("LIBRARY_IMPORT_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/library-import.db",
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


def _genre(slug="rock", name="Rock"):
    return LibraryGenreOut(
        slug=slug, name=name, color="#e0654a", sort_order=1
    )


def _manifest(yt="PL1", label="Rock", genre=None, count=0):
    return LibraryPlaylistManifestOut(
        youtube_playlist_id=yt,
        label=label,
        genre=genre or _genre(),
        track_count=count,
    )


def _membership(yt="PL1", position=0, gain=None):
    return LibraryPlaylistOut(
        youtube_playlist_id=yt,
        label="Rock",
        genre=_genre(),
        position=position,
        gain_db=gain,
    )


def _track(
    video="v1",
    *,
    playlists=None,
    detail=None,
    title="One",
    artist="Art",
    gain_db=None,
):
    return LibraryTrackOut(
        youtube_video_id=video,
        title=title,
        artist=artist,
        duration_seconds=200,
        thumbnail_url=f"https://img/{video}",
        gain_db=gain_db,
        playlists=playlists or [],
        detail=detail,
    )


def _snapshot(*, playlists=None, tracks=None):
    return LibrarySnapshotOut(
        schema_version=1,
        generated_at=datetime.now(timezone.utc),
        playlists=playlists or [],
        tracks=tracks or [],
    )


def _chart(name="Test", peak=3):
    return ChartEntryOut(chart_name=name, peak=peak, year=1999)


def test_import_creates_library_records(tmp_path):
    engine = _engine(tmp_path)
    snapshot = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(
                    album="Album",
                    summary="Summary",
                    charts=[_chart()],
                ),
            )
        ],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, snapshot)
        s.commit()

    assert out.genres_created == 1
    assert out.playlists_created == 1
    assert out.tracks_created == 1
    assert out.memberships_added == 1
    assert out.details_created == 1

    with Session(engine) as s:
        assert len(s.exec(select(Genre)).all()) == 1
        assert len(s.exec(select(Playlist)).all()) == 1
        track = s.exec(select(TrackCache)).one()
        assert track.playlist_id is not None
        detail = s.exec(select(TrackDetail)).one()
        assert detail.album == "Album"
        assert len(s.exec(select(TrackChartEntry)).all()) == 1


def test_import_creates_one_detail_per_video_in_two_playlists(tmp_path):
    engine = _engine(tmp_path)
    snapshot = _snapshot(
        playlists=[_manifest("PL1"), _manifest("PL2", label="Rock B")],
        tracks=[
            _track(
                playlists=[_membership("PL1"), _membership("PL2", position=2)],
                detail=LibraryDetailOut(summary="Shared"),
            )
        ],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, snapshot)
        s.commit()

    assert out.tracks_created == 1
    with Session(engine) as s:
        rows = s.exec(select(TrackCache)).all()
        assert len(rows) == 2
        assert {row.playlist_id for row in rows} == {
            s.exec(select(Playlist.id).where(Playlist.youtube_playlist_id == "PL1")).one(),
            s.exec(select(Playlist.id).where(Playlist.youtube_playlist_id == "PL2")).one(),
        }
        assert len(s.exec(select(TrackDetail)).all()) == 1


def test_reimport_is_idempotent(tmp_path):
    engine = _engine(tmp_path)
    snapshot = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(summary="Summary", locked_fields=[]),
            )
        ],
    )
    with Session(engine) as s:
        apply_snapshot(s, snapshot)
        s.commit()
    with Session(engine) as s:
        out = apply_snapshot(s, snapshot)
        s.commit()

    assert out.tracks_created == 0
    assert out.tracks_updated == 0
    assert out.tracks_unchanged == 1
    assert out.memberships_updated == 0
    assert out.details_updated == 0
    assert out.details_unchanged == 1


def test_import_respects_local_detail_locks(tmp_path):
    engine = _engine(tmp_path)
    first = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(
                    summary="live summary", story="live story"
                ),
            )
        ],
    )
    with Session(engine) as s:
        apply_snapshot(s, first)
        s.commit()

    with Session(engine) as s:
        row = s.exec(select(TrackDetail)).one()
        row.locked_fields = ["story"]
        row.story = "local story"
        s.add(row)
        s.commit()

    second = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(
                    summary="new summary", story="new live story"
                ),
            )
        ],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, second)
        s.commit()

    assert out.locked_fields_skipped >= 1
    with Session(engine) as s:
        row = s.exec(select(TrackDetail)).one()
        assert row.story == "local story"
        assert row.summary == "new summary"
        assert row.locked_fields == ["story"]


def test_import_does_not_reorder_existing_locks(tmp_path):
    engine = _engine(tmp_path)
    snapshot = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(
                    story="story",
                    album="album",
                    locked_fields=["story", "album"],
                ),
            )
        ],
    )
    with Session(engine) as s:
        apply_snapshot(s, snapshot)
        s.commit()
    with Session(engine) as s:
        out = apply_snapshot(s, snapshot)
        s.commit()

    assert out.details_unchanged == 1
    with Session(engine) as s:
        assert s.exec(select(TrackDetail)).one().locked_fields == [
            "story",
            "album",
        ]


def test_dj_note_lock_protects_public_flag(tmp_path):
    engine = _engine(tmp_path)
    first = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(dj_note="one", dj_note_public=True),
            )
        ],
    )
    with Session(engine) as s:
        apply_snapshot(s, first)
        s.commit()

    with Session(engine) as s:
        row = s.exec(select(TrackDetail)).one()
        row.locked_fields = ["dj_note"]
        s.add(row)
        s.commit()

    second = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(
                    dj_note="two", dj_note_public=False
                ),
            )
        ],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, second)
        s.commit()

    assert out.locked_fields_skipped >= 1
    with Session(engine) as s:
        row = s.exec(select(TrackDetail)).one()
        assert row.dj_note == "one"
        assert row.dj_note_public is True


def test_charts_are_replaced_unless_locked(tmp_path):
    engine = _engine(tmp_path)
    first = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(charts=[_chart("First", 1)]),
            )
        ],
    )
    with Session(engine) as s:
        apply_snapshot(s, first)
        s.commit()

    with Session(engine) as s:
        row = s.exec(select(TrackDetail)).one()
        row.locked_fields = ["charts"]
        s.add(row)
        s.commit()

    second = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(charts=[_chart("Second", 2)]),
            )
        ],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, second)
        s.commit()
    assert out.charts_replaced == 0
    with Session(engine) as s:
        assert s.exec(select(TrackChartEntry)).one().chart_name == "First"

    with Session(engine) as s:
        row = s.exec(select(TrackDetail)).one()
        row.locked_fields = []
        s.add(row)
        s.commit()
    with Session(engine) as s:
        out = apply_snapshot(s, second)
        s.commit()
    assert out.charts_replaced == 1
    with Session(engine) as s:
        assert s.exec(select(TrackChartEntry)).one().chart_name == "Second"


def test_removed_membership_detaches_and_reattaches(tmp_path):
    engine = _engine(tmp_path)
    first = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[
            _track(
                playlists=[_membership()],
                detail=LibraryDetailOut(summary="Kept"),
            )
        ],
    )
    with Session(engine) as s:
        apply_snapshot(s, first)
        s.commit()
    with Session(engine) as s:
        original_id = s.exec(select(TrackCache)).one().id

    second = _snapshot(
        playlists=[_manifest(count=0)],
        tracks=[_track(playlists=[])],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, second)
        s.commit()
    assert out.tracks_detached == 1
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        assert row.id == original_id
        assert row.playlist_id is None
        assert row.position == 0
        assert s.exec(select(TrackDetail)).one().summary == "Kept"

    third = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[_track(playlists=[_membership()])],
    )
    with Session(engine) as s:
        apply_snapshot(s, third)
        s.commit()
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        assert row.id == original_id
        assert row.playlist_id is not None


def test_standalone_track_is_created_without_playlists(tmp_path):
    engine = _engine(tmp_path)
    snapshot = _snapshot(
        playlists=[],
        tracks=[_track(playlists=[], gain_db=-3.5)],
    )
    with Session(engine) as s:
        out = apply_snapshot(s, snapshot)
        s.commit()
    assert out.tracks_created == 1
    with Session(engine) as s:
        row = s.exec(select(TrackCache)).one()
        assert row.playlist_id is None
        assert row.gain_db == -3.5


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        LibrarySnapshotOut(
            schema_version=99,
            generated_at=datetime.now(timezone.utc),
        )


def test_import_endpoint_dry_run_rolls_back(tmp_path):
    engine = _engine(tmp_path)
    client = _client(engine)
    body = _snapshot(
        playlists=[_manifest(count=1)],
        tracks=[_track(playlists=[_membership()])],
    ).model_dump(mode="json")
    response = client.post(
        "/api/library/import?dry_run=true",
        json=body,
        headers={"Authorization": "Bearer test-library-key"},
    )
    assert response.status_code == 200
    assert response.json()["tracks_created"] == 1
    assert client.get(
        "/api/library/meta",
        headers={"Authorization": "Bearer test-library-key"},
    ).json()["tracks"] == 0


def test_import_endpoint_rejects_bad_version(tmp_path):
    engine = _engine(tmp_path)
    client = _client(engine)
    body = _snapshot().model_dump(mode="json")
    body["schema_version"] = 99
    response = client.post(
        "/api/library/import",
        json=body,
        headers={"Authorization": "Bearer test-library-key"},
    )
    assert response.status_code == 422
