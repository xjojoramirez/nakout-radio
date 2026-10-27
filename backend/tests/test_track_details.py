"""Track details: public read API and Studio editing.

Details are keyed by YouTube video id so they survive playlist re-syncs (which
delete and recreate ``TrackCache`` rows).
"""

from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import create_app
from app.models import Genre, Playlist, TrackCache
from app.sync import sync_playlist
from app.youtube import TrackData


def _client(tmp_path):
    from fastapi.testclient import TestClient

    engine = create_engine(
        f"sqlite:///{tmp_path}/t.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app), engine


def _seed(tmp_path):
    client, engine = _client(tmp_path)
    with Session(engine) as s:
        genre = Genre(name="Jazz", slug="jazz", is_default=True)
        s.add(genre)
        s.commit()
        s.refresh(genre)
        playlist = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        s.add(playlist)
        s.commit()
        s.refresh(playlist)
        other = Playlist(genre_id=genre.id, youtube_playlist_id="PL2")
        s.add(other)
        s.commit()
        s.refresh(other)
        s.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="vid1",
                title="Blue in Green",
                artist="Miles Davis",
                thumbnail_url="https://img/1.jpg",
                duration_seconds=337,
                position=0,
            )
        )
        s.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="vid2",
                title="So What",
                artist="Miles Davis",
                thumbnail_url="https://img/2.jpg",
                duration_seconds=545,
                position=1,
            )
        )
        # Same video in a second playlist: the library must not list it twice.
        s.add(
            TrackCache(
                playlist_id=other.id,
                youtube_video_id="vid1",
                title="Blue in Green",
                artist="Miles Davis",
                thumbnail_url="https://img/1.jpg",
                duration_seconds=337,
                position=0,
            )
        )
        s.commit()
    client.post("/api/studio/login", json={"password": "test-pass"})
    return client, engine


