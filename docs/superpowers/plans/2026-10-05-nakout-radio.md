# Nakout Radio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dockerized personal internet-radio website that streams the owner's YouTube playlists with an always-on scheduled station, selectable mood stations, a live listener count, and an admin panel.

**Architecture:** A FastAPI backend reads playlist tracks via the YouTube Data API v3 and caches them in SQLite; a React/Vite frontend drives the YouTube IFrame Player for playback and shows a vintage-radio UI. Caddy terminates TLS and routes one origin to the frontend and backend. All services run under Docker Compose on the owner's VPS.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, SQLite, httpx, PyJWT, pytest; React 18, TypeScript, Vite, Vitest, YouTube IFrame Player API; Docker Compose, Caddy, nginx.

**Note on git:** This repository is not yet a git repo. Before executing, run `git init` at the project root, or skip the "Commit" steps until git is initialized.

**Spec:** `docs/superpowers/specs/2026-10-05-nakout-radio-design.md`

---

## File Structure

```
nakout-radio/
├─ backend/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py                 # FastAPI app factory, CORS, router mounts
│  │  ├─ config.py               # pydantic-settings Settings
│  │  ├─ db.py                   # SQLModel engine + session dependency
│  │  ├─ models.py               # Station, Playlist, TrackCache, ScheduleSlot
│  │  ├─ schemas.py              # API request/response models
│  │  ├─ youtube.py              # parse_playlist_id, fetch_playlist_items
│  │  ├─ scheduler.py            # resolve_slot / current station logic
│  │  ├─ auth.py                 # password check + JWT session cookie
│  │  └─ routers/
│  │     ├─ __init__.py
│  │     ├─ stations.py
│  │     ├─ schedule.py
│  │     ├─ admin.py
│  │     └─ ws.py
│  ├─ alembic/                   # migrations (env.py, versions/)
│  ├─ tests/
│  │  ├─ conftest.py
│  │  ├─ test_config.py
│  │  ├─ test_youtube.py
│  │  ├─ test_scheduler.py
│  │  ├─ test_auth.py
│  │  ├─ test_stations.py
│  │  └─ test_ws.py
│  ├─ requirements.txt
│  ├─ requirements-dev.txt
│  ├─ Dockerfile
│  └─ .env.example
├─ frontend/
│  ├─ src/
│  │  ├─ main.tsx
│  │  ├─ App.tsx
│  │  ├─ api/client.ts
│  │  ├─ types.ts
│  │  ├─ hooks/
│  │  │  ├─ useYouTubePlayer.ts
│  │  │  ├─ useSchedule.ts
│  │  │  └─ useListenerCount.ts
│  │  ├─ components/
│  │  │  ├─ RadioPlayer.tsx
│  │  │  ├─ NowPlaying.tsx
│  │  │  ├─ StationDial.tsx
│  │  │  └─ VUMeter.tsx
│  │  ├─ pages/
│  │  │  ├─ RadioPage.tsx
│  │  │  └─ AdminPage.tsx
│  │  ├─ utils/format.ts
│  │  └─ styles/vintage.css
│  ├─ src/test/setup.ts
│  ├─ index.html
│  ├─ vite.config.ts
│  ├─ tsconfig.json
│  ├─ package.json
│  ├─ nginx.conf
│  ├─ Dockerfile
│  └─ .env.example
├─ Caddyfile
├─ docker-compose.yml
└─ README.md
```

---

# Phase A — Backend

## Task 1: Backend scaffold, config, and health endpoint

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_config.py`
- Create: `backend/.env.example`

- [ ] **Step 1: Write dependencies**

`backend/requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlmodel==0.0.22
alembic==1.13.3
httpx==0.27.2
pydantic-settings==2.5.2
PyJWT==2.9.0
```

`backend/requirements-dev.txt`:
```
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_config.py`:
```python
from app.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.station_tz == "Asia/Manila"
    assert s.cache_ttl_minutes == 60
    assert s.database_url.startswith("sqlite")


def test_missing_secret_raises(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("YT_API_KEY", raising=False)
    try:
        Settings(_env_file=None)
    except Exception as exc:
        assert "secret_key" in str(exc).lower() or "admin_password" in str(exc).lower()
    else:
        raise AssertionError("Settings should reject empty required config")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 4: Write config**

`backend/app/__init__.py`:
```python
```

`backend/app/config.py`:
```python
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    yt_api_key: str
    admin_password: str
    secret_key: str
    station_tz: str = "Asia/Manila"
    database_url: str = "sqlite:///./radio.db"
    frontend_origin: str = "http://localhost:5173"
    cache_ttl_minutes: int = 60

    @field_validator("yt_api_key", "admin_password", "secret_key")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("required config value must not be empty")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/.env.example`:
```
YT_API_KEY=your-youtube-data-api-key
ADMIN_PASSWORD=change-me
SECRET_KEY=change-me-to-a-long-random-string
STATION_TZ=Asia/Manila
DATABASE_URL=sqlite:///./radio.db
FRONTEND_ORIGIN=http://localhost:5173
CACHE_TTL_MINUTES=60
```

- [ ] **Step 5: Write the health test and app**

`backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nakout Radio")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

`backend/tests/conftest.py`:
```python
import os

import pytest

os.environ.setdefault("YT_API_KEY", "test-key")
os.environ.setdefault("ADMIN_PASSWORD", "test-pass")
os.environ.setdefault("SECRET_KEY", "test-secret")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())
```

- [ ] **Step 6: Add health test**

`backend/tests/test_config.py` (append):
```python
def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pip install -r requirements-dev.txt && python -m pytest -v`
Expected: 3 passed

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat(backend): scaffold FastAPI app, config, and health endpoint"
```

---

