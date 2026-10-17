import threading
from types import SimpleNamespace

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import loudness
from app.loudness import (
    DeezerLookupError,
    clean_query,
    enrich_pending,
    ensure_backfill,
    lookup_gain,
    offset_for_gain,
    pick_candidate,
)
from app.models import Genre, Playlist, TrackCache


# --- offset math -----------------------------------------------------------


def test_offset_for_gain_states_and_caps():
    assert offset_for_gain(None) == 0.0
    assert offset_for_gain(-15.0) == 0.0
    assert offset_for_gain(-7.0) == -8.0
    assert offset_for_gain(-19.3) == pytest.approx(4.3)
    assert offset_for_gain(-30.0) == 6.0  # boost cap
    assert offset_for_gain(5.0) == -15.0  # attenuation cap


# --- query cleaning --------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "artist", "expected"),
    [
        (
            "Led Zeppelin - Stairway to Heaven (Remaster)",
            "Led Zeppelin",
            ("Stairway to Heaven", "Led Zeppelin"),
        ),
        # The " - " inside brackets must not confuse the artist split.
        ("Hurricane (2015 - Remaster)", "", ("Hurricane", "")),
        ("Artist - Song | Lyrics", "", ("Song", "Artist")),
        ("Artist - Song [HD]", "", ("Song", "Artist")),
        ("Song (Official Video)", "Artist", ("Song", "Artist")),
        ("Song Official Video", "Artist", ("Song", "Artist")),
        ("Song", "Artist", ("Song", "Artist")),
        # Empty right-hand side keeps the raw title and the known artist.
        ("Artist - ", "", ("Artist", "")),
    ],
)
def test_clean_query(title, artist, expected):
    assert clean_query(title, artist) == expected


# --- candidate matching ----------------------------------------------------


def _item(title: str, artist: str, item_id: int = 1) -> dict:
    return {"id": item_id, "title": title, "artist": {"name": artist}}


def test_pick_candidate_rejects_a_different_artist():
    # Measured false positive from the feasibility probe: "Glitch - Shiver"
    # matched "Aaron Glitch - Shivers"; containment alone must not allow it.
    items = [_item("Shivers", "Aaron Glitch")]
    assert pick_candidate(items, "Shiver", "Glitch") is None


def test_pick_candidate_accepts_containment_matches():
    items = [_item("Stairway to Heaven (Remaster)", "Led Zeppelin")]
    assert pick_candidate(items, "Stairway to Heaven", "Led Zeppelin") is not None


def test_pick_candidate_prefers_exact_keys():
    items = [
        _item("The Unforgiven II", "Metallica", 1),
        _item("The Unforgiven", "Metallica", 2),
    ]
    found = pick_candidate(items, "The Unforgiven", "Metallica")
    assert found is not None and found["id"] == 2


def test_pick_candidate_artistless_requires_exact_title():
    items = [_item("Shivers", "Aaron Glitch")]
    assert pick_candidate(items, "Shiver", "") is None
    assert pick_candidate(items, "Shivers", "") is not None


def test_pick_candidate_survives_junk():
    assert pick_candidate([], "Song", "Artist") is None
    assert pick_candidate([{"nope": 1}], "Song", "Artist") is None
    assert pick_candidate([_item("Song", "Artist")], "", "Artist") is None


# --- Deezer lookup ---------------------------------------------------------


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lookup_gain_hit_fetches_detail_once():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 1, "title": "Song", "artist": {"name": "Artist"}}
                    ]
                },
            )
        return httpx.Response(200, json={"gain": -9.5, "bpm": 0})

    with _mock_client(handler) as client:
        assert lookup_gain("Artist - Song", "", client) == -9.5
    assert seen == ["/search", "/track/1"]


def test_lookup_gain_no_match_skips_detail():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "data": [{"id": 2, "title": "Other", "artist": {"name": "X"}}]
            },
        )

    with _mock_client(handler) as client:
        assert lookup_gain("Artist - Song", "", client) is None
    assert seen == ["/search"]


@pytest.mark.parametrize("gain", [0, None, "loud"])
def test_lookup_gain_rejects_unusable_values(gain):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 1, "title": "Song", "artist": {"name": "Artist"}}
                    ]
                },
            )
        return httpx.Response(200, json={} if gain is None else {"gain": gain})

    with _mock_client(handler) as client:
        assert lookup_gain("Artist - Song", "", client) is None


