from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import create_app


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


def _setup(client):
    client.post("/api/studio/login", json={"password": "test-pass"})
    morning = client.post(
        "/api/studio/genres", json={"name": "Morning", "slug": "morning"}
    ).json()["id"]
    evening = client.post(
        "/api/studio/genres", json={"name": "Evening", "slug": "evening"}
    ).json()["id"]
    # Monday — must match the frozen dates used in the tests below, so the
    # suite is deterministic regardless of the real day it runs on.
    day = 0
    first = client.post(
        "/api/studio/slots",
        json={"genre_id": morning, "days_of_week": [day], "start_time": "05:00"},
    ).json()["id"]
    second = client.post(
        "/api/studio/slots",
        json={"genre_id": evening, "days_of_week": [day], "start_time": "17:00"},
    ).json()["id"]
    return first, second


def test_today_lists_todays_slots_sorted_with_current(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    first, second = _setup(client)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 1, 5, 9, 30, tzinfo=tz)

    monkeypatch.setattr("app.routers.schedule.datetime", Frozen)
    body = client.get("/api/schedule/today").json()
    assert body["current_id"] == first
    assert [s["id"] for s in body["slots"]] == [first, second]
    assert body["slots"][0]["genre_name"] == "Morning"
    assert body["slots"][1]["genre_name"] == "Evening"
    assert body["slots"][0]["start_time"] == "05:00"


def test_today_current_null_before_first_start(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _setup(client)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 1, 5, 4, 59, tzinfo=tz)

    monkeypatch.setattr("app.routers.schedule.datetime", Frozen)
    body = client.get("/api/schedule/today").json()
    assert body["current_id"] is None
    assert len(body["slots"]) == 2


def test_today_excludes_other_weekday_slots(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _setup(client)
    client.post("/api/studio/genres", json={"name": "Nomad", "slug": "nomad"})
    nomad = client.get("/api/genres").json()[-1]["id"]
    client.post(
        "/api/studio/slots",
        json={"genre_id": nomad, "days_of_week": [6], "start_time": "12:00"},
    )

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 1, 5, 9, 30, tzinfo=tz)  # Monday

    monkeypatch.setattr("app.routers.schedule.datetime", Frozen)
    body = client.get("/api/schedule/today").json()
    names = {s["genre_name"] for s in body["slots"]}
    assert names == {"Morning", "Evening"}


def test_today_empty_without_slots(tmp_path):
    client, _ = _client(tmp_path)
    body = client.get("/api/schedule/today").json()
    assert body == {"current_id": None, "slots": []}
