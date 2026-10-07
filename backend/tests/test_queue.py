from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import create_app
from app.models import Playlist, Genre, TrackCache
from app.queue import decode_cursor, encode_cursor


def _seed(session):
    genre = Genre(name="Morning", slug="morning", is_default=True)
    session.add(genre)
    session.commit()
    session.refresh(genre)
    pl = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
    session.add(pl)
    session.commit()
    session.refresh(pl)
    for i, vid in enumerate(["v0", "v1", "v2"]):
        session.add(
            TrackCache(
                playlist_id=pl.id,
                youtube_video_id=vid,
                title=vid,
                artist="A",
                position=i,
            )
        )
    session.commit()


def _client(tmp_path):
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


def test_cursor_roundtrip_and_tamper():
    token = encode_cursor("secret", "morning", 2)
    assert decode_cursor("secret", token) == ("morning", 2)
    assert decode_cursor("secret", token + "x") is None
    assert decode_cursor("other", token) is None
    assert decode_cursor("secret", "not-base64!!") is None


def test_advance_next_and_prev_wrap(tmp_path):
    client = _client(tmp_path)
    start = client.get("/api/genres/morning").json()["cursor"]
    nxt = client.post(
        "/api/queue/advance", json={"cursor": start, "direction": "next"}
    ).json()
    assert nxt["track"]["youtube_video_id"] == "v1"
    prev = client.post(
        "/api/queue/advance", json={"cursor": start, "direction": "prev"}
    ).json()
    assert prev["track"]["youtube_video_id"] == "v2"


def test_advance_random_is_in_range(tmp_path):
    client = _client(tmp_path)
    start = client.get("/api/genres/morning").json()["cursor"]
    got = client.post(
        "/api/queue/advance", json={"cursor": start, "direction": "random"}
    ).json()["track"]["youtube_video_id"]
    assert got in {"v0", "v1", "v2"}


def test_advance_invalid_cursor_400(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/queue/advance", json={"cursor": "bad", "direction": "next"})
    assert resp.status_code == 400


def test_advance_unknown_genre_404(tmp_path):
    client = _client(tmp_path)
    token = encode_cursor("test-secret", "nope", 0)
    resp = client.post(
        "/api/queue/advance", json={"cursor": token, "direction": "next"}
    )
    assert resp.status_code == 404


def test_cursor_non_ascii_is_rejected(tmp_path):
    import base64

    client = _client(tmp_path)
    token = base64.urlsafe_b64encode("a:b:é".encode("utf-8")).decode("ascii")
    resp = client.post(
        "/api/queue/advance", json={"cursor": token, "direction": "next"}
    )
    assert resp.status_code == 400


def test_cursor_rotates_on_advance(tmp_path):
    client = _client(tmp_path)
    start = client.get("/api/genres/morning").json()["cursor"]
    nxt = client.post(
        "/api/queue/advance", json={"cursor": start, "direction": "next"}
    ).json()
    assert nxt["cursor"] != start


def test_advance_empty_genre_returns_no_track(tmp_path):
    from sqlmodel import Session, SQLModel, create_engine

    from app.db import get_session
    from app.main import create_app
    from app.models import Genre
    from app.queue import encode_cursor

    engine = create_engine(
        f"sqlite:///{tmp_path}/empty.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Genre(name="Empty", slug="empty"))
        s.commit()

    def override():
        with Session(engine) as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override
    from fastapi.testclient import TestClient

    client = TestClient(app)
    token = encode_cursor("test-secret", "empty", 0)
    resp = client.post(
        "/api/queue/advance", json={"cursor": token, "direction": "next"}
    )
    assert resp.status_code == 200
    assert resp.json()["track"] is None
    assert resp.json()["cursor"] == token
