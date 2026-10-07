# Browse Channel Playlists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin save a YouTube channel once and browse/add its public playlists directly from the admin page.

**Architecture:** Backend adds a `Setting` key/value table, two pure YouTube Data API helpers (`resolve_channel_id`, `fetch_channel_playlists`), and three authenticated admin endpoints. The React admin page adds a "Browse YouTube playlists" section that saves a channel, lists its public playlists, and adds a chosen one to a station through the existing playlist-sync endpoint.

**Tech Stack:** FastAPI + SQLModel + Alembic + httpx (backend); React + TypeScript + Vite + Vitest + Testing Library (frontend).

**Working directory:** Backend `python`/`pytest`/`alembic` commands run from `backend/`. `npm`/`vitest` commands run from `frontend/`. `docker compose` commands run from the repository root.

**Version control note:** This workspace is **not** a git repository. Each "Commit" step is a checkpoint: if you have not run `git init`, skip the git commands and just confirm the tests pass. If you do initialize git, run the commands as written.

---

## File Structure

- `backend/app/models.py` — add the `Setting` table.
- `backend/alembic/versions/<new>_add_setting_table.py` — migration.
- `backend/app/youtube.py` — add `PlaylistData`, `resolve_channel_id`, `fetch_channel_playlists`.
- `backend/app/schemas.py` — add `ChannelIn`, `ChannelOut`, `ChannelPlaylistOut`.
- `backend/app/routers/admin.py` — add channel/playlist endpoints + helpers.
- `backend/tests/test_models.py` — `Setting` round-trip test.
- `backend/tests/test_youtube.py` — channel parse + playlist fetch tests.
- `backend/tests/test_admin.py` — endpoint tests.
- `frontend/src/types.ts` — `ChannelSource`, `ChannelPlaylist`.
- `frontend/src/api/client.ts` — three new methods.
- `frontend/src/api/client.test.ts` — client tests.
- `frontend/src/pages/AdminPage.tsx` — new section.
- `frontend/src/pages/AdminPage.dom.test.tsx` — DOM tests (and mock additions so existing tests keep working).

---

## Task 1: `Setting` model and migration

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/b2f4c1a9d3e7_add_setting_table.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_models.py`. Update the import line at the top to include `Setting`:

```python
from app.models import Playlist, ScheduleSlot, Setting, Station, TrackCache
```

Append this test at the end of the file:

```python
def test_setting_round_trip(session):
    session.add(Setting(key="youtube_channel_id", value="UC123"))
    session.commit()
    loaded = session.get(Setting, "youtube_channel_id")
    assert loaded is not None
    assert loaded.value == "UC123"


def test_setting_value_can_be_updated(session):
    session.add(Setting(key="youtube_channel_title", value="Old"))
    session.commit()
    row = session.get(Setting, "youtube_channel_title")
    row.value = "New"
    session.add(row)
    session.commit()
    assert session.get(Setting, "youtube_channel_title").value == "New"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_models.py::test_setting_round_trip -v`
Expected: FAIL with `ImportError` / `cannot import name 'Setting'`.

- [ ] **Step 3: Add the model**

Append to `backend/app/models.py`:

```python
class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Create the migration**

Create `backend/alembic/versions/b2f4c1a9d3e7_add_setting_table.py` (adjust the revision id if you prefer, but keep `down_revision` pointing at the initial migration):

```python
"""add setting table

Revision ID: b2f4c1a9d3e7
Revises: 63cf14ae878f
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b2f4c1a9d3e7'
down_revision: Union[str, None] = '63cf14ae878f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'setting',
        sa.Column('key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('value', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('setting')
```

- [ ] **Step 6: Apply the migration**

Run (from `backend/`): `alembic upgrade head`
Expected: no error; the `setting` table is created in the configured database. Verify:
`python -c "import sqlite3; print([r[0] for r in sqlite3.connect('radio.db').execute(\"select name from sqlite_master where type='table'\")])"`
Expected: output includes `'setting'`.

- [ ] **Step 7: Commit (checkpoint)**

```bash
git add backend/app/models.py backend/alembic/versions/b2f4c1a9d3e7_add_setting_table.py backend/tests/test_models.py
git commit -m "feat: add Setting key/value table"
```

---

