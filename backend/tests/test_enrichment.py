"""Automatic track enrichment from Deezer and MusicBrainz."""

from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import enrichment
from app.enrichment import pipeline
from app.enrichment.base import (
    ProviderData,
    ProviderError,
    apply_provider_data,
    is_empty,
)
from app.enrichment.deezer import lookup_deezer
from app.enrichment.musicbrainz import lookup_musicbrainz
from app.enrichment.pipeline import enrich_pending, enrich_track, progress
from app.models import Genre, Playlist, TrackCache, TrackDetail


# --- provider parsing ------------------------------------------------------


def _deezer_client(seen: list[str] | None = None, album_error: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        if url.startswith("https://api.deezer.com/search"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 123,
                            "title": "Blue in Green",
                            "artist": {"id": 1, "name": "Miles Davis"},
                            "album": {"id": 9, "title": "Kind of Blue"},
                        }
                    ]
                },
            )
        if url.startswith("https://api.deezer.com/track/123"):
            return httpx.Response(
                200,
                json={
                    "id": 123,
                    "title": "Blue in Green",
                    "bpm": 143.1,
                    "isrc": "USSM15900001",
                    "release_date": "1959-08-17",
                    "track_position": 3,
                    "disk_number": 1,
                    "album": {
                        "id": 9,
                        "title": "Kind of Blue",
                        "release_date": "1959-08-17",
                        "cover_xl": "https://cdn/cover.jpg",
                    },
                    "artist": {"id": 1, "name": "Miles Davis"},
                    "contributors": [
                        {"id": 1, "name": "Miles Davis", "role": "Main Artist"},
                        {"id": 2, "name": "Bill Evans", "role": "Piano"},
                    ],
                },
            )
        if url.startswith("https://api.deezer.com/album/9"):
            if album_error:
                return httpx.Response(
                    200, json={"error": {"message": "album unavailable"}}
                )
            return httpx.Response(
                200,
                json={
                    "id": 9,
                    "title": "Kind of Blue",
                    "label": "Columbia",
                    "release_date": "1959-08-17",
                    "artist": {"id": 1, "name": "Miles Davis"},
                    "genres": {"data": [{"id": 1, "name": "Jazz"}]},
                    "cover_xl": "https://cdn/cover.jpg",
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_deezer_lookup_maps_album_label_credits():
    seen: list[str] = []
    client = _deezer_client(seen)

    data = lookup_deezer("Blue in Green (Remaster)", "Miles Davis", client)

    assert data is not None
    assert data.provider == "deezer"
    assert data.confidence == "exact"
    assert data.fields["album"] == "Kind of Blue"
    assert data.fields["album_artist"] == "Miles Davis"
    assert data.fields["release_date"] == "1959-08-17"
    assert data.fields["release_year"] == 1959
    assert data.fields["label"] == "Columbia"
    assert data.fields["genres"] == ["Jazz"]
    assert data.fields["isrc"] == "USSM15900001"
    assert data.fields["bpm"] == 143
    assert data.fields["track_number"] == 3
    assert data.fields["disc_number"] == 1
    assert data.fields["cover_url"] == "https://cdn/cover.jpg"
    assert data.fields["credits"] == [
        {"role": "Main Artist", "name": "Miles Davis"},
        {"role": "Piano", "name": "Bill Evans"},
    ]
    assert data.url.endswith("/123")
    assert len(seen) == 3


def test_deezer_lookup_keeps_track_data_when_the_album_is_unavailable():
    client = _deezer_client(album_error=True)

    data = lookup_deezer("Blue in Green", "Miles Davis", client)

    assert data is not None
    assert data.fields["album"] == "Kind of Blue"
    assert "label" not in data.fields
    assert data.fields["isrc"] == "USSM15900001"


def test_deezer_lookup_returns_none_for_an_unrelated_artist():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 99,
                        "title": "Blue in Green",
                        "artist": {"name": "Some Other Band"},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    assert lookup_deezer("Blue in Green", "Miles Davis", client) is None


def test_deezer_lookup_raises_on_an_error_payload():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"message": "quota"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError):
        lookup_deezer("Blue in Green", "Miles Davis", client)


def test_deezer_lookup_marks_containment_matches_for_review():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "search" in url:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 7,
                            "title": "Blue in Green Live",
                            "artist": {"name": "Miles Davis"},
                        }
                    ]
                },
            )
        if url.startswith("https://api.deezer.com/track/7"):
            return httpx.Response(
                200,
                json={
                    "id": 7,
                    "title": "Blue in Green Live",
                    "album": {"id": 9, "title": "Live"},
                    "artist": {"name": "Miles Davis"},
                    "contributors": [],
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    data = lookup_deezer("Blue in Green", "Miles Davis", client)

    assert data is not None
    assert data.confidence == "fuzzy"


def _musicbrainz_client(seen: list[str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        if url.startswith("https://musicbrainz.org/ws/2/recording/mb-1"):
            return httpx.Response(
                200,
                json={
                    "id": "mb-1",
                    "title": "Blue in Green",
                    "isrcs": ["USSM15900001"],
                    "releases": [
                        {
                            "id": "rel-1",
                            "title": "Kind of Blue",
                            "date": "1959-08-17",
                            "country": "US",
                            "status": "Official",
                            "release-group": {
                                "id": "rg-1",
                                "title": "Kind of Blue",
                                "first-release-date": "1959-08-17",
                                "primary-type": "Album",
                            },
                        },
                        {
                            "id": "rel-2",
                            "title": "Mitos do jazz",
                            "date": "2012-01-01",
                            "country": "BR",
                            "status": "Official",
                            "release-group": {
                                "id": "rg-2",
                                "title": "Mitos do jazz",
                                "first-release-date": "2012-01-01",
                                "primary-type": "Compilation",
                            },
                        },
                    ],
                },
            )
        if url.startswith("https://musicbrainz.org/ws/2/recording"):
            return httpx.Response(
                200,
                json={
                    "recordings": [
                        {
                            "id": "mb-1",
                            "title": "Blue in Green",
                            "artist-credit": [{"name": "Miles Davis"}],
                            "first-release-date": "1959-08-17",
                            "isrcs": ["USSM15900001"],
                            "releases": [
                                {
                                    "id": "rel-2",
                                    "title": "Mitos do jazz",
                                    "date": "2012-01-01",
                                    "country": "BR",
                                }
                            ],
                        }
                    ]
                },
            )
        if url.startswith("https://musicbrainz.org/ws/2/release/rel-1"):
            return httpx.Response(
                200,
                json={
                    "id": "rel-1",
                    "title": "Kind of Blue",
                    "date": "1959-08-17",
                    "country": "US",
                    "label-info": [{"label": {"name": "Columbia"}}],
                },
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_musicbrainz_lookup_prefers_the_earliest_release_group():
    seen: list[str] = []
    client = _musicbrainz_client(seen)

    data = lookup_musicbrainz(
        "Blue in Green (Remaster)", "Miles Davis", client, sleep=lambda _: None
    )

    assert data is not None
    assert data.provider == "musicbrainz"
    assert data.confidence == "exact"
    assert data.fields["album"] == "Kind of Blue"
    assert data.fields["release_date"] == "1959-08-17"
    assert data.fields["release_year"] == 1959
    assert data.fields["label"] == "Columbia"
    assert data.fields["country"] == "US"
    assert data.fields["isrc"] == "USSM15900001"
    assert data.url == "https://musicbrainz.org/recording/mb-1"
    assert len(seen) == 3
    assert any("/recording/mb-1" in url for url in seen)
    assert any("inc=releases%20release-groups%20isrcs" in url for url in seen)
    assert any("/release/rel-1" in url for url in seen)


def test_musicbrainz_marks_search_only_matches_for_review():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://musicbrainz.org/ws/2/recording/mb-1"):
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "recordings": [
                    {
                        "id": "mb-1",
                        "title": "Blue in Green",
                        "artist-credit": [{"name": "Miles Davis"}],
                        "first-release-date": "1959-08-17",
                        "releases": [
                            {
                                "id": "rel-2",
                                "title": "Mitos do jazz",
                                "date": "2012-01-01",
                                "country": "BR",
                            }
                        ],
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    data = lookup_musicbrainz(
        "Blue in Green", "Miles Davis", client, sleep=lambda _: None
    )

    assert data is not None
    assert data.confidence == "fuzzy"
    assert data.fields["release_year"] == 2012


# --- merge rules -----------------------------------------------------------


def test_merge_fills_empty_fields_and_respects_locks():
    row = TrackDetail(
        youtube_video_id="v1",
        album="Manual album",
        locked_fields=["album"],
    )
    data = ProviderData(
        provider="deezer",
        url="https://deezer/track/1",
        fields={"album": "Auto album", "release_year": 1959, "label": "Columbia"},
    )

    applied = apply_provider_data(row, data, fetched_at="2026-10-26T00:00:00")

    assert applied == 2
    assert row.album == "Manual album"
    assert row.release_year == 1959
    assert row.label == "Columbia"
    assert "album" not in row.sources
    assert row.sources["release_year"] == {
        "provider": "deezer",
        "url": "https://deezer/track/1",
        "fetched_at": "2026-10-26T00:00:00",
    }


def test_merge_does_not_overwrite_an_existing_value_without_force():
    row = TrackDetail(
        youtube_video_id="v1",
        release_year=1959,
        sources={
            "release_year": {
                "provider": "deezer",
                "url": "https://deezer/track/1",
                "fetched_at": "2026-01-01",
            }
        },
    )
    data = ProviderData(
        provider="musicbrainz",
        url="https://musicbrainz/recording/1",
        fields={"release_year": 1970},
    )

    apply_provider_data(row, data, fetched_at="2026-10-26T00:00:00")

    assert row.release_year == 1959
    assert row.sources["release_year"]["provider"] == "deezer"


def test_force_refreshes_auto_fields_but_not_manual_ones():
    row = TrackDetail(
        youtube_video_id="v1",
        album="Manual album",
        release_year=1959,
        sources={
            "release_year": {
                "provider": "deezer",
                "url": "https://deezer/track/1",
                "fetched_at": "2026-01-01",
            }
        },
    )
    data = ProviderData(
        provider="deezer",
        url="https://deezer/track/2",
        fields={"album": "New album", "release_year": 1970},
    )

    apply_provider_data(row, data, fetched_at="2026-10-26T00:00:00", force=True)

    assert row.album == "Manual album"
    assert row.release_year == 1970
    assert row.sources["release_year"]["url"] == "https://deezer/track/2"


def test_empty_values_are_ignored():
    assert is_empty(None)
    assert is_empty("")
    assert is_empty("   ")
    assert is_empty([])
    assert is_empty({})
    assert not is_empty(0)
    assert not is_empty("1959")


# --- pipeline --------------------------------------------------------------


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/enrich.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        genre = Genre(name="Jazz", slug="jazz", is_default=True)
        session.add(genre)
        session.commit()
        session.refresh(genre)
        playlist = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v1",
                title="Blue in Green (Remaster)",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=337,
                position=0,
            )
        )
        session.commit()
    return engine


def _data(**overrides) -> ProviderData:
    fields = {
        "album": "Kind of Blue",
        "release_date": "1959-08-17",
        "release_year": 1959,
        "label": "Columbia",
        "isrc": "USSM15900001",
        "genres": ["Jazz"],
        "cover_url": "https://cdn/cover.jpg",
        "credits": [{"role": "Piano", "name": "Bill Evans"}],
    }
    fields.update(overrides)
    return ProviderData(
        provider="deezer",
        url="https://deezer/track/123",
        confidence="exact",
        fields=fields,
    )


def test_enrich_track_fills_and_marks_auto(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_track(
            session,
            "v1",
            client=object(),
            deezer=lambda *_: _data(),
            musicbrainz=lambda *_: pytest.fail("MusicBrainz should not be needed"),
        )
        row = session.get(TrackDetail, "v1")

    assert outcome.committed is True
    assert outcome.matched is True
    assert outcome.providers == ["deezer"]
    assert row is not None
    assert row.album == "Kind of Blue"
    assert row.enriched_at is not None
    assert row.enrich_error is None
    assert row.needs_review is False
    assert row.sources["album"]["provider"] == "deezer"


def test_enrich_track_calls_musicbrainz_for_gaps(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_track(
            session,
            "v1",
            client=object(),
            deezer=lambda *_: _data(label=None, release_year=None),
            musicbrainz=lambda *_: ProviderData(
                provider="musicbrainz",
                url="https://musicbrainz/recording/1",
                confidence="fuzzy",
                fields={"release_year": 1959, "label": "Columbia"},
            ),
        )
        row = session.get(TrackDetail, "v1")

    assert outcome.providers == ["deezer", "musicbrainz"]
    assert outcome.confidence == "fuzzy"
    assert row.needs_review is True
    assert row.release_year == 1959
    assert row.sources["release_year"]["provider"] == "musicbrainz"


def test_definitive_miss_is_remembered(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_track(
            session,
            "v1",
            client=object(),
            deezer=lambda *_: None,
            musicbrainz=lambda *_: None,
        )
        row = session.get(TrackDetail, "v1")

    assert outcome.committed is True
    assert outcome.matched is False
    assert row is not None
    assert row.enriched_at is not None
    assert row.enrich_error is None


def test_provider_errors_leave_the_track_pending(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        outcome = enrich_track(
            session,
            "v1",
            client=object(),
            deezer=lambda *_: (_ for _ in ()).throw(ProviderError("down")),
            musicbrainz=lambda *_: (_ for _ in ()).throw(ProviderError("down")),
        )
        row = session.get(TrackDetail, "v1")

    assert outcome.committed is False
    assert outcome.errors
    assert row is None


def test_enrich_pending_dedupes_video_ids(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        playlist = session.exec(select(Playlist)).first()
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v1",
                title="Blue in Green",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=337,
                position=1,
            )
        )
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v2",
                title="So What",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=545,
                position=2,
            )
        )
        session.commit()

    def fake_deezer(_title, _artist, _client):
        return _data()

    processed = enrich_pending(
        lambda: Session(engine),
        object(),
        deezer=fake_deezer,
        musicbrainz=None,
        pause_seconds=0,
        sleep=lambda _: None,
    )

    with Session(engine) as session:
        rows = session.exec(select(TrackDetail)).all()
        call_count = progress(session)

    assert processed == 2
    assert {row.youtube_video_id for row in rows} == {"v1", "v2"}
    assert call_count["enriched"] == 2
    assert call_count["remaining"] == 0


def test_enrich_pending_aborts_after_consecutive_errors(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        playlist = session.exec(select(Playlist)).first()
        for index in range(6):
            session.add(
                TrackCache(
                    playlist_id=playlist.id,
                    youtube_video_id=f"err{index}",
                    title=f"Track {index}",
                    artist="Nobody",
                    thumbnail_url="",
                    duration_seconds=100,
                    position=index + 1,
                )
            )
        session.commit()

    calls: list[str] = []

    def failing(title, _artist, _client):
        calls.append(title)
        raise ProviderError("down")

    monkeypatch.setattr(
        pipeline,
        "get_settings",
        lambda: SimpleNamespace(
            enrichment_pause_seconds=0,
            enrichment_max_consecutive_errors=5,
        ),
    )

    processed = enrich_pending(
        lambda: Session(engine),
        object(),
        deezer=failing,
        musicbrainz=None,
        pause_seconds=0,
        sleep=lambda _: None,
    )

    assert processed == 0
    assert len(calls) == 5


def test_ensure_backfill_is_disabled_by_config(monkeypatch):
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: SimpleNamespace(enrichment_enabled=False)
    )

    assert enrichment.ensure_backfill() is False
    assert enrichment.is_running() is False


def test_ensure_backfill_is_single_flight(monkeypatch):
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: SimpleNamespace(enrichment_enabled=True)
    )
    pipeline._running.set()
    try:
        assert enrichment.ensure_backfill() is False
    finally:
        pipeline._running.clear()


# --- API -------------------------------------------------------------------


def _api_client(tmp_path):
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import create_app

    engine = create_engine(
        f"sqlite:///{tmp_path}/api.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        genre = Genre(name="Jazz", slug="jazz", is_default=True)
        session.add(genre)
        session.commit()
        session.refresh(genre)
        playlist = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v1",
                title="Blue in Green",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=337,
                position=0,
            )
        )
        session.commit()

    def override():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    client.post("/api/studio/login", json={"password": "test-pass"})
    return client, engine


def test_studio_can_fetch_details_for_one_track(tmp_path, monkeypatch):
    client, _ = _api_client(tmp_path)
    monkeypatch.setattr(pipeline, "lookup_deezer", lambda *_: _data())
    monkeypatch.setattr(pipeline, "lookup_musicbrainz", lambda *_: None)
    monkeypatch.setattr(pipeline, "lookup_wikipedia", lambda *_: None)

    resp = client.post("/api/studio/tracks/v1/enrich")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["album"] == "Kind of Blue"
    assert body["status"] == "auto"
    assert body["metadata_sources"] == ["Deezer"]
    public = client.get("/api/tracks/v1")
    assert public.status_code == 200
    assert public.json()["metadata_sources"] == ["Deezer"]


def test_studio_enrich_requires_login(tmp_path, monkeypatch):
    client, _ = _api_client(tmp_path)
    client.post("/api/studio/logout")
    monkeypatch.setattr(pipeline, "lookup_deezer", lambda *_: _data())

    assert client.post("/api/studio/tracks/v1/enrich").status_code == 401


def test_studio_enrich_reports_provider_outages(tmp_path, monkeypatch):
    client, _ = _api_client(tmp_path)

    def fail(*_args):
        raise ProviderError("deezer is down")

    monkeypatch.setattr(pipeline, "lookup_deezer", fail)
    monkeypatch.setattr(pipeline, "lookup_musicbrainz", fail)
    monkeypatch.setattr(pipeline, "lookup_wikipedia", fail)

    resp = client.post("/api/studio/tracks/v1/enrich")

    assert resp.status_code == 502


def test_enrichment_status_counts(tmp_path):
    client, engine = _api_client(tmp_path)
    assert client.get("/api/studio/tracks/enrich/status").json() == {
        "running": False,
        "total": 1,
        "enriched": 0,
        "failed": 0,
        "remaining": 1,
        "stories": 0,
        "stories_failed": 0,
    }
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                album="Kind of Blue",
                enriched_at=datetime(2026, 10, 26),
            )
        )
        session.commit()

    body = client.get("/api/studio/tracks/enrich/status").json()

    assert body["enriched"] == 1
    assert body["remaining"] == 0


def test_enrich_all_starts_the_worker(tmp_path, monkeypatch):
    client, _ = _api_client(tmp_path)
    monkeypatch.setattr(enrichment, "ensure_backfill", lambda **_: True)

    resp = client.post("/api/studio/tracks/enrich")

    assert resp.status_code == 200
    assert resp.json() == {"started": True}


def test_library_item_exposes_the_review_flag(tmp_path):
    client, engine = _api_client(tmp_path)
    with Session(engine) as session:
        session.add(TrackDetail(youtube_video_id="v1", needs_review=True))
        session.commit()

    items = client.get("/api/studio/tracks").json()["items"]

    assert items[0]["needs_review"] is True
