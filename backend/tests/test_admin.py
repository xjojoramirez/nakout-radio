import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import get_session
from app.main import create_app
from app.models import Playlist, ScheduleSlot, Genre, TrackCache
from app.youtube import TrackData


def _client(tmp_path):
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


def test_login_sets_cookie(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/login", json={"password": "test-pass"})
    assert resp.status_code == 200
    assert "nakout_session" in resp.cookies


def test_login_rejects_bad_password(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_locks_out_after_repeated_failures(tmp_path):
    client, _ = _client(tmp_path)
    for _ in range(5):
        assert (
            client.post("/api/admin/login", json={"password": "nope"}).status_code
            == 401
        )
    assert (
        client.post("/api/admin/login", json={"password": "nope"}).status_code == 429
    )
    assert (
        client.post("/api/admin/login", json={"password": "test-pass"}).status_code
        == 429
    )


def test_login_success_resets_failure_counter(tmp_path):
    client, _ = _client(tmp_path)
    for _ in range(4):
        assert (
            client.post("/api/admin/login", json={"password": "nope"}).status_code
            == 401
        )
    assert (
        client.post("/api/admin/login", json={"password": "test-pass"}).status_code
        == 200
    )
    for _ in range(4):
        assert (
            client.post("/api/admin/login", json={"password": "nope"}).status_code
            == 401
        )
    assert (
        client.post("/api/admin/login", json={"password": "test-pass"}).status_code
        == 200
    )


def test_logout_revokes_session_server_side(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/login", json={"password": "test-pass"})
    token = resp.cookies["nakout_session"]
    assert client.get("/api/admin/session").status_code == 200
    client.post("/api/admin/logout")
    reused = client.get(
        "/api/admin/session", headers={"Cookie": f"nakout_session={token}"}
    )
    assert reused.status_code == 401


def test_create_genre_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/genres", json={"name": "Chill", "slug": "chill"})
    assert resp.status_code == 401


def test_create_genre_when_authed(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post("/api/admin/genres", json={"name": "Chill", "slug": "chill"})
    assert resp.status_code == 201
    assert resp.json()["slug"] == "chill"


def test_duplicate_slug_returns_409(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post("/api/admin/genres", json={"name": "Chill", "slug": "chill"})
    resp = client.post("/api/admin/genres", json={"name": "Chill2", "slug": "chill"})
    assert resp.status_code == 409


def test_delete_genre_removes_children(tmp_path):
    client, engine = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    with Session(engine) as s:
        pl = Playlist(genre_id=sid, youtube_playlist_id="PL1")
        s.add(pl)
        s.commit()
        s.refresh(pl)
        s.add(
            TrackCache(
                playlist_id=pl.id,
                youtube_video_id="v",
                title="t",
                artist="a",
                position=0,
            )
        )
        s.add(
            ScheduleSlot(genre_id=sid, days_of_week=[0], start_time="06:00")
        )
        s.commit()
    assert client.delete(f"/api/admin/genres/{sid}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Playlist)).all() == []
        assert s.exec(select(TrackCache)).all() == []
        assert s.exec(select(ScheduleSlot)).all() == []
        assert s.exec(select(Genre)).all() == []


def test_update_genre_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.put("/api/admin/genres/1", json={"name": "X"})
    assert resp.status_code == 401


def test_update_genre_when_authed(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    resp = client.put(
        f"/api/admin/genres/{sid}", json={"name": "Rock", "slug": "rock"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Rock"
    assert body["slug"] == "rock"


def test_update_genre_unknown_404(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.put("/api/admin/genres/999", json={"name": "X"})
    assert resp.status_code == 404


def test_update_genre_duplicate_slug_409(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post("/api/admin/genres", json={"name": "A", "slug": "a"})
    sid = client.post(
        "/api/admin/genres", json={"name": "B", "slug": "b"}
    ).json()["id"]
    resp = client.put(f"/api/admin/genres/{sid}", json={"slug": "a"})
    assert resp.status_code == 409


def test_update_genre_keeps_untouched_fields(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres",
        json={"name": "S", "slug": "s", "sort_order": 4},
    ).json()["id"]
    client.put(f"/api/admin/genres/{sid}", json={"name": "Renamed"})
    resp = client.put(f"/api/admin/genres/{sid}", json={"is_default": True})
    assert resp.status_code == 200
    assert resp.json()["sort_order"] == 4


def test_update_genre_sets_exclusive_default(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post(
        "/api/admin/genres", json={"name": "A", "slug": "a", "is_default": True}
    )
    second = client.post(
        "/api/admin/genres", json={"name": "B", "slug": "b"}
    ).json()["id"]
    resp = client.put(f"/api/admin/genres/{second}", json={"is_default": True})
    assert resp.status_code == 200
    genres = client.get("/api/genres").json()
    assert [g["id"] for g in genres if g["is_default"]] == [second]


def test_create_playlist_unknown_genre_404(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/playlists",
        json={"genre_id": 999, "youtube_playlist_url": "PL1", "label": ""},
    )
    assert resp.status_code == 404


def test_create_slot_unknown_genre_404(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/slots",
        json={
            "genre_id": 999,
            "days_of_week": [0],
            "start_time": "06:00",
        },
    )
    assert resp.status_code == 404


def _create_slot(client, genre_id, **overrides):
    payload = {
        "genre_id": genre_id,
        "days_of_week": [0],
        "start_time": "06:00",
    }
    payload.update(overrides)
    return client.post("/api/admin/slots", json=payload)


def test_list_slots_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/admin/slots").status_code == 401


def test_list_slots_empty(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    resp = client.get("/api/admin/slots")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_slots_includes_genre_name_and_fields(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    _create_slot(client, sid)
    resp = client.get("/api/admin/slots")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["genre_id"] == sid
    assert body[0]["genre_name"] == "Chill"
    assert body[0]["days_of_week"] == [0]
    assert body[0]["start_time"] == "06:00"


def test_create_slot_returns_genre_name(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    resp = _create_slot(client, sid)
    assert resp.status_code == 201
    assert resp.json()["genre_name"] == "Chill"


def test_list_slots_orders_by_id(tmp_path):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    with Session(engine) as s:
        first = ScheduleSlot(genre_id=sid, days_of_week=[1], start_time="01:00")
        s.add(first)
        s.commit()
        first_id = first.id
        second = ScheduleSlot(genre_id=sid, days_of_week=[2], start_time="03:00")
        s.add(second)
        s.commit()
        second_id = second.id
    body = client.get("/api/admin/slots").json()
    assert [s["id"] for s in body] == [first_id, second_id]


def test_update_slot_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.put("/api/admin/slots/1", json={"start_time": "01:00"}).status_code == 401


def test_update_slot(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    slot_id = _create_slot(client, sid).json()["id"]
    resp = client.put(
        f"/api/admin/slots/{slot_id}",
        json={"days_of_week": [5, 6], "start_time": "22:00"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days_of_week"] == [5, 6]
    assert body["start_time"] == "22:00"
    assert body["genre_id"] == sid
    assert body["genre_name"] == "Chill"


def test_update_slot_unknown_404(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    resp = client.put("/api/admin/slots/999", json={"start_time": "01:00"})
    assert resp.status_code == 404


def test_update_slot_unknown_genre_404(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    slot_id = _create_slot(client, sid).json()["id"]
    resp = client.put(f"/api/admin/slots/{slot_id}", json={"genre_id": 999})
    assert resp.status_code == 404
    assert client.get("/api/admin/slots").json()[0]["genre_id"] == sid


def test_update_slot_rejects_bad_time(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    slot_id = _create_slot(client, sid).json()["id"]
    assert (
        client.put(f"/api/admin/slots/{slot_id}", json={"start_time": "nope"}).status_code
        == 422
    )


def test_create_slot_duplicate_start_returns_409(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    assert _create_slot(client, sid).status_code == 201
    assert _create_slot(client, sid, days_of_week=[0, 2]).status_code == 409


def test_create_slot_same_time_other_day_allowed(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    assert _create_slot(client, sid, days_of_week=[0]).status_code == 201
    assert _create_slot(client, sid, days_of_week=[1]).status_code == 201


def test_update_slot_duplicate_start_returns_409(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    _create_slot(client, sid, days_of_week=[0], start_time="06:00")
    second = _create_slot(client, sid, days_of_week=[0], start_time="12:00").json()["id"]
    resp = client.put(f"/api/admin/slots/{second}", json={"start_time": "06:00"})
    assert resp.status_code == 409


def test_create_slot_unpadded_time_still_collides(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    assert _create_slot(client, sid, start_time="06:00").status_code == 201
    assert _create_slot(client, sid, start_time="6:00").status_code == 409


def test_create_slot_empty_days_returns_422(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    assert _create_slot(client, sid, days_of_week=[]).status_code == 422


def test_update_slot_null_fields_are_ignored(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    slot_id = _create_slot(client, sid).json()["id"]
    resp = client.put(
        f"/api/admin/slots/{slot_id}",
        json={"days_of_week": None, "start_time": None},
    )
    assert resp.status_code == 200
    body = client.get("/api/admin/slots").json()[0]
    assert body["days_of_week"] == [0]
    assert body["start_time"] == "06:00"


def test_update_slot_days_overlap_returns_409(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    _create_slot(client, sid, days_of_week=[0], start_time="06:00")
    second = _create_slot(client, sid, days_of_week=[1], start_time="06:00").json()["id"]
    resp = client.put(f"/api/admin/slots/{second}", json={"days_of_week": [0, 1]})
    assert resp.status_code == 409


def test_update_slot_genre_only_does_not_self_conflict(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    first_genre = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    second_genre = client.post(
        "/api/admin/genres", json={"name": "Rock", "slug": "rock"}
    ).json()["id"]
    slot_id = _create_slot(client, first_genre).json()["id"]
    resp = client.put(f"/api/admin/slots/{slot_id}", json={"genre_id": second_genre})
    assert resp.status_code == 200
    assert resp.json()["genre_id"] == second_genre


def test_delete_slot(tmp_path):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "Chill", "slug": "chill"}
    ).json()["id"]
    slot_id = _create_slot(client, sid).json()["id"]
    assert client.delete(f"/api/admin/slots/{slot_id}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(ScheduleSlot)).all() == []
    assert client.get("/api/admin/slots").json() == []


def test_delete_slot_missing_404(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    assert client.delete("/api/admin/slots/999").status_code == 404


def test_delete_slot_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.delete("/api/admin/slots/1").status_code == 401


def test_logout_clears_session(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post("/api/admin/logout")
    resp = client.post("/api/admin/genres", json={"name": "X", "slug": "x"})
    assert resp.status_code == 401


def test_session_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/admin/session").status_code == 401


def test_session_returns_ok_when_authed(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.get("/api/admin/session")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/admin/genres", {"name": "A", "slug": "a"}),
        (
            "/api/admin/playlists",
            {"genre_id": 1, "youtube_playlist_url": "PL1", "label": ""},
        ),
        (
            "/api/admin/slots",
            {"genre_id": 1, "days_of_week": [0], "start_time": "06:00"},
        ),
    ],
)
def test_mutating_endpoints_require_auth(tmp_path, path, payload):
    client, _ = _client(tmp_path)
    assert client.post(path, json=payload).status_code == 401


def _fake_fetch(tracks):
    return lambda _pid: list(tracks)


def test_create_playlist_syncs_tracks(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch(
            [TrackData("v1", "One", "A", "u", 0), TrackData("v2", "Two", "A", "u", 1)]
        ),
    )
    resp = client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": ""},
    )
    assert resp.status_code == 201
    assert resp.json()["synced"] == 2
    with Session(engine) as s:
        rows = s.exec(select(TrackCache)).all()
        assert len(rows) == 2


def test_create_playlist_fetch_error_is_reported(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]

    def boom(_pid):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.routers.admin._build_fetch", lambda: boom)
    resp = client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": ""},
    )
    assert resp.status_code == 201
    assert resp.json()["synced"] == 0
    assert resp.json()["sync_error"]
    with Session(engine) as s:
        assert len(s.exec(select(Playlist)).all()) == 1


def test_refresh_playlist(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch([TrackData("v1", "One", "A", "u", 0)]),
    )
    pid = client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": ""},
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch([TrackData("v2", "Two", "A", "u", 0)]),
    )
    resp = client.post(f"/api/admin/playlists/{pid}/refresh")
    assert resp.status_code == 200
    assert resp.json()["synced"] == 1
    with Session(engine) as s:
        rows = s.exec(select(TrackCache)).all()
        assert [r.youtube_video_id for r in rows] == ["v2"]


def test_refresh_missing_playlist_404(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    assert client.post("/api/admin/playlists/999/refresh").status_code == 404


def test_sync_all_reports_each_playlist(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch([TrackData("v1", "One", "A", "u", 0)]),
    )
    client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": ""},
    )
    client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL2", "label": ""},
    )
    resp = client.post("/api/admin/sync")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 2


def _login(client):
    client.post("/api/admin/login", json={"password": "test-pass"})


def test_channel_endpoints_require_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/admin/youtube/channel").status_code == 401
    assert (
        client.put("/api/admin/youtube/channel", json={"channel": "@x"}).status_code
        == 401
    )


def test_get_channel_empty(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    resp = client.get("/api/admin/youtube/channel")
    assert resp.status_code == 200
    assert resp.json() == {"channel_id": None, "title": None}


def test_set_and_get_channel(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    monkeypatch.setattr(
        "app.routers.admin.resolve_channel_id",
        lambda value, api_key, client: ("UCresolved", "My Channel"),
    )
    resp = client.put("/api/admin/youtube/channel", json={"channel": "@me"})
    assert resp.status_code == 200
    assert resp.json() == {"channel_id": "UCresolved", "title": "My Channel"}
    again = client.get("/api/admin/youtube/channel")
    assert again.json() == {"channel_id": "UCresolved", "title": "My Channel"}


def test_set_channel_invalid_returns_400(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)

    def boom(value, api_key, client):
        raise ValueError("channel not found")

    monkeypatch.setattr("app.routers.admin.resolve_channel_id", boom)
    resp = client.put("/api/admin/youtube/channel", json={"channel": "UCnope"})
    assert resp.status_code == 400
    assert "channel not found" in resp.json()["detail"]


def test_set_channel_requires_non_empty(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    resp = client.put("/api/admin/youtube/channel", json={"channel": "   "})
    assert resp.status_code == 400


def test_set_channel_httpx_error_returns_502(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)

    def boom(value, api_key, client):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.routers.admin.resolve_channel_id", boom)
    resp = client.put("/api/admin/youtube/channel", json={"channel": "@me"})
    assert resp.status_code == 502


def test_set_channel_updates_existing(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    monkeypatch.setattr(
        "app.routers.admin.resolve_channel_id",
        lambda value, api_key, client: ("UC1", "First"),
    )
    client.put("/api/admin/youtube/channel", json={"channel": "@one"})
    monkeypatch.setattr(
        "app.routers.admin.resolve_channel_id",
        lambda value, api_key, client: ("UC2", "Second"),
    )
    client.put("/api/admin/youtube/channel", json={"channel": "@two"})
    assert client.get("/api/admin/youtube/channel").json() == {
        "channel_id": "UC2",
        "title": "Second",
    }


def test_list_playlists_no_channel_is_empty(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    resp = client.get("/api/admin/youtube/playlists")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_playlists_marks_already_added(tmp_path, monkeypatch):
    from app.youtube import PlaylistData

    client, engine = _client(tmp_path)
    _login(client)
    monkeypatch.setattr(
        "app.routers.admin.resolve_channel_id",
        lambda value, api_key, client: ("UCresolved", "My Channel"),
    )
    client.put("/api/admin/youtube/channel", json={"channel": "@me"})
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    with Session(engine) as s:
        s.add(Playlist(genre_id=sid, youtube_playlist_id="PLadded"))
        s.commit()

    monkeypatch.setattr(
        "app.routers.admin.fetch_channel_playlists",
        lambda channel_id, api_key, client: [
            PlaylistData("PLadded", "Added One", 3, "u1"),
            PlaylistData("PLnew", "New One", 5, "u2"),
        ],
    )
    resp = client.get("/api/admin/youtube/playlists")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "youtube_playlist_id": "PLadded",
            "title": "Added One",
            "item_count": 3,
            "thumbnail_url": "u1",
            "already_added": True,
        },
        {
            "youtube_playlist_id": "PLnew",
            "title": "New One",
            "item_count": 5,
            "thumbnail_url": "u2",
            "already_added": False,
        },
    ]


def test_list_playlists_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/admin/youtube/playlists").status_code == 401


def test_list_playlists_httpx_error_returns_502(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    monkeypatch.setattr(
        "app.routers.admin.resolve_channel_id",
        lambda value, api_key, client: ("UCresolved", "My Channel"),
    )
    client.put("/api/admin/youtube/channel", json={"channel": "@me"})

    def boom(channel_id, api_key, client):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.routers.admin.fetch_channel_playlists", boom)
    resp = client.get("/api/admin/youtube/playlists")
    assert resp.status_code == 502


def test_list_playlists_forwards_saved_channel(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    monkeypatch.setattr(
        "app.routers.admin.resolve_channel_id",
        lambda value, api_key, client: ("UCresolved", "My Channel"),
    )
    client.put("/api/admin/youtube/channel", json={"channel": "@me"})
    seen = {}

    def fake(channel_id, api_key, client):
        seen["channel_id"] = channel_id
        return []

    monkeypatch.setattr("app.routers.admin.fetch_channel_playlists", fake)
    assert client.get("/api/admin/youtube/playlists").status_code == 200
    assert seen["channel_id"] == "UCresolved"


def test_set_channel_error_redacts_api_key(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    request = httpx.Request(
        "GET",
        "https://www.googleapis.com/youtube/v3/channels?key=SECRET123&id=UCx",
    )
    response = httpx.Response(403, request=request)

    def boom(value, api_key, client):
        raise httpx.HTTPStatusError("403", request=request, response=response)

    monkeypatch.setattr("app.routers.admin.resolve_channel_id", boom)
    resp = client.put("/api/admin/youtube/channel", json={"channel": "UCx"})
    assert resp.status_code == 502
    assert "SECRET123" not in resp.text


def test_list_added_playlists_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/admin/playlists").status_code == 401


def test_list_added_playlists(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch(
            [TrackData("v1", "One", "A", "u", 0), TrackData("v2", "Two", "A", "u", 1)]
        ),
    )
    client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": "L"},
    )
    resp = client.get("/api/admin/playlists")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["genre_id"] == sid
    assert body[0]["genre_name"] == "S"
    assert body[0]["youtube_playlist_id"] == "PL1"
    assert body[0]["label"] == "L"
    assert body[0]["track_count"] == 2


def test_list_added_playlists_counts_zero_without_tracks(tmp_path):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    with Session(engine) as s:
        s.add(Playlist(genre_id=sid, youtube_playlist_id="PL1"))
        s.commit()
    resp = client.get("/api/admin/playlists")
    assert resp.status_code == 200
    assert resp.json()[0]["track_count"] == 0


def test_delete_playlist_removes_tracks(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch([TrackData("v1", "One", "A", "u", 0)]),
    )
    pid = client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": ""},
    ).json()["id"]
    assert client.delete(f"/api/admin/playlists/{pid}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Playlist)).all() == []
        assert s.exec(select(TrackCache)).all() == []


def test_delete_playlist_missing_404(tmp_path):
    client, _ = _client(tmp_path)
    _login(client)
    assert client.delete("/api/admin/playlists/999").status_code == 404


def test_delete_playlist_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.delete("/api/admin/playlists/1").status_code == 401


def test_list_added_playlists_orders_by_genre_then_id(tmp_path):
    client, engine = _client(tmp_path)
    _login(client)
    sid_a = client.post(
        "/api/admin/genres", json={"name": "A", "slug": "a"}
    ).json()["id"]
    sid_b = client.post(
        "/api/admin/genres", json={"name": "B", "slug": "b"}
    ).json()["id"]
    assert sid_a < sid_b
    with Session(engine) as s:
        pla1 = Playlist(genre_id=sid_a, youtube_playlist_id="PLA1")
        s.add(pla1)
        s.commit()
        s.refresh(pla1)
        plb1 = Playlist(genre_id=sid_b, youtube_playlist_id="PLB1")
        s.add(plb1)
        s.commit()
        s.refresh(plb1)
        pla2 = Playlist(genre_id=sid_a, youtube_playlist_id="PLA2")
        s.add(pla2)
        s.commit()
        s.refresh(pla2)
    resp = client.get("/api/admin/playlists")
    assert resp.status_code == 200
    body = resp.json()
    keys = [(p["genre_id"], p["id"]) for p in body]
    assert keys == sorted(keys)
    assert [p["youtube_playlist_id"] for p in body] == ["PLA1", "PLA2", "PLB1"]
    assert [p["genre_name"] for p in body] == ["A", "A", "B"]


def test_delete_playlist_leaves_other_playlists_tracks(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/genres", json={"name": "S", "slug": "s"}
    ).json()["id"]
    batches = iter(
        [
            [TrackData("v1", "One", "A", "u", 0)],
            [TrackData("v2", "Two", "A", "u", 0)],
        ]
    )
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: (lambda _pid: list(next(batches))),
    )
    first = client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL1", "label": ""},
    ).json()
    second = client.post(
        "/api/admin/playlists",
        json={"genre_id": sid, "youtube_playlist_url": "PL2", "label": ""},
    ).json()
    assert client.delete(f"/api/admin/playlists/{first['id']}").status_code == 200
    with Session(engine) as s:
        playlists = s.exec(select(Playlist)).all()
        assert [p.id for p in playlists] == [second["id"]]
        tracks = s.exec(select(TrackCache)).all()
        assert [t.playlist_id for t in tracks] == [second["id"]]
        assert [t.youtube_video_id for t in tracks] == ["v2"]


def _seed_genre_with_tracks(engine, slug="chill", vids=("a", "b", "c")):
    from app.models import Playlist, Genre, TrackCache

    with Session(engine) as s:
        st = Genre(name=slug.title(), slug=slug, is_default=True)
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(genre_id=st.id, youtube_playlist_id=f"PL-{slug}")
        s.add(pl)
        s.commit()
        s.refresh(pl)
        for pos, vid in enumerate(vids):
            s.add(
                TrackCache(
                    playlist_id=pl.id,
                    youtube_video_id=vid,
                    title=vid.upper(),
                    artist="A",
                    position=pos,
                    duration_seconds=100,
                )
            )
        s.commit()
        return st.id


def test_genre_tracks_requires_auth(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    assert client.get(f"/api/admin/genres/{sid}/tracks").status_code == 401


def test_genre_tracks_returns_ordered_list(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.put(f"/api/admin/genres/{sid}/order", json={"video_ids": ["c", "a"]})
    body = client.get(f"/api/admin/genres/{sid}/tracks").json()
    assert [t["youtube_video_id"] for t in body] == ["c", "a", "b"]


def test_play_and_auto_endpoints(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/playback/play",
        json={"genre_id": sid, "youtube_video_id": "b"},
    )
    assert resp.status_code == 200
    assert client.get("/api/now").json()["source"] == "manual"
    assert client.get("/api/now").json()["track"]["youtube_video_id"] == "b"
    assert client.post("/api/admin/playback/auto").status_code == 200
    assert client.get("/api/now").json()["source"] == "default"


def test_stop_endpoint_takes_station_off_air(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post(
        "/api/admin/playback/play",
        json={"genre_id": sid, "youtube_video_id": "a"},
    )
    assert client.get("/api/now").json()["source"] == "manual"
    assert client.post("/api/admin/playback/stop").status_code == 200
    body = client.get("/api/now").json()
    assert body["source"] == "none"
    assert body["track"] is None
    assert body["genre"] is None
    assert client.post("/api/admin/playback/auto").status_code == 200
    assert client.get("/api/now").json()["source"] == "default"


def test_next_prev_endpoints(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    client.post(
        "/api/admin/playback/play",
        json={"genre_id": sid, "youtube_video_id": "a"},
    )
    client.post("/api/admin/playback/next", json={"genre_id": sid})
    assert client.get("/api/now").json()["track"]["youtube_video_id"] == "b"
    client.post("/api/admin/playback/prev", json={"genre_id": sid})
    assert client.get("/api/now").json()["track"]["youtube_video_id"] == "a"


def test_play_unknown_track_returns_404(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/admin/playback/play",
        json={"genre_id": sid, "youtube_video_id": "nope"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "track not found"


def test_playback_endpoints_require_auth(tmp_path):
    client, engine = _client(tmp_path)
    sid = _seed_genre_with_tracks(engine)
    assert (
        client.post(
            "/api/admin/playback/play",
            json={"genre_id": sid, "youtube_video_id": "a"},
        ).status_code
        == 401
    )
    assert (
        client.post("/api/admin/playback/next", json={"genre_id": sid}).status_code
        == 401
    )
    assert (
        client.post("/api/admin/playback/prev", json={"genre_id": sid}).status_code
        == 401
    )
    assert client.post("/api/admin/playback/auto").status_code == 401
    assert client.post("/api/admin/playback/stop").status_code == 401
    assert (
        client.put(
            f"/api/admin/genres/{sid}/order", json={"video_ids": []}
        ).status_code
        == 401
    )


def test_next_prev_unknown_genre_and_empty_genre(tmp_path):
    client, engine = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    assert (
        client.post("/api/admin/playback/next", json={"genre_id": 999}).status_code
        == 404
    )
    empty = _seed_genre_with_tracks(engine, slug="empty", vids=())
    assert (
        client.post("/api/admin/playback/next", json={"genre_id": empty}).status_code
        == 400
    )