## Task 2: Database models and Alembic setup

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/test_models.py`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_models.py`:
```python
from app.models import ScheduleSlot, Station


def test_station_slug_unique_defaults():
    s = Station(name="Chill", slug="chill")
    assert s.is_default is False
    assert s.sort_order == 0


def test_schedule_slot_stores_days_list():
    slot = ScheduleSlot(
        station_id=1,
        days_of_week=[0, 1, 2, 3, 4],
        start_time="06:00",
        end_time="12:00",
    )
    assert slot.days_of_week == [0, 1, 2, 3, 4]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Write models**

`backend/app/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Station(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    is_default: bool = False
    sort_order: int = 0


class Playlist(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    station_id: int = Field(foreign_key="station.id", index=True)
    youtube_playlist_id: str
    label: str = ""


class TrackCache(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    playlist_id: int = Field(foreign_key="playlist.id", index=True)
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    position: int = 0
    fetched_at: datetime = Field(default_factory=_utcnow)


class ScheduleSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    station_id: int = Field(foreign_key="station.id", index=True)
    days_of_week: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    start_time: str
    end_time: str
```

`backend/app/db.py`:
```python
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()
engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
```

`backend/app/schemas.py`:
```python
from pydantic import BaseModel


class TrackOut(BaseModel):
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str
    duration_seconds: int
    position: int


class StationOut(BaseModel):
    id: int
    name: str
    slug: str
    is_default: bool
    track_count: int


class StationDetail(StationOut):
    tracks: list[TrackOut]


class CurrentStationOut(BaseModel):
    station: StationOut | None
    tracks: list[TrackOut]
    source: str


class SlotIn(BaseModel):
    station_id: int
    days_of_week: list[int]
    start_time: str
    end_time: str


class PlaylistIn(BaseModel):
    station_id: int
    youtube_playlist_url: str
    label: str = ""
```

- [ ] **Step 4: Initialize Alembic**

Run:
```bash
cd backend && alembic init alembic
```
Then edit `backend/alembic/env.py` so the metadata and URL come from the app:
```python
from app.config import get_settings
from app.db import engine
from sqlmodel import SQLModel
import app.models  # noqa: F401  (register tables on metadata)

target_metadata = SQLModel.metadata
config.set_main_option("sqlalchemy.url", get_settings().database_url)
```
And in `run_migrations_online()` use `engine` directly. Set `script_location = alembic` in `alembic.ini`.

- [ ] **Step 5: Generate and apply the first migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "initial schema" && alembic upgrade head
```
Expected: tables `station`, `playlist`, `trackcache`, `scheduleslot` created

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/schemas.py backend/alembic backend/alembic.ini backend/tests/test_models.py
git commit -m "feat(backend): add data models and initial Alembic migration"
```

---

## Task 3: YouTube playlist ID parsing and Data API client

**Files:**
- Create: `backend/app/youtube.py`
- Create: `backend/tests/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_youtube.py`:
```python
import pytest

from app.youtube import fetch_playlist_items, parse_playlist_id


@pytest.mark.parametrize(
    "value,expected",
    [
        ("PL123abc", "PL123abc"),
        ("https://www.youtube.com/playlist?list=PL123abc", "PL123abc"),
        ("https://music.youtube.com/playlist?list=OLAK5uy_xyz&si=1", "OLAK5uy_xyz"),
        ("https://youtu.be/abc?list=PL999", "PL999"),
    ],
)
def test_parse_playlist_id(value, expected):
    assert parse_playlist_id(value) == expected


def test_parse_playlist_id_rejects_empty():
    with pytest.raises(ValueError):
        parse_playlist_id("https://www.youtube.com/watch?v=abc")


def test_fetch_playlist_items_parses_response():
    payload = {
        "items": [
            {
                "snippet": {
                    "title": "Song A",
                    "videoOwnerChannelTitle": "Artist A",
                    "position": 0,
                    "resourceId": {"videoId": "vidA"},
                    "thumbnails": {"high": {"url": "https://img/a.jpg"}},
                },
                "contentDetails": {"videoPublishedAt": "2020-01-01T00:00:00Z"},
            }
        ]
    }

    class FakeClient:
        def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    tracks = fetch_playlist_items("PL1", "key", FakeClient())
    assert tracks[0].youtube_video_id == "vidA"
    assert tracks[0].title == "Song A"
    assert tracks[0].artist == "Artist A"
    assert tracks[0].position == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_youtube.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.youtube'`

- [ ] **Step 3: Write the implementation**

`backend/app/youtube.py`:
```python
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

_API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


@dataclass
class TrackData:
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str
    position: int


def parse_playlist_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("empty playlist reference")
    if "youtube.com" in value or "youtu.be" in value:
        query = parse_qs(urlparse(value).query)
        list_values = query.get("list")
        if not list_values or not list_values[0]:
            raise ValueError("no list= parameter in URL")
        return list_values[0]
    return value


def fetch_playlist_items(
    playlist_id: str, api_key: str, client: httpx.Client
) -> list[TrackData]:
    tracks: list[TrackData] = []
    page_token: str | None = None
    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = client.get(_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            snippet = item["snippet"]
            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                continue
            thumbs = snippet.get("thumbnails", {})
            thumb = (
                thumbs.get("high")
                or thumbs.get("medium")
                or thumbs.get("default")
                or {}
            ).get("url", "")
            tracks.append(
                TrackData(
                    youtube_video_id=video_id,
                    title=snippet.get("title", "Unknown"),
                    artist=snippet.get("videoOwnerChannelTitle", "")
                    or snippet.get("channelTitle", ""),
                    thumbnail_url=thumb,
                    position=snippet.get("position", len(tracks)),
                )
            )
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return tracks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_youtube.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/youtube.py backend/tests/test_youtube.py
git commit -m "feat(backend): add YouTube playlist parsing and data client"
```

---

## Task 4: Time-of-day schedule resolution

**Files:**
- Create: `backend/app/scheduler.py`
- Create: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_scheduler.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from app.scheduler import matches, resolve_station_id

TZ = ZoneInfo("Asia/Manila")


def _dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_matches_simple_window():
    assert matches([0, 1, 2, 3, 4], "06:00", "12:00", _dt(2026, 1, 5, 9)) is True  # Mon
    assert matches([0, 1, 2, 3, 4], "06:00", "12:00", _dt(2026, 1, 5, 13)) is False


def test_matches_rejects_wrong_day():
    assert matches([0, 1, 2, 3, 4], "06:00", "12:00", _dt(2026, 1, 4, 9)) is False  # Sun


def test_matches_overnight_window():
    # 22:00 -> 02:00 crosses midnight; active at 23:00 and 01:00 next day
    assert matches([0], "22:00", "02:00", _dt(2026, 1, 5, 23)) is True
    assert matches([0], "22:00", "02:00", _dt(2026, 1, 6, 1)) is True
    assert matches([0], "22:00", "02:00", _dt(2026, 1, 6, 3)) is False


def test_resolve_picks_matching_slot():
    slots = [
        (1, [0, 1, 2, 3, 4], "06:00", "12:00"),
        (2, [0, 1, 2, 3, 4], "12:00", "18:00"),
    ]
    assert resolve_station_id(slots, _dt(2026, 1, 5, 8), default_id=9) == 1
    assert resolve_station_id(slots, _dt(2026, 1, 5, 15), default_id=9) == 2


def test_resolve_falls_back_to_default():
    slots = [(1, [0], "06:00", "12:00")]
    assert resolve_station_id(slots, _dt(2026, 1, 4, 8), default_id=9) == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scheduler'`

- [ ] **Step 3: Write the implementation**

`backend/app/scheduler.py`:
```python
from datetime import datetime, time

Slot = tuple[int, list[int], str, str]  # station_id, days, start, end


def _to_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def matches(days: list[int], start: str, end: str, now: datetime) -> bool:
    weekday = now.weekday()  # Monday=0
    start_t = _to_time(start)
    end_t = _to_time(end)
    current = now.time()

    if start_t <= end_t:
        return weekday in days and start_t <= current < end_t

    # Overnight window: e.g. 22:00 -> 02:00
    if current >= start_t:
        return weekday in days
    if current < end_t:
        previous_day = (weekday - 1) % 7
        return previous_day in days
    return False


def resolve_station_id(
    slots: list[Slot], now: datetime, default_id: int | None
) -> int | None:
    matching = [s for s in slots if matches(s[1], s[2], s[3], now)]
    if not matching:
        return default_id
    # Latest-starting matching slot wins on overlap.
    matching.sort(key=lambda s: _to_time(s[2]))
    return matching[-1][0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(backend): add time-of-day schedule resolution"
```

---

## Task 5: Admin authentication

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_auth.py`:
```python
from app.auth import create_session_token, verify_password, verify_session_token


def test_verify_password():
    assert verify_password("secret", "secret") is True
    assert verify_password("secret", "wrong") is False


def test_session_token_roundtrip():
    token = create_session_token("secret-key")
    assert verify_session_token(token, "secret-key") is True


def test_session_token_rejects_tampering():
    token = create_session_token("secret-key")
    assert verify_session_token(token + "x", "secret-key") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Write the implementation**

`backend/app/auth.py`:
```python
import hmac
from datetime import datetime, timedelta, timezone

import jwt

_ALGORITHM = "HS256"
_COOKIE_NAME = "nakout_session"
_TTL_HOURS = 24


def verify_password(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate or "", expected or "")


def create_session_token(secret_key: str) -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS),
    }
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def verify_session_token(token: str, secret_key: str) -> bool:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("sub") == "admin"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat(backend): add admin password and session token auth"
```

---

## Task 6: Stations and schedule API routers

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/stations.py`
- Create: `backend/app/routers/schedule.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_stations.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_stations.py`:
```python
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import create_app
from app.models import Playlist, ScheduleSlot, Station, TrackCache


def _seed(session: Session) -> None:
    station = Station(name="Morning", slug="morning", is_default=True)
    session.add(station)
    session.commit()
    session.refresh(station)
    pl = Playlist(station_id=station.id, youtube_playlist_id="PL1")
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


def test_list_stations(tmp_path):
    client = _client_with_db(tmp_path)
    resp = client.get("/api/stations")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["slug"] == "morning"
    assert body[0]["track_count"] == 1


def test_station_detail_includes_tracks(tmp_path):
    client = _client_with_db(tmp_path)
    resp = client.get("/api/stations/morning")
    assert resp.status_code == 200
    assert resp.json()["tracks"][0]["youtube_video_id"] == "vid1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_stations.py -v`
Expected: FAIL with 404 on `/api/stations`

- [ ] **Step 3: Write the routers**

`backend/app/routers/__init__.py`:
```python
```

`backend/app/routers/stations.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Playlist, Station, TrackCache
from app.schemas import StationDetail, StationOut, TrackOut

router = APIRouter(prefix="/api/stations", tags=["stations"])


def _tracks_for_station(session: Session, station_id: int) -> list[TrackCache]:
    playlist_ids = session.exec(
        select(Playlist.id).where(Playlist.station_id == station_id)
    ).all()
    if not playlist_ids:
        return []
    rows = session.exec(
        select(TrackCache)
        .where(TrackCache.playlist_id.in_(playlist_ids))
        .order_by(TrackCache.position)
    ).all()
    return list(rows)


@router.get("", response_model=list[StationOut])
def list_stations(session: Session = Depends(get_session)) -> list[StationOut]:
    stations = session.exec(select(Station).order_by(Station.sort_order)).all()
    return [
        StationOut(
            id=s.id,
            name=s.name,
            slug=s.slug,
            is_default=s.is_default,
            track_count=len(_tracks_for_station(session, s.id)),
        )
        for s in stations
    ]


@router.get("/{slug}", response_model=StationDetail)
def get_station(slug: str, session: Session = Depends(get_session)) -> StationDetail:
    station = session.exec(select(Station).where(Station.slug == slug)).first()
    if station is None:
        raise HTTPException(status_code=404, detail="station not found")
    tracks = _tracks_for_station(session, station.id)
    return StationDetail(
        id=station.id,
        name=station.name,
        slug=station.slug,
        is_default=station.is_default,
        track_count=len(tracks),
        tracks=[
            TrackOut(
                youtube_video_id=t.youtube_video_id,
                title=t.title,
                artist=t.artist,
                thumbnail_url=t.thumbnail_url,
                duration_seconds=t.duration_seconds,
                position=t.position,
            )
            for t in tracks
        ],
    )
```

`backend/app/routers/schedule.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import ScheduleSlot, Station
from app.routers.stations import _tracks_for_station
from app.schemas import CurrentStationOut, StationOut, TrackOut
from app.scheduler import resolve_station_id

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/now", response_model=CurrentStationOut)
def schedule_now(session: Session = Depends(get_session)) -> CurrentStationOut:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.station_tz))

    default_station = session.exec(
        select(Station).where(Station.is_default == True)  # noqa: E712
    ).first()

    slot_rows = session.exec(select(ScheduleSlot)).all()
    slots = [
        (s.station_id, s.days_of_week, s.start_time, s.end_time) for s in slot_rows
    ]
    station_id = resolve_station_id(
        slots, now, default_station.id if default_station else None
    )

    station = session.get(Station, station_id) if station_id else None
    if station is None:
        return CurrentStationOut(station=None, tracks=[], source="none")

    tracks = _tracks_for_station(session, station.id)
    return CurrentStationOut(
        station=StationOut(
            id=station.id,
            name=station.name,
            slug=station.slug,
            is_default=station.is_default,
            track_count=len(tracks),
        ),
        tracks=[
            TrackOut(
                youtube_video_id=t.youtube_video_id,
                title=t.title,
                artist=t.artist,
                thumbnail_url=t.thumbnail_url,
                duration_seconds=t.duration_seconds,
                position=t.position,
            )
            for t in tracks
        ],
        source="schedule",
    )
```

- [ ] **Step 4: Mount routers**

Modify `backend/app/main.py` inside `create_app()` before `return app`:
```python
    from app.routers import schedule, stations

    app.include_router(stations.router)
    app.include_router(schedule.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_stations.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers backend/app/main.py backend/tests/test_stations.py
git commit -m "feat(backend): add stations and schedule endpoints"
```

---

## Task 7: Admin CRUD and playlist sync

**Files:**
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_admin.py`:
```python
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


def test_login_sets_cookie(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/login", json={"password": "test-pass"})
    assert resp.status_code == 200
    assert "nakout_session" in resp.cookies


def test_login_rejects_bad_password(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_create_station_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/stations", json={"name": "Chill", "slug": "chill"})
    assert resp.status_code == 401


def test_create_station_when_authed(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/admin/login", json={"password": "test-pass"})
    resp = client.post("/api/admin/stations", json={"name": "Chill", "slug": "chill"})
    assert resp.status_code == 201
    assert resp.json()["slug"] == "chill"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_admin.py -v`
Expected: FAIL with 404 on admin routes

- [ ] **Step 3: Write the admin router**

`backend/app/routers/admin.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import create_session_token, verify_password, verify_session_token
from app.config import get_settings
from app.db import get_session
from app.models import Playlist, ScheduleSlot, Station, TrackCache
from app.schemas import PlaylistIn, SlotIn

router = APIRouter(prefix="/api/admin", tags=["admin"])
_COOKIE = "nakout_session"


class LoginIn(BaseModel):
    password: str


class StationIn(BaseModel):
    name: str
    slug: str
    is_default: bool = False
    sort_order: int = 0


def require_admin(request: Request) -> None:
    settings = get_settings()
    token = request.cookies.get(_COOKIE, "")
    if not verify_session_token(token, settings.secret_key):
        raise HTTPException(status_code=401, detail="not authenticated")


@router.post("/login")
def login(body: LoginIn, response: Response) -> dict[str, str]:
    settings = get_settings()
    if not verify_password(body.password, settings.admin_password):
        raise HTTPException(status_code=401, detail="invalid password")
    token = create_session_token(settings.secret_key)
    response.set_cookie(
        _COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=86400,
    )
    return {"status": "ok"}


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(_COOKIE)
    return {"status": "ok"}


@router.post("/stations", status_code=201, dependencies=[Depends(require_admin)])
def create_station(body: StationIn, session: Session = Depends(get_session)) -> Station:
    station = Station(**body.model_dump())
    session.add(station)
    session.commit()
    session.refresh(station)
    return station


@router.delete("/stations/{station_id}", dependencies=[Depends(require_admin)])
def delete_station(station_id: int, session: Session = Depends(get_session)) -> dict:
    station = session.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="station not found")
    session.delete(station)
    session.commit()
    return {"status": "deleted"}


@router.post("/playlists", status_code=201, dependencies=[Depends(require_admin)])
def create_playlist(
    body: PlaylistIn, session: Session = Depends(get_session)
) -> dict:
    from app.youtube import parse_playlist_id

    try:
        yt_id = parse_playlist_id(body.youtube_playlist_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    playlist = Playlist(
        station_id=body.station_id, youtube_playlist_id=yt_id, label=body.label
    )
    session.add(playlist)
    session.commit()
    session.refresh(playlist)
    return {"id": playlist.id, "youtube_playlist_id": yt_id}


@router.post("/slots", status_code=201, dependencies=[Depends(require_admin)])
def create_slot(body: SlotIn, session: Session = Depends(get_session)) -> ScheduleSlot:
    slot = ScheduleSlot(**body.model_dump())
    session.add(slot)
    session.commit()
    session.refresh(slot)
    return slot
```

- [ ] **Step 4: Mount the admin router**

Modify `backend/app/main.py` router import block:
```python
    from app.routers import admin, schedule, stations

    app.include_router(stations.router)
    app.include_router(schedule.router)
    app.include_router(admin.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_admin.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/app/main.py backend/tests/test_admin.py
git commit -m "feat(backend): add admin auth and CRUD endpoints"
```

---

## Task 8: Playlist sync job and cache refresh

**Files:**
- Create: `backend/app/sync.py`
- Create: `backend/tests/test_sync.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sync.py`:
```python
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Playlist, Station, TrackCache
from app.sync import sync_playlist
from app.youtube import TrackData


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_sync_replaces_tracks():
    engine = _engine()
    with Session(engine) as s:
        st = Station(name="A", slug="a")
        s.add(st)
        s.commit()
        s.refresh(st)
        pl = Playlist(station_id=st.id, youtube_playlist_id="PL1")
        s.add(pl)
        s.commit()
        s.refresh(pl)

    fetch = lambda pl_id: [
        TrackData("v1", "One", "Art", "u1", 0),
        TrackData("v2", "Two", "Art", "u2", 1),
    ]

    with Session(engine) as s:
        pl = s.exec(select(Playlist)).one()
        sync_playlist(s, pl, fetch)
        rows = s.exec(select(TrackCache).order_by(TrackCache.position)).all()
        assert [r.youtube_video_id for r in rows] == ["v1", "v2"]
        sync_playlist(s, pl, lambda _id: [TrackData("v3", "Three", "Art", "u3", 0)])
        rows = s.exec(select(TrackCache)).all()
        assert [r.youtube_video_id for r in rows] == ["v3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sync'`

- [ ] **Step 3: Write the implementation**

`backend/app/sync.py`:
```python
from collections.abc import Callable

from sqlmodel import Session, delete, select

from app.models import Playlist, TrackCache
from app.youtube import TrackData


def sync_playlist(
    session: Session,
    playlist: Playlist,
    fetch: Callable[[str], list[TrackData]],
) -> int:
    tracks = fetch(playlist.youtube_playlist_id)
    session.exec(delete(TrackCache).where(TrackCache.playlist_id == playlist.id))
    for t in tracks:
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id=t.youtube_video_id,
                title=t.title,
                artist=t.artist,
                thumbnail_url=t.thumbnail_url,
                position=t.position,
            )
        )
    session.commit()
    return len(tracks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/sync.py backend/tests/test_sync.py
git commit -m "feat(backend): add playlist sync with cache replacement"
```

---

## Task 9: WebSocket listener counter

**Files:**
- Create: `backend/app/routers/ws.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_ws.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_ws.py`:
```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_listener_count_increments_and_decrements():
    client = TestClient(create_app())
    with client.websocket_connect("/api/ws/listeners") as ws:
        assert ws.receive_json() == {"count": 1}
    with client.websocket_connect("/api/ws/listeners") as ws:
        assert ws.receive_json() == {"count": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ws.py -v`
Expected: FAIL — WebSocket route not found

- [ ] **Step 3: Write the WebSocket router**

`backend/app/routers/ws.py`:
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/ws", tags=["ws"])

_connections: set[WebSocket] = set()


async def _broadcast() -> None:
    payload = {"count": len(_connections)}
    for ws in list(_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            _connections.discard(ws)


@router.websocket("/listeners")
async def listeners(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    await _broadcast()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        await _broadcast()
```

- [ ] **Step 4: Mount the WebSocket router**

Modify `backend/app/main.py` router import block:
```python
    from app.routers import admin, schedule, stations, ws

    app.include_router(stations.router)
    app.include_router(schedule.router)
    app.include_router(admin.router)
    app.include_router(ws.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_ws.py -v`
Expected: 1 passed

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/ws.py backend/app/main.py backend/tests/test_ws.py
git commit -m "feat(backend): add live listener count websocket"
```

---

# Phase B — Frontend

## Task 10: Frontend scaffold, types, and API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/utils/format.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/utils/format.test.ts`

- [ ] **Step 1: Write package manifest and configs**

`frontend/package.json`:
```json
{
  "name": "nakout-radio-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
```

`frontend/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Nakout Radio</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Write the failing util test**

`frontend/src/utils/format.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { formatDuration, secondsUntilNextMinute } from "./format";

describe("formatDuration", () => {
  it("formats seconds as m:ss", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(3605)).toBe("60:05");
  });
});

describe("secondsUntilNextMinute", () => {
  it("returns seconds to the next minute boundary", () => {
    expect(secondsUntilNextMinute(new Date(2026, 0, 1, 6, 30, 15))).toBe(45);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm install && npm test`
Expected: FAIL — cannot find `./format`

- [ ] **Step 4: Write types, API client, and utils**

`frontend/src/types.ts`:
```ts
export interface Track {
  youtube_video_id: string;
  title: string;
  artist: string;
  thumbnail_url: string;
  duration_seconds: number;
  position: number;
}

export interface Station {
  id: number;
  name: string;
  slug: string;
  is_default: boolean;
  track_count: number;
}

export interface StationDetail extends Station {
  tracks: Track[];
}

export interface CurrentStation {
  station: Station | null;
  tracks: Track[];
  source: string;
}
```

`frontend/src/api/client.ts`:
```ts
import type { CurrentStation, Station, StationDetail } from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    throw new Error(`Request failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export const api = {
  listStations: () => request<Station[]>("/stations"),
  getStation: (slug: string) => request<StationDetail>(`/stations/${slug}`),
  scheduleNow: () => request<CurrentStation>("/schedule/now"),
  login: (password: string) =>
    request<{ status: string }>("/admin/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  createStation: (name: string, slug: string) =>
    request<Station>("/admin/stations", {
      method: "POST",
      body: JSON.stringify({ name, slug }),
    }),
  createPlaylist: (stationId: number, url: string, label: string) =>
    request<unknown>("/admin/playlists", {
      method: "POST",
      body: JSON.stringify({
        station_id: stationId,
        youtube_playlist_url: url,
        label,
      }),
    }),
  createSlot: (slot: {
    station_id: number;
    days_of_week: number[];
    start_time: string;
    end_time: string;
  }) =>
    request<unknown>("/admin/slots", {
      method: "POST",
      body: JSON.stringify(slot),
    }),
};
```

`frontend/src/utils/format.ts`:
```ts
export function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function secondsUntilNextMinute(now: Date): number {
  return 60 - now.getSeconds();
}
```

`frontend/src/test/setup.ts`:
```ts
import "@testing-library/jest-dom";
```

`frontend/src/App.tsx`:
```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AdminPage } from "./pages/AdminPage";
import { RadioPage } from "./pages/RadioPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RadioPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

`frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles/vintage.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: 2 passed (create empty placeholder page files first, see Task 11)

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/src
git commit -m "feat(frontend): scaffold Vite React app with API client and utils"
```

---

## Task 11: YouTube player hook

**Files:**
- Create: `frontend/src/hooks/useYouTubePlayer.ts`
- Create: `frontend/src/hooks/useYouTubePlayer.test.ts`
- Create: `frontend/src/pages/RadioPage.tsx` (placeholder)
- Create: `frontend/src/pages/AdminPage.tsx` (placeholder)

- [ ] **Step 1: Write the failing test (pure helpers)**

`frontend/src/hooks/useYouTubePlayer.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { nextIndex, prevIndex } from "./useYouTubePlayer";

describe("queue navigation", () => {
  it("wraps forward", () => {
    expect(nextIndex(0, 3)).toBe(1);
    expect(nextIndex(2, 3)).toBe(0);
  });
  it("wraps backward", () => {
    expect(prevIndex(0, 3)).toBe(2);
  });
  it("handles empty", () => {
    expect(nextIndex(0, 0)).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — cannot find `nextIndex`

- [ ] **Step 3: Write the hook**

`frontend/src/hooks/useYouTubePlayer.ts`:
```ts
import { useCallback, useEffect, useRef, useState } from "react";
import type { Track } from "../types";

export function nextIndex(current: number, length: number): number {
  if (length <= 0) return 0;
  return (current + 1) % length;
}

export function prevIndex(current: number, length: number): number {
  if (length <= 0) return 0;
  return (current - 1 + length) % length;
}

interface PlayerState {
  ready: boolean;
  playing: boolean;
  index: number;
  progress: number;
}

declare global {
  interface Window {
    YT?: any;
    onYouTubeIframeAPIReady?: () => void;
  }
}

function loadIframeApi(): Promise<void> {
  if (window.YT && window.YT.Player) return Promise.resolve();
  return new Promise((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.body.appendChild(script);
  });
}

export function useYouTubePlayer(tracks: Track[], containerId: string) {
  const playerRef = useRef<any>(null);
  const tracksRef = useRef<Track[]>(tracks);
  const [state, setState] = useState<PlayerState>({
    ready: false,
    playing: false,
    index: 0,
    progress: 0,
  });

  tracksRef.current = tracks;

  useEffect(() => {
    let cancelled = false;
    loadIframeApi().then(() => {
      if (cancelled || !window.YT) return;
      const first = tracksRef.current[0];
      if (!first) return;
      playerRef.current = new window.YT.Player(containerId, {
        height: "1",
        width: "1",
        videoId: first.youtube_video_id,
        playerVars: { controls: 0, disablekb: 1, playsinline: 1 },
        events: {
          onReady: () => setState((s) => ({ ...s, ready: true })),
          onStateChange: (e: any) => {
            const playing = e.data === window.YT.PlayerState.PLAYING;
            setState((s) => ({ ...s, playing }));
            if (e.data === window.YT.PlayerState.ENDED) {
              playIndex(nextIndex(state.index, tracksRef.current.length));
            }
          },
          onError: () => {
            playIndex(nextIndex(state.index, tracksRef.current.length));
          },
        },
      });
    });
    return () => {
      cancelled = true;
      playerRef.current?.destroy?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerId]);

  const playIndex = useCallback((index: number) => {
    const track = tracksRef.current[index];
    if (!track || !playerRef.current) return;
    setState((s) => ({ ...s, index }));
    playerRef.current.loadVideoById(track.youtube_video_id);
  }, []);

  const tuneIn = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    if (player.getPlayerState?.() === window.YT?.PlayerState?.PLAYING) {
      player.pauseVideo();
    } else {
      player.unMute();
      player.playVideo();
    }
  }, []);

  const next = useCallback(
    () => playIndex(nextIndex(state.index, tracksRef.current.length)),
    [playIndex, state.index],
  );
  const prev = useCallback(
    () => playIndex(prevIndex(state.index, tracksRef.current.length)),
    [playIndex, state.index],
  );

  useEffect(() => {
    const timer = setInterval(() => {
      const player = playerRef.current;
      if (player?.getCurrentTime) {
        setState((s) => ({ ...s, progress: player.getCurrentTime() }));
      }
    }, 500);
    return () => clearInterval(timer);
  }, []);

  return { ...state, tuneIn, next, prev, playIndex };
}
```

- [ ] **Step 4: Add placeholder pages so the app compiles**

`frontend/src/pages/RadioPage.tsx`:
```tsx
export function RadioPage() {
  return <div>Radio</div>;
}
```

`frontend/src/pages/AdminPage.tsx`:
```tsx
export function AdminPage() {
  return <div>Admin</div>;
}
```

- [ ] **Step 5: Run tests and typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: tests pass, no type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useYouTubePlayer.ts frontend/src/hooks/useYouTubePlayer.test.ts frontend/src/pages
git commit -m "feat(frontend): add YouTube player hook with queue navigation"
```

---

## Task 12: Schedule and listener hooks

**Files:**
- Create: `frontend/src/hooks/useSchedule.ts`
- Create: `frontend/src/hooks/useListenerCount.ts`
- Create: `frontend/src/hooks/useListenerCount.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/hooks/useListenerCount.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { listenerSocketUrl } from "./useListenerCount";

describe("listenerSocketUrl", () => {
  it("uses ws scheme on http", () => {
    expect(listenerSocketUrl("http:", "example.com")).toBe(
      "ws://example.com/api/ws/listeners",
    );
  });
  it("uses wss scheme on https", () => {
    expect(listenerSocketUrl("https:", "example.com")).toBe(
      "wss://example.com/api/ws/listeners",
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — cannot find `listenerSocketUrl`

- [ ] **Step 3: Write the hooks**

`frontend/src/hooks/useListenerCount.ts`:
```ts
import { useEffect, useState } from "react";

export function listenerSocketUrl(protocol: string, host: string): string {
  const scheme = protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${host}/api/ws/listeners`;
}

export function useListenerCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const url = listenerSocketUrl(location.protocol, location.host);
    let socket: WebSocket | null = new WebSocket(url);
    let closed = false;

    const connect = () => {
      socket = new WebSocket(url);
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as { count: number };
          setCount(data.count);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        if (!closed) setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      closed = true;
      socket?.close();
    };
  }, []);

  return count;
}
```

`frontend/src/hooks/useSchedule.ts`:
```ts
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { secondsUntilNextMinute } from "../utils/format";
import type { CurrentStation } from "../types";

export function useSchedule(): CurrentStation | null {
  const [current, setCurrent] = useState<CurrentStation | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const data = await api.scheduleNow();
        if (!cancelled) setCurrent(data);
      } catch {
        if (!cancelled) setCurrent((prev) => prev ?? { station: null, tracks: [], source: "error" });
      }
    };

    const scheduleNext = () => {
      const delay = secondsUntilNextMinute(new Date()) * 1000;
      timerRef.current = window.setTimeout(async () => {
        await refresh();
        scheduleNext();
      }, delay);
    };

    refresh();
    scheduleNext();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return current;
}
```

- [ ] **Step 4: Run tests and typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSchedule.ts frontend/src/hooks/useListenerCount.ts frontend/src/hooks/useListenerCount.test.ts
git commit -m "feat(frontend): add schedule polling and listener count hooks"
```

---

## Task 13: Now Playing, VU meter, and station dial components

**Files:**
- Create: `frontend/src/components/NowPlaying.tsx`
- Create: `frontend/src/components/VUMeter.tsx`
- Create: `frontend/src/components/StationDial.tsx`

- [ ] **Step 1: Write NowPlaying**

`frontend/src/components/NowPlaying.tsx`:
```tsx
import type { Track } from "../types";

interface Props {
  track: Track | null;
  progress: number;
}

export function NowPlaying({ track, progress }: Props) {
  if (!track) {
    return <div className="now-playing empty">Station off air</div>;
  }
  const pct =
    track.duration_seconds > 0
      ? Math.min(100, (progress / track.duration_seconds) * 100)
      : 0;
  return (
    <div className="now-playing">
      {track.thumbnail_url && (
        <img className="art" src={track.thumbnail_url} alt="" />
      )}
      <div className="meta">
        <div className="title">{track.title}</div>
        <div className="artist">{track.artist}</div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write VUMeter**

`frontend/src/components/VUMeter.tsx`:
```tsx
interface Props {
  playing: boolean;
  seed: number;
}

export function VUMeter({ playing, seed }: Props) {
  const bars = Array.from({ length: 12 }, (_, i) => {
    const base = playing ? 40 + ((seed + i * 7) % 60) : 6;
    return Math.min(100, base);
  });
  return (
    <div className="vu-meter" aria-hidden="true">
      {bars.map((height, i) => (
        <div
          key={i}
          className="vu-bar"
          style={{ height: `${height}%` }}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Write StationDial**

`frontend/src/components/StationDial.tsx`:
```tsx
import type { Station } from "../types";

interface Props {
  stations: Station[];
  activeSlug: string | null;
  onSelect: (slug: string) => void;
}

export function StationDial({ stations, activeSlug, onSelect }: Props) {
  const activeIndex = Math.max(
    0,
    stations.findIndex((s) => s.slug === activeSlug),
  );
  const angle = stations.length
    ? -120 + (240 / Math.max(1, stations.length - 1)) * activeIndex
    : -120;

  return (
    <div className="station-dial">
      <div className="knob" style={{ transform: `rotate(${angle}deg)` }}>
        <div className="knob-indicator" />
      </div>
      <ul className="station-list">
        {stations.map((s) => (
          <li key={s.slug}>
            <button
              type="button"
              className={s.slug === activeSlug ? "active" : ""}
              onClick={() => onSelect(s.slug)}
            >
              {s.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components
git commit -m "feat(frontend): add now playing, VU meter, and station dial components"
```

---

## Task 14: Radio page wiring and vintage styling

**Files:**
- Modify: `frontend/src/pages/RadioPage.tsx`
- Create: `frontend/src/styles/vintage.css`

- [ ] **Step 1: Write the Radio page**

`frontend/src/pages/RadioPage.tsx`:
```tsx
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { NowPlaying } from "../components/NowPlaying";
import { StationDial } from "../components/StationDial";
import { VUMeter } from "../components/VUMeter";
import { useListenerCount } from "../hooks/useListenerCount";
import { useSchedule } from "../hooks/useSchedule";
import { useYouTubePlayer } from "../hooks/useYouTubePlayer";
import type { Station } from "../types";

export function RadioPage() {
  const current = useSchedule();
  const listeners = useListenerCount();
  const [stations, setStations] = useState<Station[]>([]);
  const [overrideSlug, setOverrideSlug] = useState<string | null>(null);

  useEffect(() => {
    api.listStations().then(setStations).catch(() => setStations([]));
  }, []);

  const activeSlug = overrideSlug ?? current?.station?.slug ?? null;
  const tracks = current?.tracks ?? [];
  const player = useYouTubePlayer(tracks, "yt-player");
  const activeTrack = tracks[player.index] ?? null;

  const tunedLabel = useMemo(() => {
    const station = stations.find((s) => s.slug === activeSlug);
    return station?.name ?? current?.station?.name ?? "—";
  }, [stations, activeSlug, current]);

  return (
    <div className="radio-cabinet">
      <header className="radio-header">
        <h1>Nakout Radio</h1>
        <span className="listeners">{listeners} listening</span>
      </header>

      <div id="yt-player" className="hidden-player" />

      <NowPlaying track={activeTrack} progress={player.progress} />
      <VUMeter playing={player.playing} seed={player.index} />

      <div className="station-row">
        <span className="tuned-label">Tuned: {tunedLabel}</span>
        <StationDial
          stations={stations}
          activeSlug={activeSlug}
          onSelect={setOverrideSlug}
        />
      </div>

      <div className="controls">
        {!player.playing ? (
          <button type="button" className="tune-in" onClick={player.tuneIn}>
            TUNE IN
          </button>
        ) : (
          <button type="button" className="tune-in" onClick={player.tuneIn}>
            PAUSE
          </button>
        )}
        <button type="button" onClick={player.prev}>
          ⟨ PREV
        </button>
        <button type="button" onClick={player.next}>
          NEXT ⟩
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write the vintage stylesheet**

`frontend/src/styles/vintage.css`:
```css
:root {
  --wood: #3b2417;
  --wood-light: #6b4630;
  --cream: #efe3c8;
  --amber: #ffb347;
  --ink: #2a1a10;
}

body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: radial-gradient(circle at 50% 20%, #4a2e1e, #1c110a 70%);
  font-family: "Courier New", monospace;
  color: var(--ink);
}

.radio-cabinet {
  width: min(560px, 92vw);
  padding: 28px;
  border-radius: 22px;
  background: linear-gradient(160deg, var(--wood-light), var(--wood));
  box-shadow: inset 0 2px 0 rgba(255, 255, 255, 0.15),
    0 30px 60px rgba(0, 0, 0, 0.6);
  border: 6px solid #241408;
}

.radio-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  color: var(--cream);
}

.radio-header h1 {
  font-size: 1.4rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.listeners {
  color: var(--amber);
}

.hidden-player {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
}

.now-playing {
  display: flex;
  gap: 16px;
  margin: 18px 0;
  padding: 16px;
  border-radius: 12px;
  background: var(--cream);
  box-shadow: inset 0 0 20px rgba(59, 36, 23, 0.35);
}

.now-playing .art {
  width: 96px;
  height: 96px;
  border-radius: 8px;
  object-fit: cover;
}

.now-playing .title {
  font-weight: bold;
  font-size: 1.1rem;
}

.now-playing .artist {
  opacity: 0.7;
  margin-bottom: 10px;
}

.progress-track {
  height: 8px;
  border-radius: 4px;
  background: rgba(59, 36, 23, 0.2);
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  background: var(--amber);
  transition: width 0.4s linear;
}

.vu-meter {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 56px;
  padding: 8px;
  border-radius: 8px;
  background: #120b06;
}

.vu-bar {
  flex: 1;
  background: linear-gradient(var(--amber), #ff6a00);
  border-radius: 2px;
  transition: height 0.12s ease-out;
}

.station-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 18px 0;
  color: var(--cream);
}

.station-dial {
  display: flex;
  align-items: center;
  gap: 14px;
}

.knob {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #d9c9a8, #7a5a3a);
  border: 4px solid #241408;
  position: relative;
  transition: transform 0.3s ease;
}

.knob-indicator {
  position: absolute;
  top: 4px;
  left: 50%;
  width: 3px;
  height: 14px;
  background: var(--ink);
  transform: translateX(-50%);
}

.station-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.station-list button {
  cursor: pointer;
  border: none;
  border-radius: 999px;
  padding: 6px 12px;
  background: rgba(0, 0, 0, 0.3);
  color: var(--cream);
  font-family: inherit;
}

.station-list button.active {
  background: var(--amber);
  color: var(--ink);
}

.controls {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.controls button {
  cursor: pointer;
  font-family: inherit;
  border-radius: 8px;
  border: 2px solid #241408;
  padding: 10px 18px;
  background: var(--cream);
  color: var(--ink);
}

.tune-in {
  background: var(--amber) !important;
  font-weight: bold;
  letter-spacing: 0.15em;
}
```

- [ ] **Step 3: Typecheck and build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/RadioPage.tsx frontend/src/styles/vintage.css
git commit -m "feat(frontend): wire radio page and add vintage styling"
```

---

## Task 15: Admin page

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`

- [ ] **Step 1: Write the admin page**

`frontend/src/pages/AdminPage.tsx`:
```tsx
import { useState } from "react";
import { api } from "../api/client";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function AdminPage() {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState("");
  const [stationName, setStationName] = useState("");
  const [stationSlug, setStationSlug] = useState("");
  const [stationId, setStationId] = useState("");
  const [playlistUrl, setPlaylistUrl] = useState("");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [start, setStart] = useState("06:00");
  const [end, setEnd] = useState("12:00");

  const login = async () => {
    try {
      await api.login(password);
      setAuthed(true);
      setError("");
    } catch {
      setError("Invalid password");
    }
  };

  const addStation = async () => {
    try {
      const s = await api.createStation(stationName, stationSlug);
      setStationId(String(s.id));
      setError("");
    } catch {
      setError("Could not create station");
    }
  };

  const addPlaylist = async () => {
    try {
      await api.createPlaylist(Number(stationId), playlistUrl, "");
      setPlaylistUrl("");
    } catch {
      setError("Could not add playlist");
    }
  };

  const addSlot = async () => {
    try {
      await api.createSlot({
        station_id: Number(stationId),
        days_of_week: days,
        start_time: start,
        end_time: end,
      });
    } catch {
      setError("Could not add slot");
    }
  };

  const toggleDay = (day: number) => {
    setDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  };

  if (!authed) {
    return (
      <div className="admin">
        <h1>Admin</h1>
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="button" onClick={login}>
          Log in
        </button>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  return (
    <div className="admin">
      <h1>Admin</h1>
      {error && <p className="error">{error}</p>}

      <section>
        <h2>Station</h2>
        <input
          placeholder="Name"
          value={stationName}
          onChange={(e) => setStationName(e.target.value)}
        />
        <input
          placeholder="Slug"
          value={stationSlug}
          onChange={(e) => setStationSlug(e.target.value)}
        />
        <button type="button" onClick={addStation}>
          Add station
        </button>
        {stationId && <p>Station ID: {stationId}</p>}
      </section>

      <section>
        <h2>Playlist</h2>
        <input
          placeholder="YouTube playlist URL"
          value={playlistUrl}
          onChange={(e) => setPlaylistUrl(e.target.value)}
        />
        <button type="button" onClick={addPlaylist}>
          Add playlist
        </button>
      </section>

      <section>
        <h2>Schedule slot</h2>
        <div className="days">
          {DAY_LABELS.map((label, i) => (
            <button
              type="button"
              key={label}
              className={days.includes(i) ? "active" : ""}
              onClick={() => toggleDay(i)}
            >
              {label}
            </button>
          ))}
        </div>
        <input value={start} onChange={(e) => setStart(e.target.value)} />
        <input value={end} onChange={(e) => setEnd(e.target.value)} />
        <button type="button" onClick={addSlot}>
          Add slot
        </button>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck and build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx
git commit -m "feat(frontend): add admin page for stations, playlists, and slots"
```

---

# Phase C — Packaging and Deployment

## Task 16: Backend Dockerfile

**Files:**
- Create: `backend/entrypoint.sh`
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

- [ ] **Step 1: Write the entrypoint**

`backend/entrypoint.sh`:
```sh
#!/bin/sh
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Write the Dockerfile**

`backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000
CMD ["./entrypoint.sh"]
```

`backend/.dockerignore`:
```
__pycache__
*.pyc
.env
radio.db
.pytest_cache
tests
```

- [ ] **Step 3: Build the image to verify**

Run: `docker build -t nakout-backend ./backend`
Expected: image builds successfully

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/entrypoint.sh backend/.dockerignore
git commit -m "build(backend): add Dockerfile and entrypoint"
```

---

## Task 17: Frontend Dockerfile and nginx

**Files:**
- Create: `frontend/nginx.conf`
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`

- [ ] **Step 1: Write the nginx config**

`frontend/nginx.conf`:
```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Write the Dockerfile**

`frontend/Dockerfile`:
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

`frontend/.dockerignore`:
```
node_modules
dist
.env
```

- [ ] **Step 3: Build the image to verify**

Run: `docker build -t nakout-frontend ./frontend`
Expected: image builds successfully

- [ ] **Step 4: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore
git commit -m "build(frontend): add Dockerfile and nginx config"
```

---

## Task 18: Caddy and Docker Compose

**Files:**
- Create: `Caddyfile`
- Create: `docker-compose.yml`
- Modify: `backend/.env.example` (document volume path)
- Create: `.env.example` at project root

- [ ] **Step 1: Write the Caddyfile**

`Caddyfile`:
```
{$DOMAIN} {
    encode gzip

    @backend path /api/* /api
    handle @backend {
        reverse_proxy backend:8000
    }

    handle {
        reverse_proxy frontend:80
    }
}
```

- [ ] **Step 2: Write docker-compose.yml**

`docker-compose.yml`:
```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    environment:
      DOMAIN: ${DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
      - frontend

  backend:
    build: ./backend
    restart: unless-stopped
    env_file: ./backend/.env
    volumes:
      - radio_data:/data
    environment:
      DATABASE_URL: sqlite:////data/radio.db

  frontend:
    build: ./frontend
    restart: unless-stopped

volumes:
  radio_data:
  caddy_data:
  caddy_config:
```

- [ ] **Step 3: Write root env example**

`.env.example`:
```
DOMAIN=radio.example.com
```
Also create `backend/.env` on the server from `backend/.env.example` (never committed), and set `FRONTEND_ORIGIN=https://radio.example.com`.

- [ ] **Step 4: Validate the compose file**

Run: `docker compose config`
Expected: valid configuration printed, no errors

- [ ] **Step 5: Build all images**

Run: `docker compose build`
Expected: all three images build

- [ ] **Step 6: Commit**

```bash
git add Caddyfile docker-compose.yml .env.example
git commit -m "build: add Caddy reverse proxy and docker-compose stack"
```

---

## Task 19: README and run instructions

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

`README.md`:
```markdown
# Nakout Radio

A personal internet-radio website streaming the owner's YouTube playlists,
with an always-on scheduled station, mood stations, a live listener count,
and an admin panel.

## Architecture

- `backend/` — FastAPI + SQLite. Reads playlist tracks via the YouTube Data
  API v3 and caches them. Serves stations, schedule, admin, and a listener
  websocket.
- `frontend/` — React + Vite. Drives the YouTube IFrame Player and renders the
  vintage-radio UI.
- `caddy` — TLS termination and routing: `/` to frontend, `/api` and `/ws` to
  backend.

## Local development

### Backend
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # fill in values
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Required configuration

| Variable | Purpose |
| --- | --- |
| `YT_API_KEY` | YouTube Data API v3 key |
| `ADMIN_PASSWORD` | Admin login password |
| `SECRET_KEY` | Session signing key |
| `STATION_TZ` | Schedule timezone, e.g. `Asia/Manila` |
| `DATABASE_URL` | SQLite path |
| `FRONTEND_ORIGIN` | Allowed CORS origin |
| `CACHE_TTL_MINUTES` | Track cache freshness window |
| `DOMAIN` | Public domain for Caddy/TLS |

## Production deploy

1. Point your domain's DNS at the VPS.
2. Create `backend/.env` from `backend/.env.example` and a root `.env` with `DOMAIN`.
3. Run `docker compose up -d --build`.
4. Caddy obtains TLS certificates automatically.
5. Visit `/admin`, log in, add stations, playlists, and schedule slots.

Data is stored in the `radio_data` Docker volume; include it in backups.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and deploy instructions"
```

---

## Self-Review

**Spec coverage check:**

- Hybrid Data API + IFrame playback → Tasks 3, 8, 11 ✓
- FastAPI backend → Tasks 1–9 ✓
- React + Vite frontend → Tasks 10–15 ✓
- SQLite via SQLModel + Alembic → Tasks 2 ✓
- Single-password admin session → Tasks 5, 7, 15 ✓
- Fixed-timezone schedule → Tasks 4, 6, 12 ✓
- In-memory WebSocket listener count → Tasks 9, 12 ✓
- Vintage radio UI + TUNE IN → Tasks 11, 13, 14 ✓
- Docker Compose with caddy/frontend/backend → Tasks 16–18 ✓
- Error handling (stale cache, skip on error, disconnect cleanup, 401) → Tasks 3 (raise_for_status), 8 (cache), 11 (onError skip), 9 (finally), 7 (401) ✓

**Placeholder scan:** No TBD/TODO steps; every code step contains complete code.

**Type consistency:** `TrackOut`/`StationOut`/`StationDetail` in `schemas.py` match the TypeScript `Track`/`Station`/`StationDetail` in `types.ts`. `nextIndex`/`prevIndex` defined once and reused. `listenerSocketUrl` name consistent across implementation and test.

**Known gaps intentionally deferred (post-v1):** queue/history views, track requests, Redis, Postgres migration.