## Task 2: `resolve_channel_id` in youtube.py

**Files:**
- Modify: `backend/app/youtube.py`
- Test: `backend/tests/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_youtube.py`. Update the import at the top to:

```python
from app.youtube import (
    fetch_playlist_items,
    parse_playlist_id,
    resolve_channel_id,
)
```

Add:

```python
class _ChannelClient:
    def __init__(self, payload):
        self.payload = payload
        self.seen_params = None

    def get(self, url, params=None):
        self.seen_params = params
        payload = self.payload

        class R:
            def raise_for_status(self):
                return None

            def json(self_inner):
                return payload

        return R()


@pytest.mark.parametrize(
    "value,param_key,param_value",
    [
        ("UCabc123", "id", "UCabc123"),
        ("@somehandle", "forHandle", "@somehandle"),
        ("https://www.youtube.com/@somehandle", "forHandle", "@somehandle"),
        ("https://www.youtube.com/channel/UCxyz", "id", "UCxyz"),
        ("https://www.youtube.com/user/legacyuser", "forUsername", "legacyuser"),
    ],
)
def test_resolve_channel_id_lookup_param(value, param_key, param_value):
    payload = {"items": [{"id": "UCresolved", "snippet": {"title": "My Channel"}}]}
    client = _ChannelClient(payload)
    channel_id, title = resolve_channel_id(value, "key", client)
    assert channel_id == "UCresolved"
    assert title == "My Channel"
    assert client.seen_params[param_key] == param_value


def test_resolve_channel_id_empty_raises():
    with pytest.raises(ValueError):
        resolve_channel_id("   ", "key", _ChannelClient({"items": []}))


def test_resolve_channel_id_not_found_raises():
    with pytest.raises(ValueError):
        resolve_channel_id("UCnope", "key", _ChannelClient({"items": []}))


def test_resolve_channel_id_rejects_non_youtube_url():
    with pytest.raises(ValueError):
        resolve_channel_id("https://example.com/@foo", "key", _ChannelClient({"items": []}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_youtube.py -v -k resolve_channel_id`
Expected: FAIL with `ImportError: cannot import name 'resolve_channel_id'`.

- [ ] **Step 3: Implement**

Add to `backend/app/youtube.py` (below `_API_URL`):

```python
_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


def _channel_lookup_param(value: str) -> dict[str, str]:
    value = (value or "").strip()
    if not value:
        raise ValueError("empty channel reference")
    if value.startswith("UC"):
        return {"id": value}
    if value.startswith("@"):
        return {"forHandle": value}
    if not (
        "://" in value
        or value.startswith("youtube.com")
        or value.startswith("www.youtube.com")
        or value.startswith("music.youtube.com")
    ):
        return {"id": value}
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.hostname or ""
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        raise ValueError("not a YouTube channel URL")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("no channel in URL")
    if parts[0].startswith("@"):
        return {"forHandle": parts[0]}
    if len(parts) >= 2 and parts[0] == "channel":
        return {"id": parts[1]}
    if len(parts) >= 2 and parts[0] == "user":
        return {"forUsername": parts[1]}
    raise ValueError("unsupported channel URL")


def resolve_channel_id(
    value: str, api_key: str, client: httpx.Client
) -> tuple[str, str]:
    params = {"part": "snippet", "key": api_key, **_channel_lookup_param(value)}
    resp = client.get(_CHANNELS_URL, params=params)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError("channel not found")
    item = items[0]
    return item["id"], item.get("snippet", {}).get("title", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_youtube.py -v -k resolve_channel_id`
Expected: all PASS.

- [ ] **Step 5: Commit (checkpoint)**

```bash
git add backend/app/youtube.py backend/tests/test_youtube.py
git commit -m "feat: resolve YouTube channel id from id/handle/url"
```

---

## Task 3: `fetch_channel_playlists` in youtube.py