def test_lookup_gain_raises_on_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"error": {"type": "Exception", "message": "Quota exceeded"}}
        )

    with _mock_client(handler) as client:
        with pytest.raises(DeezerLookupError):
            lookup_gain("Artist - Song", "", client)


def test_lookup_gain_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with _mock_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            lookup_gain("Artist - Song", "", client)


# --- enrichment ------------------------------------------------------------


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _factory(engine):
    return lambda: Session(engine)


def _seed(engine, tracks: list[tuple[str, str, str]]) -> None:
    with Session(engine) as s:
        genre = Genre(name="A", slug="a")
        s.add(genre)
        s.commit()
        s.refresh(genre)
        for index, (video_id, title, artist) in enumerate(tracks):
            playlist = Playlist(
                genre_id=genre.id, youtube_playlist_id=f"PL{index}"
            )
            s.add(playlist)
            s.commit()
            s.refresh(playlist)
            s.add(
                TrackCache(
                    playlist_id=playlist.id,
                    youtube_video_id=video_id,
                    title=title,
                    artist=artist,
                )
            )
        s.commit()


def test_enrich_pending_resolves_and_marks_every_row(monkeypatch):
    engine = _engine()
    _seed(
        engine,
        [
            ("v1", "Artist - Song", ""),
            ("v1", "Artist - Song", ""),  # same video in a second playlist
            ("v2", "Nobody - Nope", ""),
        ],
    )
    calls: list[tuple[str, str]] = []

    def fake_lookup(title, artist, client):
        calls.append((title, artist))
        return -9.0 if "Song" in title else None

    monkeypatch.setattr(loudness, "lookup_gain", fake_lookup)
    noop = lambda _s: None  # noqa: E731
    assert enrich_pending(_factory(engine), client=None, sleep=noop) == 2
    # One lookup per distinct video id, miss included.
    assert calls == [("Artist - Song", ""), ("Nobody - Nope", "")]
    with Session(engine) as s:
        rows = s.exec(select(TrackCache).order_by(TrackCache.id)).all()
        assert [r.gain_db for r in rows] == [-9.0, -9.0, None]
        assert all(r.gain_checked_at is not None for r in rows)
    # Nothing left unchecked: a second run is a no-op.
    assert enrich_pending(_factory(engine), client=None, sleep=noop) == 0


def test_enrich_pending_respects_limit(monkeypatch):
    engine = _engine()
    _seed(engine, [(f"v{i}", f"Artist - Song {i}", "") for i in range(3)])
    monkeypatch.setattr(loudness, "lookup_gain", lambda t, a, c: -9.0)
    assert (
        enrich_pending(_factory(engine), client=None, limit=2, sleep=lambda _s: None)
        == 2
    )


def test_enrich_pending_keeps_errors_pending_and_aborts(monkeypatch):
    engine = _engine()
    _seed(engine, [(f"v{i}", f"Artist - Song {i}", "") for i in range(6)])

    def failing_lookup(title, artist, client):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(loudness, "lookup_gain", failing_lookup)
    assert enrich_pending(_factory(engine), client=None, sleep=lambda _s: None) == 0
    with Session(engine) as s:
        rows = s.exec(select(TrackCache)).all()
        assert all(r.gain_checked_at is None and r.gain_db is None for r in rows)


# --- backfill trigger ------------------------------------------------------


def test_ensure_backfill_disabled_by_default():
    # conftest forces LOUDNESS_LOOKUP_ENABLED=false for the test process.
    assert ensure_backfill() is False


def test_ensure_backfill_single_flight(monkeypatch):
    monkeypatch.setattr(
        loudness, "get_settings", lambda: SimpleNamespace(loudness_lookup_enabled=True)
    )
    loudness._backfill_running.set()
    try:
        assert ensure_backfill() is False
    finally:
        loudness._backfill_running.clear()


def test_ensure_backfill_starts_worker(monkeypatch):
    monkeypatch.setattr(
        loudness, "get_settings", lambda: SimpleNamespace(loudness_lookup_enabled=True)
    )
    ran = threading.Event()

    def worker():
        ran.set()
        loudness._backfill_running.clear()

    monkeypatch.setattr(loudness, "_backfill_worker", worker)
    assert ensure_backfill() is True
    assert ran.wait(2.0)
