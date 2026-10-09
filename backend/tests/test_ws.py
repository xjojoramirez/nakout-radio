import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app


def test_listener_count_increments_and_decrements():
    client = TestClient(create_app())
    with client.websocket_connect("/api/ws/listeners") as ws:
        assert ws.receive_json() == {"count": 1}
    with client.websocket_connect("/api/ws/listeners") as ws:
        assert ws.receive_json() == {"count": 1}


def test_listener_connection_cap(monkeypatch):
    from app.routers import ws

    monkeypatch.setattr(ws, "MAX_LISTENERS", 1)
    ws._connections.clear()
    client = TestClient(create_app())
    with client.websocket_connect("/api/ws/listeners") as first:
        assert first.receive_json() == {"count": 1}
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws/listeners"):
                pass
    ws._connections.clear()


def test_radio_connection_cap(monkeypatch):
    from app.routers import ws

    monkeypatch.setattr(ws, "MAX_RADIO_CLIENTS", 1)
    ws._radio_clients.clear()
    client = TestClient(create_app())
    with client.websocket_connect("/api/ws/radio"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws/radio"):
                pass
    ws._radio_clients.clear()


def test_two_listeners_receive_count_then_decrement():
    client = TestClient(create_app())
    with client.websocket_connect("/api/ws/listeners") as ws1:
        assert ws1.receive_json() == {"count": 1}
        with client.websocket_connect("/api/ws/listeners") as ws2:
            assert ws1.receive_json() == {"count": 2}
            assert ws2.receive_json() == {"count": 2}
        assert ws1.receive_json() == {"count": 1}


from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.models import Genre, Playlist, TrackCache


def _radio_client(tmp_path):
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


def _seed(session, slug, vids):
    st = Genre(name=slug.title(), slug=slug, is_default=True)
    session.add(st)
    session.commit()
    session.refresh(st)
    pl = Playlist(genre_id=st.id, youtube_playlist_id=f"PL-{slug}")
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
                duration_seconds=100,
            )
        )
    session.commit()
    return st


def test_radio_pushes_manual_play_at_zero(tmp_path):
    client, engine = _radio_client(tmp_path)
    with Session(engine) as s:
        gid = _seed(s, "chill", ["a", "b", "c"]).id
    client.post("/api/studio/login", json={"password": "test-pass"})
    with client.websocket_connect("/api/ws/radio") as ws:
        resp = client.post(
            "/api/studio/playback/play",
            json={"genre_id": gid, "youtube_video_id": "b"},
        )
        assert resp.status_code == 200
        message = ws.receive_json()
    assert message["source"] == "manual"
    assert message["track"]["youtube_video_id"] == "b"
    assert message["offset_seconds"] == 0


def test_radio_play_without_clients_succeeds(tmp_path):
    client, engine = _radio_client(tmp_path)
    with Session(engine) as s:
        gid = _seed(s, "chill", ["a", "b"]).id
    client.post("/api/studio/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/studio/playback/play",
        json={"genre_id": gid, "youtube_video_id": "b"},
    )
    assert resp.status_code == 200


def test_radio_pushes_skip(tmp_path):
    client, engine = _radio_client(tmp_path)
    with Session(engine) as s:
        gid = _seed(s, "chill", ["a", "b", "c"]).id
    client.post("/api/studio/login", json={"password": "test-pass"})
    client.post(
        "/api/studio/playback/play",
        json={"genre_id": gid, "youtube_video_id": "a"},
    )
    with client.websocket_connect("/api/ws/radio") as ws:
        resp = client.post(
            "/api/studio/playback/next", json={"genre_id": gid}
        )
        assert resp.status_code == 200
        message = ws.receive_json()
    assert message["track"]["youtube_video_id"] == "b"