**Files:**
- Modify: `backend/app/youtube.py`
- Test: `backend/tests/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

Update the `app.youtube` import in `backend/tests/test_youtube.py` to also import `fetch_channel_playlists` and `PlaylistData`:

```python
from app.youtube import (
    PlaylistData,
    fetch_channel_playlists,
    fetch_playlist_items,
    parse_playlist_id,
    resolve_channel_id,
)
```

Append:

```python
def test_fetch_channel_playlists_parses_response():
    payload = {
        "items": [
            {
                "id": "PLaaa",
                "snippet": {
                    "title": "Chill Mix",
                    "thumbnails": {"high": {"url": "https://img/a.jpg"}},
                },
                "contentDetails": {"itemCount": 12},
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

    result = fetch_channel_playlists("UC1", "key", FakeClient())
    assert result == [
        PlaylistData(
            youtube_playlist_id="PLaaa",
            title="Chill Mix",
            item_count=12,
            thumbnail_url="https://img/a.jpg",
        )
    ]


def test_fetch_channel_playlists_follows_pagination():
    page1 = {
        "items": [
            {
                "id": "PL1",
                "snippet": {"title": "One", "thumbnails": {}},
                "contentDetails": {"itemCount": 1},
            }
        ],
        "nextPageToken": "TOKEN2",
    }
    page2 = {
        "items": [
            {
                "id": "PL2",
                "snippet": {"title": "Two", "thumbnails": {}},
                "contentDetails": {"itemCount": 2},
            }
        ],
    }
    pages = [page1, page2]
    seen = []

    class FakeClient:
        def get(self, url, params=None):
            seen.append(params)
            payload = pages.pop(0)

            class R:
                def raise_for_status(self):
                    return None

                def json(self_inner):
                    return payload

            return R()

    result = fetch_channel_playlists("UC1", "key", FakeClient())
    assert [p.youtube_playlist_id for p in result] == ["PL1", "PL2"]
    assert seen[0].get("pageToken") is None
    assert seen[1].get("pageToken") == "TOKEN2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_youtube.py -v -k fetch_channel_playlists`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Add to `backend/app/youtube.py`:

```python
_PLAYLISTS_URL = "https://www.googleapis.com/youtube/v3/playlists"


@dataclass
class PlaylistData:
    youtube_playlist_id: str
    title: str
    item_count: int
    thumbnail_url: str


def _pick_thumbnail(thumbs: dict) -> str:
    for key in ("high", "medium", "default"):
        candidate = (thumbs.get(key) or {}).get("url")
        if candidate:
            return candidate
    return ""


def fetch_channel_playlists(
    channel_id: str, api_key: str, client: httpx.Client
) -> list[PlaylistData]:
    playlists: list[PlaylistData] = []
    page_token: str | None = None
    while True:
        params = {
            "part": "snippet,contentDetails",
            "channelId": channel_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = client.get(_PLAYLISTS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            playlists.append(
                PlaylistData(
                    youtube_playlist_id=item.get("id", ""),
                    title=snippet.get("title") or "Untitled",
                    item_count=int(content.get("itemCount", 0) or 0),
                    thumbnail_url=_pick_thumbnail(snippet.get("thumbnails", {})),
                )
            )
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return playlists
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (checkpoint)**

```bash
git add backend/app/youtube.py backend/tests/test_youtube.py
git commit -m "feat: fetch public playlists for a channel"
```

---

## Task 4: Channel schemas and GET/PUT endpoints

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin.py -v -k channel`
Expected: FAIL — 404 (routes do not exist) / import errors.

- [ ] **Step 3: Add schemas**

Append to `backend/app/schemas.py`:

```python
class ChannelIn(BaseModel):
    channel: str


class ChannelOut(BaseModel):
    channel_id: str | None = None
    title: str | None = None
```

- [ ] **Step 4: Add endpoint imports and helpers**

In `backend/app/routers/admin.py`, update the imports:

```python
from app.models import Playlist, ScheduleSlot, Setting, Station, TrackCache
from app.schemas import ChannelIn, ChannelOut, PlaylistIn, SlotIn
from app.youtube import (
    TrackData,
    fetch_playlist_items,
    parse_playlist_id,
    resolve_channel_id,
)
```

Add these helpers after the `require_admin` function:

```python
def _save_channel(session: Session, channel_id: str, title: str) -> None:
    for key, value in (
        ("youtube_channel_id", channel_id),
        ("youtube_channel_title", title),
    ):
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
    session.commit()


def _get_saved_channel(session: Session) -> tuple[str | None, str | None]:
    channel_id = session.get(Setting, "youtube_channel_id")
    title = session.get(Setting, "youtube_channel_title")
    return (
        channel_id.value if channel_id else None,
        title.value if title else None,
    )
```

Add the endpoints at the end of the file:

```python
@router.get(
    "/youtube/channel",
    response_model=ChannelOut,
    dependencies=[Depends(require_admin)],
)
def get_youtube_channel(session: Session = Depends(get_session)) -> ChannelOut:
    channel_id, title = _get_saved_channel(session)
    return ChannelOut(channel_id=channel_id, title=title)


@router.put(
    "/youtube/channel",
    response_model=ChannelOut,
    dependencies=[Depends(require_admin)],
)
def set_youtube_channel(
    body: ChannelIn, session: Session = Depends(get_session)
) -> ChannelOut:
    if not body.channel.strip():
        raise HTTPException(status_code=400, detail="channel is required")
    settings = get_settings()
    try:
        with httpx.Client(timeout=10) as client:
            channel_id, title = resolve_channel_id(
                body.channel, settings.yt_api_key, client
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"YouTube lookup failed: {exc}"
        ) from exc
    _save_channel(session, channel_id, title)
    return ChannelOut(channel_id=channel_id, title=title)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v -k channel`
Expected: all PASS.

- [ ] **Step 6: Commit (checkpoint)**

```bash
git add backend/app/schemas.py backend/app/routers/admin.py backend/tests/test_admin.py
git commit -m "feat: save and read YouTube channel setting"
```

---

## Task 5: List channel playlists endpoint

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin.py`:

```python
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
        "/api/admin/stations", json={"name": "S", "slug": "s"}
    ).json()["id"]
    with Session(engine) as s:
        s.add(Playlist(station_id=sid, youtube_playlist_id="PLadded"))
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin.py -v -k list_playlists`
Expected: FAIL — 404 for the playlists route.

- [ ] **Step 3: Add the response schema**

Append to `backend/app/schemas.py`:

```python
class ChannelPlaylistOut(BaseModel):
    youtube_playlist_id: str
    title: str
    item_count: int
    thumbnail_url: str
    already_added: bool
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/routers/admin.py`:
- Extend the schema import to include `ChannelPlaylistOut`:

```python
from app.schemas import ChannelIn, ChannelOut, ChannelPlaylistOut, PlaylistIn, SlotIn
```

- Extend the youtube import to include `fetch_channel_playlists`:

```python
from app.youtube import (
    TrackData,
    fetch_channel_playlists,
    fetch_playlist_items,
    parse_playlist_id,
    resolve_channel_id,
)
```

- Add this endpoint at the end of the file:

```python
@router.get(
    "/youtube/playlists",
    response_model=list[ChannelPlaylistOut],
    dependencies=[Depends(require_admin)],
)
def list_youtube_playlists(
    session: Session = Depends(get_session),
) -> list[ChannelPlaylistOut]:
    channel_id, _ = _get_saved_channel(session)
    if not channel_id:
        return []
    settings = get_settings()
    try:
        with httpx.Client(timeout=10) as client:
            playlists = fetch_channel_playlists(
                channel_id, settings.yt_api_key, client
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"YouTube fetch failed: {exc}"
        ) from exc
    existing = set(session.exec(select(Playlist.youtube_playlist_id)).all())
    return [
        ChannelPlaylistOut(
            youtube_playlist_id=p.youtube_playlist_id,
            title=p.title,
            item_count=p.item_count,
            thumbnail_url=p.thumbnail_url,
            already_added=p.youtube_playlist_id in existing,
        )
        for p in playlists
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v`
Expected: all PASS (including previous admin tests).

- [ ] **Step 6: Run the full backend suite**

Run: `python -m pytest -v`
Expected: all PASS.

- [ ] **Step 7: Commit (checkpoint)**

```bash
git add backend/app/schemas.py backend/app/routers/admin.py backend/tests/test_admin.py
git commit -m "feat: list channel playlists with already-added flag"
```

---

## Task 6: Frontend types and API client

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/api/client.test.ts`, inside the `describe("api client", ...)` block:

```ts
  it("GETs the saved channel source", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ channel_id: "UC1", title: "Mine" }), {
        status: 200,
      }),
    );
    const result = await api.getChannelSource();
    expect(spy.mock.calls[0][0]).toBe("/api/admin/youtube/channel");
    expect(result).toEqual({ channel_id: "UC1", title: "Mine" });
  });

  it("PUTs the channel as JSON", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ channel_id: "UC1", title: "Mine" }), {
        status: 200,
      }),
    );
    await api.setChannelSource("@me");
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/admin/youtube/channel");
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(JSON.stringify({ channel: "@me" }));
  });

  it("GETs channel playlists", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    await api.listChannelPlaylists();
    expect(spy.mock.calls[0][0]).toBe("/api/admin/youtube/playlists");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm test -- src/api/client.test.ts`
Expected: FAIL — `api.getChannelSource is not a function`.

- [ ] **Step 3: Add types**

Append to `frontend/src/types.ts`:

```ts
export interface ChannelSource {
  channel_id: string | null;
  title: string | null;
}

export interface ChannelPlaylist {
  youtube_playlist_id: string;
  title: string;
  item_count: number;
  thumbnail_url: string;
  already_added: boolean;
}
```

- [ ] **Step 4: Add client methods**

In `frontend/src/api/client.ts`, extend the type-only import at the top:

```ts
import type {
  ChannelPlaylist,
  ChannelSource,
  CurrentStation,
  Station,
  StationDetail,
  Track,
} from "../types";
```

Add to the `api` object (e.g. after `syncAll`):

```ts
  getChannelSource: () => request<ChannelSource>("/admin/youtube/channel"),
  setChannelSource: (channel: string) =>
    request<ChannelSource>("/admin/youtube/channel", {
      method: "PUT",
      body: JSON.stringify({ channel }),
    }),
  listChannelPlaylists: () =>
    request<ChannelPlaylist[]>("/admin/youtube/playlists"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- src/api/client.test.ts`
Expected: all PASS.

- [ ] **Step 6: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Commit (checkpoint)**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat: admin channel playlist API client"
```

---

## Task 7: Admin "Browse YouTube playlists" UI

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`
- Test: `frontend/src/pages/AdminPage.dom.test.tsx`

- [ ] **Step 1: Update the test mock so existing tests keep working**

In `frontend/src/pages/AdminPage.dom.test.tsx`, replace the `api` object inside `vi.mock` with:

```tsx
    api: {
      login: vi.fn(),
      logout: vi.fn(),
      listStations: vi.fn(),
      createStation: vi.fn(),
      createPlaylist: vi.fn(),
      createSlot: vi.fn(),
      syncAll: vi.fn(),
      getChannelSource: vi.fn(),
      setChannelSource: vi.fn(),
      listChannelPlaylists: vi.fn(),
    },
```

Then, in every existing test that logs in, add a default channel mock right before `render(<AdminPage />)`. The simplest approach is to add an `afterEach`/`beforeEach` default:

```tsx
beforeEach(() => {
  mocked.getChannelSource.mockResolvedValue({ channel_id: null, title: null });
  mocked.listChannelPlaylists.mockResolvedValue([]);
});
```

Make sure `beforeEach` is imported from `vitest` (update the import line):

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
```

- [ ] **Step 2: Write the new failing tests**

Append these tests to `frontend/src/pages/AdminPage.dom.test.tsx`, inside the `describe("AdminPage", ...)` block:

```tsx
  it("saves a channel and lists its playlists", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.getChannelSource.mockResolvedValue({ channel_id: null, title: null });
    mocked.setChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue([
      {
        youtube_playlist_id: "PLnew",
        title: "New One",
        item_count: 5,
        thumbnail_url: "u",
        already_added: false,
      },
    ]);

    render(<AdminPage />);
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "pw" },
    });
    fireEvent.click(screen.getByText("Log in"));
    await screen.findByText("Add station");

    fireEvent.change(screen.getByPlaceholderText("@handle or channel URL"), {
      target: { value: "@me" },
    });
    fireEvent.click(screen.getByText("Save channel"));

    await waitFor(() =>
      expect(mocked.setChannelSource).toHaveBeenCalledWith("@me"),
    );
    expect(await screen.findByText("New One")).toBeInTheDocument();
    expect(await screen.findByText("(5 tracks)")).toBeInTheDocument();
  });

  it("adds a browsed playlist to the chosen station", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue([
      {
        youtube_playlist_id: "PLnew",
        title: "New One",
        item_count: 5,
        thumbnail_url: "u",
        already_added: false,
      },
    ]);
    mocked.createPlaylist.mockResolvedValue({
      id: 9,
      youtube_playlist_id: "PLnew",
      synced: 5,
      sync_error: null,
    });

    render(<AdminPage />);
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "pw" },
    });
    fireEvent.click(screen.getByText("Log in"));
    await screen.findByText("New One");

    fireEvent.change(screen.getByLabelText("Station for New One"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PLnew",
        "",
      ),
    );
    expect(await screen.findByText(/Playlist synced \(5 tracks\)/)).toBeInTheDocument();
  });

  it("shows already-added playlists as non-addable", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([]);
    mocked.getChannelSource.mockResolvedValue({
      channel_id: "UC1",
      title: "My Channel",
    });
    mocked.listChannelPlaylists.mockResolvedValue([
      {
        youtube_playlist_id: "PLadded",
        title: "Already",
        item_count: 3,
        thumbnail_url: "u",
        already_added: true,
      },
    ]);

    render(<AdminPage />);
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "pw" },
    });
    fireEvent.click(screen.getByText("Log in"));
    expect(await screen.findByText("Already")).toBeInTheDocument();
    expect(await screen.findByText("Added")).toBeInTheDocument();
    expect(screen.queryByText("Add")).not.toBeInTheDocument();
  });
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npm test -- src/pages/AdminPage.dom.test.tsx`
Expected: FAIL — no channel input / no "New One".

- [ ] **Step 4: Implement the UI**

In `frontend/src/pages/AdminPage.tsx`:

Update the type import:

```tsx
import type { ChannelPlaylist, ChannelSource, Station } from "../types";
```

Add state, near the other `useState` calls:

```tsx
  const [channel, setChannel] = useState<ChannelSource | null>(null);
  const [channelInput, setChannelInput] = useState("");
  const [channelError, setChannelError] = useState("");
  const [playlists, setPlaylists] = useState<ChannelPlaylist[]>([]);
  const [playlistStationById, setPlaylistStationById] = useState<
    Record<string, string>
  >({});