def _detail_payload(**overrides):
    payload = {
        "album": "Kind of Blue",
        "album_artist": "Miles Davis",
        "release_date": "1959-08-17",
        "release_year": 1959,
        "label": "Columbia",
        "catalog_number": "CL 1355",
        "isrc": "USSM15900001",
        "track_number": 3,
        "disc_number": 1,
        "genres": ["jazz", "modal jazz"],
        "country": "US",
        "language": "instrumental",
        "bpm": 58,
        "musical_key": "D minor",
        "summary": "A modal jazz ballad from Kind of Blue.",
        "story": "Recorded in two sessions in 1959.",
        "dj_note": "One for the rainy window.",
        "lyric_snippet": "",
        "moods": ["late night", "rainy day"],
        "credits": [
            {"role": "Trumpet", "name": "Miles Davis"},
            {"role": "Piano", "name": "Bill Evans"},
        ],
        "links": [
            {"label": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Blue_in_Green"},
        ],
        "similar_video_ids": ["vid2"],
        "charts": [
            {
                "chart_name": "Billboard Hot 100",
                "country": "US",
                "peak": 1,
                "weeks_on_chart": 12,
                "year": 1959,
                "source_url": "https://example.com/chart",
            }
        ],
        "locked_fields": ["album", "release_year"],
    }
    payload.update(overrides)
    return payload


def test_public_detail_is_404_before_any_details_exist(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.get("/api/tracks/vid1")

    assert resp.status_code == 404


def test_studio_save_creates_detail_readable_on_the_public_api(tmp_path):
    client, _ = _seed(tmp_path)

    saved = client.put("/api/studio/tracks/vid1", json=_detail_payload())
    assert saved.status_code == 200, saved.text

    resp = client.get("/api/tracks/vid1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Blue in Green"
    assert body["artist"] == "Miles Davis"
    assert body["album"] == "Kind of Blue"
    assert body["release_year"] == 1959
    assert body["label"] == "Columbia"
    assert body["track_number"] == 3
    assert body["genres"] == ["jazz", "modal jazz"]
    assert body["moods"] == ["late night", "rainy day"]
    assert body["dj_note"] == "One for the rainy window."
    assert body["credits"] == [
        {"role": "Trumpet", "name": "Miles Davis"},
        {"role": "Piano", "name": "Bill Evans"},
    ]
    assert body["links"][0]["label"] == "Wikipedia"
    assert body["similar"] == [
        {
            "youtube_video_id": "vid2",
            "title": "So What",
            "artist": "Miles Davis",
        }
    ]
    assert body["charts"] == [
        {
            "chart_name": "Billboard Hot 100",
            "country": "US",
            "peak": 1,
            "weeks_on_chart": 12,
            "year": 1959,
            "source_url": "https://example.com/chart",
        }
    ]
    # Internal editorial bookkeeping never reaches the public payload.
    assert "locked_fields" not in body
    assert "sources" not in body


def test_hidden_dj_note_is_not_public(tmp_path):
    client, _ = _seed(tmp_path)
    client.put(
        "/api/studio/tracks/vid1",
        json=_detail_payload(dj_note="Private thought", dj_note_public=False),
    )

    body = client.get("/api/tracks/vid1").json()

    assert body["dj_note"] is None


def test_studio_get_returns_an_empty_shell_for_a_known_track(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.get("/api/studio/tracks/vid1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "empty"
    assert body["completeness"] == 0
    assert body["album"] is None
    assert body["charts"] == []


def test_studio_rejects_unknown_video_id(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.put("/api/studio/tracks/nope", json=_detail_payload())

    assert resp.status_code == 404


def test_studio_save_requires_login(tmp_path):
    client, _ = _seed(tmp_path)
    client.post("/api/studio/logout")

    resp = client.put("/api/studio/tracks/vid1", json=_detail_payload())

    assert resp.status_code == 401


def test_saving_twice_replaces_chart_entries(tmp_path):
    client, _ = _seed(tmp_path)
    client.put("/api/studio/tracks/vid1", json=_detail_payload())

    client.put(
        "/api/studio/tracks/vid1",
        json=_detail_payload(
            charts=[
                {
                    "chart_name": "UK Singles Chart",
                    "country": "UK",
                    "peak": 7,
                    "weeks_on_chart": 3,
                    "year": 1960,
                    "source_url": "",
                }
            ]
        ),
    )

    charts = client.get("/api/tracks/vid1").json()["charts"]
    assert [c["chart_name"] for c in charts] == ["UK Singles Chart"]


def test_locked_fields_round_trip(tmp_path):
    client, _ = _seed(tmp_path)
    client.put("/api/studio/tracks/vid1", json=_detail_payload())

    body = client.get("/api/studio/tracks/vid1").json()

    assert body["locked_fields"] == ["album", "release_year"]
    assert body["status"] == "curated"


def test_studio_rejects_unknown_locked_field(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.put(
        "/api/studio/tracks/vid1",
        json=_detail_payload(locked_fields=["album", "not_a_field"]),
    )

    assert resp.status_code == 422


def test_studio_rejects_invalid_chart_entry(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.put(
        "/api/studio/tracks/vid1",
        json=_detail_payload(
            charts=[
                {
                    "chart_name": "Billboard Hot 100",
                    "country": "US",
                    "peak": 0,
                    "weeks_on_chart": 1,
                    "year": 1959,
                    "source_url": "",
                }
            ]
        ),
    )

    assert resp.status_code == 422


def test_studio_rejects_overlong_lyric_snippet(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.put(
        "/api/studio/tracks/vid1",
        json=_detail_payload(lyric_snippet="x" * 201),
    )

    assert resp.status_code == 422


def test_studio_rejects_non_http_link(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.put(
        "/api/studio/tracks/vid1",
        json=_detail_payload(links=[{"label": "Bad", "url": "javascript:alert(1)"}]),
    )

    assert resp.status_code == 422


def test_library_lists_unique_videos_with_status_and_completeness(tmp_path):
    client, _ = _seed(tmp_path)
    client.put("/api/studio/tracks/vid1", json=_detail_payload())

    resp = client.get("/api/studio/tracks")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    by_id = {item["youtube_video_id"]: item for item in body["items"]}
    assert by_id["vid1"]["status"] == "curated"
    assert by_id["vid1"]["album"] == "Kind of Blue"
    assert by_id["vid1"]["completeness"] == 6
    assert by_id["vid1"]["genres"] == ["Jazz"]
    assert by_id["vid1"]["has_playlist"] is True
    assert by_id["vid2"]["status"] == "empty"
    assert by_id["vid2"]["completeness"] == 0


def test_library_unassigned_filter(tmp_path):
    client, engine = _seed(tmp_path)
    with Session(engine) as s:
        s.add(
            TrackCache(
                playlist_id=None,
                youtube_video_id="solo",
                title="Solo",
                artist="Nobody",
                position=0,
            )
        )
        s.commit()

    resp = client.get("/api/studio/tracks", params={"unassigned": "true"})

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [item["youtube_video_id"] for item in items] == ["solo"]
    assert items[0]["has_playlist"] is False


def test_library_search_matches_title_or_artist(tmp_path):
    client, _ = _seed(tmp_path)

    resp = client.get("/api/studio/tracks", params={"q": "so what"})

    assert [item["youtube_video_id"] for item in resp.json()["items"]] == ["vid2"]


def test_library_status_filter(tmp_path):
    client, _ = _seed(tmp_path)
    client.put("/api/studio/tracks/vid1", json=_detail_payload())

    resp = client.get("/api/studio/tracks", params={"status": "empty"})

    assert [item["youtube_video_id"] for item in resp.json()["items"]] == ["vid2"]


def test_delete_clears_details(tmp_path):
    client, _ = _seed(tmp_path)
    client.put("/api/studio/tracks/vid1", json=_detail_payload())

    assert client.delete("/api/studio/tracks/vid1").status_code == 200

    assert client.get("/api/tracks/vid1").status_code == 404
    assert client.get("/api/studio/tracks/vid1").json()["status"] == "empty"


def test_details_survive_a_playlist_resync(tmp_path):
    client, engine = _seed(tmp_path)
    client.put("/api/studio/tracks/vid1", json=_detail_payload())
    with Session(engine) as session:
        playlist = session.get(Playlist, 1)

        def fetch(_playlist_id: str) -> list[TrackData]:
            return [
                TrackData(
                    youtube_video_id="vid1",
                    title="Blue in Green",
                    artist="Miles Davis",
                    thumbnail_url="https://img/1.jpg",
                    position=0,
                    duration_seconds=337,
                )
            ]

        sync_playlist(session, playlist, fetch)

    assert client.get("/api/tracks/vid1").json()["album"] == "Kind of Blue"