```

Add callbacks after `refreshStations`:

```tsx
  const loadPlaylists = useCallback(async () => {
    try {
      setPlaylists(await api.listChannelPlaylists());
    } catch {
      setPlaylists([]);
    }
  }, []);
```

Update the `login` function so it loads the saved channel after login:

```tsx
  const login = async () => {
    try {
      await api.login(password);
      setAuthed(true);
      setError("");
      await refreshStations();
      const source = await api.getChannelSource();
      setChannel(source);
      if (source.channel_id) {
        await loadPlaylists();
      }
    } catch (err) {
      setError(messageFor(err));
    }
  };
```

Add these handlers near `syncAll`:

```tsx
  const saveChannel = async () => {
    beginAction();
    setChannelError("");
    try {
      const source = await api.setChannelSource(channelInput.trim());
      setChannel(source);
      setChannelInput("");
      await loadPlaylists();
    } catch (err) {
      setChannelError(messageFor(err));
    }
  };

  const addFromList = async (playlistId: string) => {
    beginAction();
    const stationId = Number(playlistStationById[playlistId] ?? "");
    if (!stationId) {
      setError("Select a station first.");
      return;
    }
    try {
      const result = await api.createPlaylist(
        stationId,
        `https://www.youtube.com/playlist?list=${playlistId}`,
        "",
      );
      setNotice(
        result.sync_error
          ? `Playlist saved, but sync failed: ${result.sync_error}`
          : `Playlist synced (${result.synced} tracks).`,
      );
      await refreshStations();
      await loadPlaylists();
    } catch (err) {
      setError(messageFor(err));
    }
  };
```

Add a new `<section>` after the existing `<section><h2>Playlist</h2>...</section>`:

```tsx
      <section>
        <h2>Browse YouTube playlists</h2>
        {channel?.channel_id ? (
          <div>
            <p>Channel: {channel.title ?? channel.channel_id}</p>
            <button type="button" onClick={() => setChannel(null)}>
              Change
            </button>
            <button type="button" onClick={loadPlaylists}>
              Refresh
            </button>
            {channelError && (
              <p className="error" role="alert">
                {channelError}
              </p>
            )}
            <ul>
              {playlists.map((p) => (
                <li key={p.youtube_playlist_id}>
                  {p.thumbnail_url && (
                    <img src={p.thumbnail_url} alt="" width={48} />
                  )}
                  <span>{p.title}</span>
                  <span> ({p.item_count} tracks)</span>
                  {p.already_added ? (
                    <span className="added">Added</span>
                  ) : (
                    <>
                      <select
                        aria-label={`Station for ${p.title}`}
                        value={playlistStationById[p.youtube_playlist_id] ?? ""}
                        onChange={(e) =>
                          setPlaylistStationById((prev) => ({
                            ...prev,
                            [p.youtube_playlist_id]: e.target.value,
                          }))
                        }
                      >
                        <option value="">Select a station…</option>
                        {stations.map((s) => (
                          <option key={s.slug} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => addFromList(p.youtube_playlist_id)}
                      >
                        Add
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div>
            <input
              aria-label="YouTube channel"
              placeholder="@handle or channel URL"
              value={channelInput}
              onChange={(e) => setChannelInput(e.target.value)}
            />
            <button
              type="button"
              onClick={saveChannel}
              disabled={!channelInput.trim()}
            >
              Save channel
            </button>
            {channelError && (
              <p className="error" role="alert">
                {channelError}
              </p>
            )}
          </div>
        )}
      </section>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- src/pages/AdminPage.dom.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Run the full frontend suite and typecheck**

Run: `npm test`
Expected: all PASS.

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Commit (checkpoint)**

```bash
git add frontend/src/pages/AdminPage.tsx frontend/src/pages/AdminPage.dom.test.tsx
git commit -m "feat: browse and add channel playlists in admin"
```

---

## Task 8: Build and end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Rebuild and start the stack**

Run (from repo root): `docker compose up -d --build`
Expected: `backend`, `frontend`, `caddy` all start; wait for healthy.

- [ ] **Step 2: Confirm the migration ran**

Run: `docker compose logs backend | Select-String -Pattern "alembic|Running upgrade|error" -CaseSensitive:$false`
Expected: log shows the upgrade to the new revision; no startup error. Then:
`docker compose ps` shows `backend` as `healthy`.

- [ ] **Step 3: Exercise the API through Caddy**

Run (PowerShell, from repo root):

```powershell
curl.exe -ks -o NUL -w "%{http_code}`n" https://localhost:8010/api/admin/youtube/channel
```

Expected: `401` (unauthenticated), proving the route exists and is protected.

- [ ] **Step 4: Verify the admin UI in a browser**

Open `https://localhost:8010/admin` (or `http://localhost:8012/admin`), log in with the password from `backend/.env`, and:
1. In "Browse YouTube playlists", enter your channel as `@handle` or its URL and click **Save channel**.
2. Confirm the channel title appears and public playlists load with thumbnails and track counts.
3. Add one to a station and confirm it reports "Playlist synced (N tracks)" and the row switches to **Added**.
4. Confirm the homepage now shows the station on the dial and playback works after **TUNE IN**.

- [ ] **Step 5: Final checkpoint**

Confirm: `python -m pytest` (backend) and `npm test` + `npm run typecheck` (frontend) all pass. Commit the plan/any fixes if under git.

```bash
git add -A
git commit -m "chore: verify channel playlist browsing end to end"
```

---

## Self-Review Notes

- **Spec coverage:** `Setting` table + migration (Task 1); `resolve_channel_id` and `fetch_channel_playlists` (Tasks 2–3); `ChannelIn`/`ChannelOut`/`ChannelPlaylistOut` and the three endpoints incl. `already_added` (Tasks 4–5); frontend types/client (Task 6); admin browse UI with inline add and Added badge (Task 7); end-to-end verification (Task 8). Manual URL entry is untouched.
- **Placeholder scan:** no TBD/TODO; every code step contains full code and every command states expected output.
- **Type consistency:** `ChannelSource`/`ChannelPlaylist` (frontend) mirror `ChannelOut`/`ChannelPlaylistOut` (backend); `PlaylistData` fields are used identically in Tasks 3 and 5; `createPlaylist(stationId, url, "")` matches the existing client signature.
