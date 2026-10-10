# Nakout Admin Deck UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the admin studio onto the `UI reference/Nakout Admin.html` design (same vinyl-deck world as the homepage) with genre colours, grouped playlists, genre cards, and a visual 24h schedule timeline — reskin in place, keeping every existing API behaviour.

**Architecture:** Four existing admin panels keep their props and API calls; their JSX is rebuilt to the reference layouts. Backend gains `Genre.color` and `Playlist.synced_at` (nullable columns + backfill migration). New shared frontend pieces: `Toast`, `PaletteSwatches`, `GenreChipRadio`, `ScheduleTimeline`, `renderCover` (generative SVG fallback art). Admin CSS lives with the app's other styles in `frontend/src/styles/vintage.css`, adapted from the reference CSS (lines 4–219).

**Tech Stack:** FastAPI + SQLModel + Alembic (SQLite, batch migrations); React + Vite + vitest/@testing-library; Playwright-style DOM tests are NOT used — DOM tests only.

**Conventions for every task:**
- TDD where practical: write the test, see it fail, implement, see it pass, commit.
- Frontend commands run in `frontend/` workdir: `npm run test`, `npm run typecheck`, `npm run build`.
- Backend commands run in `backend/` workdir: `python -m pytest -q` (or a specific test path).
- **Visual CSS source of truth:** `UI reference/Nakout Admin.html` (untracked, READ ONLY — never commit it). Its CSS token names differ slightly from the app's; use the app tokens already in `frontend/src/styles/vintage.css` `:root` (`--bg-2` for page bg, `--wood` for card bg, `--wood-light` for raised, `--field` equivalent is `--bg-2`, `--line` equivalents are `--border`/`--border-strong`, `--amber`, `--cream`, `--muted`, `--led`, `--danger`, `--ok`, `--font-display`, `--font-mono`).
- Never stage `UI reference/`, `.superpowers/`, or `docs/superpowers/plans/`.
- Every task ends with a `docs/changelog.md` entry (most recent first) per AGENTS.md: date + summary, files, restart flag, verification results.

---

### Task 1: Backend — genre colour

**Files:**
- Modify: `backend/app/models.py` (Genre model + palette constant)
- Create: `backend/alembic/versions/a1b2c3d4e5f6_genre_color.py`
- Modify: `backend/app/schemas.py` (GenreOut.color)
- Modify: `backend/app/routers/admin.py` (GenreIn/GenreUpdate + create/update logic)
- Modify: `backend/app/routers/genres.py:88`, `backend/app/routers/now.py:18`, `backend/app/routers/schedule.py:29` (pass color)
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin.py` (reuse the file's existing `_client(tmp_path)` helper):

```python
def test_create_genre_with_explicit_color(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/studio/genres",
        json={"name": "Chill", "slug": "chill", "color": "#123abc"},
    )
    assert resp.status_code == 201
    assert resp.json()["color"] == "#123abc"


def test_create_genre_without_color_gets_first_unused_palette(tmp_path):
    from app.models import GENRE_PALETTE

    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    first = client.post(
        "/api/studio/genres", json={"name": "A", "slug": "a"}
    ).json()
    second = client.post(
        "/api/studio/genres", json={"name": "B", "slug": "b"}
    ).json()
    assert first["color"] == GENRE_PALETTE[0]
    assert second["color"] == GENRE_PALETTE[1]


def test_update_genre_color(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    gid = client.post(
        "/api/studio/genres", json={"name": "A", "slug": "a"}
    ).json()["id"]
    resp = client.put(
        f"/api/studio/genres/{gid}", json={"color": "#ff00ff"}
    )
    assert resp.status_code == 200
    assert resp.json()["color"] == "#ff00ff"


def test_invalid_color_rejected(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/studio/genres", json={"name": "A", "slug": "a", "color": "red"}
    )
    assert resp.status_code == 422


def test_public_genre_list_includes_color(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    client.post("/api/studio/genres", json={"name": "Chill", "slug": "chill"})
    listed = client.get("/api/genres").json()
    assert listed[0]["color"]


def test_palette_backfill_migration(tmp_path):
    """Existing rows get an unused palette colour at upgrade time."""
    import sqlite3

    import sqlalchemy as sa
    from alembic import migration

    db = tmp_path / "pre.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE genre (
            id INTEGER PRIMARY KEY, name VARCHAR NOT NULL,
            slug VARCHAR NOT NULL, is_default BOOLEAN,
            sort_order INTEGER, color VARCHAR
        );
        INSERT INTO genre (name, slug, is_default, sort_order)
            VALUES ('A','a',0,0), ('B','b',0,0);
        """
    )
    # fake a pre-migration alembic stamp
    conn.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
    )
    conn.execute("INSERT INTO alembic_version VALUES ('d4e5f6a7b8c9')")
    conn.commit()
    conn.close()

    from app.config import get_settings

    settings = get_settings()
    original = settings.database_url
    object.__setattr__(settings, "database_url", f"sqlite:///{db}")
    try:
        migration.MigrationContext.configure(sa.create_engine(f"sqlite:///{db}").connect())
        from alembic.command import upgrade as alembic_upgrade
        from alembic.config import Config

        cfg = Config()
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
        script_location = str(
            __import__("pathlib").Path(__file__).resolve().parent.parent / "alembic"
        )
        cfg.set_main_option("script_location", script_location)
        alembic_upgrade(cfg, "a1b2c3d4e5f6")
    finally:
        object.__setattr__(settings, "database_url", original)

    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT name, color FROM genre ORDER BY id").fetchall()
    conn.close()
    colors = {name: color for name, color in rows}
    assert colors["A"] and colors["B"]
    assert colors["A"] != colors["B"]
```

NOTE on the backfill test: if `app.config.get_settings()` is a cached/pydantic Settings without `__setattr__` support, prefer running the alembic upgrade directly with a `Config` pointed at the sqlite URL (skip the settings swap entirely). Keep whichever approach compiles; the assertions on the two rows are the contract.

- [ ] **Step 2: Run to verify failure**

Run (in `backend/`): `python -m pytest tests/test_admin.py -k "color or palette or backfill" -q`
Expected: FAIL (422 never reached — `color` unknown field is silently ignored, `color` missing in response means `"color"` KeyError / assertion error, `GENRE_PALETTE` ImportError).

- [ ] **Step 3: Implement the model + shared palette**

In `backend/app/models.py` add below the imports:

```python
# Genre accent colours, in assignment order (matches the admin palette picker).
GENRE_PALETTE: tuple[str, ...] = (
    "#f2a33a",
    "#e0654a",
    "#8fb996",
    "#5fb3b3",
    "#6fa3e0",
    "#a58be0",
    "#e58fb0",
    "#d8c18a",
)
```

And on `Genre`:

```python
class Genre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    is_default: bool = False
    sort_order: int = 0
    color: str | None = Field(default=None)
```

- [ ] **Step 4: Alembic migration**

Create `backend/alembic/versions/a1b2c3d4e5f6_genre_color.py` (down_revision `d4e5f6a7b8c9`):

```python
"""genre accent colour

Revision ID: a1b2c3d4e5f6
Revises: d4e5f6a7b8c9
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlmodel import Session, select

from app.models import GENRE_PALETTE, Genre


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.add_column(sa.Column("color", sa.String(9), nullable=True))
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        genres = session.exec(select(Genre).order_by(Genre.id)).all()
        used = {g.color for g in genres if g.color}
        for genre in genres:
            if genre.color:
                continue
            pick = next(
                (c for c in GENRE_PALETTE if c not in used),
                GENRE_PALETTE[len(used) % len(GENRE_PALETTE)],
            )
            genre.color = pick
            used.add(pick)
        session.add_all(genres)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.drop_column("color")
```

NOTE: importing app models inside a migration has worked in this repo's style so far via visible deps (`from app.models import ...` matches this plan's introduced constant only). If importing modules triggers side effects the app chokes on, inline the palette list in the migration instead of importing.

- [ ] **Step 5: Schema + routers**

In `backend/app/schemas.py`:

```python
class GenreOut(BaseModel):
    id: int
    name: str
    slug: str
    is_default: bool
    color: str = ""
    track_count: int
```

In `backend/app/routers/admin.py`:

```python
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_color(value: str | None) -> str | None:
    if value is None:
        return None
    if not _COLOR_RE.match(value):
        raise HTTPException(status_code=422, detail="color must be #rrggbb")
    return value.lower()


def _first_unused_color(session: Session) -> str:
    used = set(
        session.exec(select(Genre.color)).all()  # type: ignore[arg-type]
    )
    return next(
        (c for c in GENRE_PALETTE if c not in used),
        GENRE_PALETTE[len(used) % len(GENRE_PALETTE)],
    )
```

(Add `GENRE_PALETTE` to the `from app.models import ...` line.) Genre input classes gain the field:

```python
class GenreIn(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    is_default: bool = False
    sort_order: int = 0
    color: str | None = None


class GenreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None
    sort_order: int | None = None
    color: str | None = Field(default=None, min_length=1)
```

`create_genre` becomes:

```python
@router.post("/genres", status_code=201, dependencies=[Depends(require_admin)])
def create_genre(body: GenreIn, session: Session = Depends(get_session)) -> Genre:
    existing = session.exec(select(Genre).where(Genre.slug == body.slug)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="genre slug already exists")
    genre = Genre(**body.model_dump())
    genre.color = _validate_color(genre.color) or _first_unused_color(session)
    session.add(genre)
    session.commit()
    session.refresh(genre)
    return genre
```

In `update_genre`, right before the `for field, value in updates.items():` loop add:

```python
    if "color" in updates:
        valid = _validate_color(updates["color"])
        if valid is None:
            raise HTTPException(status_code=422, detail="color must be #rrggbb")
        updates["color"] = valid
```

Serialization sites (pass colour through):
- `backend/app/routers/genres.py` — in each `GenreOut(...)` construction add `color=(genre.color or "")` (read the file; the attribute on the ORM object is the genre row it already has in scope).
- `backend/app/routers/now.py:18` and `backend/app/routers/schedule.py:29` — same: `color=state.genre.color or ""`.

Colour counts as a "genre changed" signal: in `update_genre`, after commit, call the existing radio push exactly once. Look at how other mutations do it (`from app.routers.ws import notify_radio` is already imported in admin.py) and mirror the `update_genre` pattern already used for name/slug today (check: if there is no notify_radio call in update_genre today, add `await`-free `notify_radio(session, state)`-style call consistent with neighbouring endpoints — copy the exact call shape used in `delete_genre` or `update_slot`).

- [ ] **Step 6: Run the suite**

Run: `python -m pytest tests/test_admin.py -q`
Expected: pass, including the 6 new tests.

- [ ] **Step 7: Commit + changelog**

```bash
git add backend/app backend/alembic backend/tests
git commit -m "feat: genre accent colour (model, migration, CRUD, serialization)"
```

Changelog entry (frontend+backend? backend only → restart `backend`): date 2026-10-09, summary "genre colour field end to end", files, restart `docker compose up -d --build backend`, verification "pytest green".

---

### Task 2: Backend — playlist synced_at

**Files:**
- Modify: `backend/app/models.py` (Playlist)
- Create: `backend/alembic/versions/b2c3d4e5f6a7_playlist_synced_at.py`
- Modify: `backend/app/sync.py`, `backend/app/schemas.py`, `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Failing tests** (append to `backend/tests/test_admin.py`)

```python
def test_create_playlist_sets_synced_at(tmp_path, monkeypatch):
    from datetime import datetime

    from app.sync import sync_playlist  # noqa: F401  (import proves module loads)

    client, engine = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    gid = client.post(
        "/api/studio/genres", json={"name": "A", "slug": "a"}
    ).json()["id"]

    tracks = [
        TrackData(
            youtube_video_id="v1", title="T", artist="A",
            thumbnail_url="", position=0, duration_seconds=1,
        )
    ]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch", lambda: lambda pid: tracks
    )
    resp = client.post(
        "/api/studio/playlists",
        json={
            "genre_id": gid,
            "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLabc123",
        },
    )
    assert resp.status_code == 201
    listed = client.get("/api/studio/playlists").json()
    assert listed
    assert listed[0]["synced_at"] is not None


def test_refresh_updates_synced_at(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    gid = client.post(
        "/api/studio/genres", json={"name": "A", "slug": "a"}
    ).json()["id"]
    tracks = [
        TrackData(
            youtube_video_id="v1", title="T", artist="A",
            thumbnail_url="", position=0, duration_seconds=1,
        )
    ]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch", lambda: lambda pid: tracks
    )
    pid = client.post(
        "/api/studio/playlists",
        json={
            "genre_id": gid,
            "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLabc123",
        },
    ).json()["id"]
    before = [
        p for p in client.get("/api/studio/playlists").json() if p["id"] == pid
    ][0]["synced_at"]
    resp = client.post(f"/api/studio/playlists/{pid}/refresh")
    assert resp.status_code == 200
    after = [
        p for p in client.get("/api/studio/playlists").json() if p["id"] == pid
    ][0]["synced_at"]
    assert after is not None
    # in a 1-second-resolution test this may equal `before`; that's OK — the
    # contract is "not null" and a non-exception refresh.


def test_synced_at_backfilled_from_track_cache(tmp_path):
    """Migration backfills synced_at from the newest TrackCache.fetched_at."""
    import sqlite3
    from pathlib import Path

    import sqlalchemy as sa
    from alembic import Config
    from alembic import command as alembic_command

    db = tmp_path / "pre.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE genre (
            id INTEGER PRIMARY KEY, name VARCHAR NOT NULL,
            slug VARCHAR NOT NULL, is_default BOOLEAN,
            sort_order INTEGER, color VARCHAR
        );
        INSERT INTO genre (name, slug, is_default, sort_order, color)
            VALUES ('A','a',0,0,'#f2a33a');
        CREATE TABLE playlist (
            id INTEGER PRIMARY KEY, genre_id INTEGER NOT NULL,
            youtube_playlist_id VARCHAR NOT NULL, label VARCHAR,
            synced_at DATETIME
        );
        INSERT INTO playlist (genre_id, youtube_playlist_id, label)
            VALUES (1, 'PL1', '');
        CREATE TABLE trackcache (
            id INTEGER PRIMARY KEY, playlist_id INTEGER NOT NULL,
            youtube_video_id VARCHAR NOT NULL, title VARCHAR NOT NULL,
            artist VARCHAR NOT NULL, thumbnail_url VARCHAR,
            duration_seconds INTEGER, position INTEGER,
            fetched_at DATETIME
        );
        INSERT INTO trackcache
            (playlist_id, youtube_video_id, title, artist, thumbnail_url,
             duration_seconds, position, fetched_at)
            VALUES (1, 'v1', 'T', 'A', '', 1, 0, '2026-10-01 10:00:00');
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
    )
    conn.execute("INSERT INTO alembic_version VALUES ('d4e5f6a7b8c9')")
    conn.commit()
    conn.close()

    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    alembic_command.upgrade(cfg, "b2c3d4e5f6a7")

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT synced_at FROM playlist").fetchone()
    conn.close()
    assert row[0] is not None
```

NOTE: retry patterns above follow existing sync tests (see existing playlist create/refresh tests in this file which monkeypatch `_build_fetch` — mirror them exactly if slightly different).

- [ ] **Step 2: Run, watch fail**

Run: `python -m pytest tests/test_admin.py -k "synced_at" -q` → FAIL (unknown field `synced_at` in responses / missing migration).

- [ ] **Step 3: Implement**

`backend/app/models.py`:

```python
class Playlist(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    youtube_playlist_id: str
    label: str = ""
    synced_at: datetime | None = Field(default=None)
```

`sync.py` — stamp at the end of a successful fetch (before commit):

```python
from app.models import Playlist, TrackCache
from app.youtube import TrackData
from app.models import _utcnow  # reuse the existing utc helper


def sync_playlist(...):
    tracks = fetch(...)
    session.exec(delete(TrackCache).where(...))
    for t in tracks:
        session.add(TrackCache(...))
    playlist.synced_at = _utcnow()
    session.add(playlist)
    session.commit()
    return len(tracks)
```

(`_utcnow` is already defined in models.py — import it.)

Migration `backend/alembic/versions/b2c3d4e5f6a7_playlist_synced_at.py` (down_revision `a1b2c3d4e5f6`):

```python
"""playlist last-synced timestamp

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("playlist") as batch_op:
        batch_op.add_column(sa.Column("synced_at", sa.DateTime(), nullable=True))
    op.execute(
        """
        UPDATE playlist
           SET synced_at = (
               SELECT MAX(fetched_at) FROM trackcache
                WHERE trackcache.playlist_id = playlist.id
           )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("playlist") as batch_op:
        batch_op.drop_column("synced_at")
```

`backend/app/schemas.py`:

```python
class PlaylistOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    youtube_playlist_id: str
    label: str
    track_count: int
    synced_at: str | None = None
```

`backend/app/routers/admin.py` `list_added_playlists` — include it (datetime to iso string):

```python
    return [
        PlaylistOut(
            id=p.id,
            genre_id=p.genre_id,
            genre_name=genre_names.get(p.genre_id, ""),
            youtube_playlist_id=p.youtube_playlist_id,
            label=p.label,
            track_count=counts.get(p.id, 0),
            synced_at=p.synced_at.isoformat() + "Z" if p.synced_at else None,
        )
        for p in playlists
    ]
```

(synced_at stored naive-UTC via `_utcnow`; appending "Z" is then correct.)

- [ ] **Step 4: Run the backend suite** — `python -m pytest tests/test_admin.py -q` green.
- [ ] **Step 5: Commit + changelog** — `git commit -m "feat: playlist synced_at column (set on sync, backfilled)"`; changelog (backend restart).

---

### Task 3: Frontend data layer — types, client, format helpers

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/api/client.ts`
- Modify: `frontend/src/utils/format.ts`
- Create: `frontend/src/utils/profile.ts` (generative cover art; pure, unit-testable)
- Tests: `frontend/src/utils/format.unit.test.ts` (extend or create; co-located-style used by `deck.unit.test.ts`), `frontend/src/utils/profile.unit.test.ts`

- [ ] **Step 1: Failing unit tests**

Create `frontend/src/utils/format.unit.test.ts` additions in its style (see `deck.unit.test.ts` naming; if a `format.unit.test.ts` already exists, extend it):

```tsx
import { describe, expect, it } from "vitest";
import { minutesOf, twelveHour, timeAgo, fmtMin } from "./format";

describe("schedule time helpers", () => {
  it("minutesOf()", () => {
    expect(minutesOf("06:05")).toBe(365);
    expect(minutesOf("00:00")).toBe(0);
  });

  it("twelveHour()", () => {
    expect(twelveHour(0)).toBe("Midnight");
    expect(twelveHour(390)).toBe("6:30 AM");
    expect(twelveHour(810)).toBe("1:30 PM");
    expect(twelveHour(1439)).toBe("11:59 PM");
  });

  it("fmtMin()", () => {
    expect(fmtMin(90)).toBe("1h 30m");
    expect(fmtMin(45)).toBe("45m");
    expect(fmtMin(120)).toBe("2h");
  });

  it("timeAgo()", () => {
    const now = Date.parse("2026-10-09T12:00:00Z");
    expect(timeAgo(now - 30_000, now)).toBe("just now");
    expect(timeAgo(now - 5 * 60_000, now)).toBe("5 min ago");
    expect(timeAgo(now - 2 * 3_600_000, now)).toBe("2h ago");
    expect(timeAgo(now - 3 * 86_400_000, now)).toBe("3d ago");
  });
});
```

Create `frontend/src/utils/profile.unit.test.ts`:

```tsx
import { describe, expect, it } from "vitest";
import { cssCover } from "./profile";

describe("cssCover()", () => {
  it("is a data-URI CSS background for any string", () => {
    const a = cssCover("Endless Love");
    const b = cssCover("Du Hast");
    const c = cssCover("Endless Love");
    expect(a).toMatch(/^url\("data:image\/svg\+xml/);
    expect(a).not.toBe(b);
    expect(a).toBe(c);
  });
});
```

- [ ] **Step 2: Run, watch fail** — `npm run test -- src/utils` (workdir `frontend`) → FAIL (missing exports).

- [ ] **Step 3: Implement**

`frontend/src/utils/format.ts` — append:

```ts
export function minutesOf(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

export function twelveHour(mins: number): string {
  const m = ((mins % 1440) + 1440) % 1440;
  if (m === 0) return "Midnight";
  const h = Math.floor(m / 60);
  const mm = m % 60;
  const suffix = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 || 12;
  return `${hour12}:${String(mm).padStart(2, "0")} ${suffix}`;
}

export function fmtMin(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h ? `${h}h` : ""}${h && m ? " " : ""}${m ? `${m}m` : ""}`;
}

export function timeAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return "never";
  const ts = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`);
  const diff = Math.floor((now - ts) / 60_000);
  if (diff < 1) return "just now";
  if (diff < 60) return `${diff} min ago`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
```

`frontend/src/utils/profile.ts` (new) — the reference's generated-cover helper, typed modern:

```ts
const PALS: [string, string, string][] = [
  ["#f2a33a", "#7a2e1d", "#1c110a"],
  ["#e9d8b4", "#2f5d62", "#10242a"],
  ["#ff7a59", "#3b1f5e", "#120a24"],
  ["#ffd166", "#c1440e", "#2a0f08"],
  ["#9bd1c1", "#1d3b53", "#0a1824"],
  ["#f4b6c2", "#5a1f3a", "#1c0a14"],
];

export function cssCover(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  const [main, from, to] = PALS[h % PALS.length];
  const k = h % 5;
  const cx = 60 + k * 18;
  const cy = 150 - k * 14;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">` +
    `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/>` +
    `</linearGradient></defs>` +
    `<rect width="200" height="200" fill="url(#g)"/>` +
    `<circle cx="${cx}" cy="${cy}" r="62" fill="${main}"/>` +
    `<circle cx="${cx}" cy="${cy}" r="62" fill="none" stroke="${to}" stroke-width="3" transform="translate(14 -14)"/>` +
    `<rect y="168" width="200" height="32" fill="${to}" opacity=".55"/>` +
    `</svg>`;
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
}
```

- [ ] **Step 4: types + client**

`frontend/src/types.ts` — on `Genre` add `color: string;`; on `AddedPlaylist` add `synced_at: string | null;`.

`frontend/src/api/client.ts`:

```ts
  createGenre: (name: string, slug: string, color?: string) =>
    request<Genre>("/studio/genres", {
      method: "POST",
      body: JSON.stringify({ name, slug, ...(color ? { color } : {}) }),
    }),
  updateGenre: (
    id: number,
    updates: Partial<Pick<Genre, "name" | "slug" | "is_default" | "color">>,
  ) =>
    request<Genre>(`/studio/genres/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),
```

- [ ] **Step 5: Run everything** — `npm run test` (all), `npm run typecheck`. Green.
- [ ] **Step 6: Commit + changelog** — `git commit -m "feat: colour/synced_at on shapes, schedule time helpers, generated covers"`; changelog (frontend-only? build is not deploy-critical until reskin ships — no restart yet since it's unreferenced; state "no restart (not yet exercised)" or "frontend-only" — choose frontend-only and note it ships with the reskin).

---

### Task 4: Shared primitives — Toast, PaletteSwatches, GenreChipRadio (+ CSS)

**Files:**
- Create: `frontend/src/components/admin/Toast.tsx`, `frontend/src/components/admin/PaletteSwatches.tsx`, `frontend/src/components/admin/GenreChipRadio.tsx`
- Modify: `frontend/src/styles/vintage.css` (new admin class families; do NOT remove existing admin rules until Task 8 — additive here)
- Tests: `frontend/src/components/admin/Toast.dom.test.tsx`, `PaletteSwatches.dom.test.tsx`, `GenreChipRadio.dom.test.tsx`

- [ ] **Step 1: Failing DOM tests**

`frontend/src/components/admin/Toast.dom.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toast } from "./Toast";

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the message with role=status", () => {
    render(<Toast message="Genre added." onDone={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent("Genre added.");
  });

  it("auto-hides after 2.2s and calls onDone", () => {
    const onDone = vi.fn();
    render(<Toast message="Saved." onDone={onDone} />);
    act(() => {
      vi.advanceTimersByTime(2200);
    });
    expect(onDone).toHaveBeenCalled();
  });

  it("renders nothing when message is empty", () => {
    render(<Toast message="" onDone={() => {}} />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
```

`PaletteSwatches.dom.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PaletteSwatches } from "./PaletteSwatches";
import { GENRE_PALETTE } from "../../palette";

describe("PaletteSwatches", () => {
  it("renders one radio per palette colour, checked on the selected", () => {
    render(
      <PaletteSwatches
        label="Genre colour"
        value={GENRE_PALETTE[0]}
        onChange={() => {}}
      />,
    );
    const group = screen.getByRole("radiogroup", { name: "Genre colour" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(GENRE_PALETTE.length);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
  });

  it("reports clicked colour", () => {
    const onChange = vi.fn();
    render(
      <PaletteSwatches label="Genre colour" value="" onChange={onChange} />,
    );
    const group = screen.getByRole("radiogroup", { name: "Genre colour" });
    fireEvent.click(within(group).getAllByRole("radio")[2]);
    expect(onChange).toHaveBeenCalledWith(GENRE_PALETTE[2]);
  });
});
```

(import `within` from @testing-library/react; `GENRE_PALETTE` for the frontend is a new `frontend/src/palette.ts` — mirror of the backend tuple, single source for chips + swatches.)

`GenreChipRadio.dom.test.tsx`:

```tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GenreChipRadio } from "./GenreChipRadio";

const genres = [
  { id: 1, name: "Emo Night", slug: "EN", is_default: false, color: "#f2a33a", track_count: 3 },
  { id: 2, name: "NU Metal", slug: "numetal", is_default: false, color: "#e0654a", track_count: 5 },
];

describe("GenreChipRadio", () => {
  it("chips carry the genre colour as --gc and radiogroup semantics", () => {
    render(<GenreChipRadio label="Genre" genres={genres} value={2} onChange={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: "Genre" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[1]).toHaveAttribute("aria-checked", "true");
    expect(radios[0].style.getPropertyValue("--gc")).toBe("#f2a33a");
    expect(radios[0]).toHaveTextContent("Emo Night");
  });

  it("shows the empty hint when there are no genres", () => {
    render(<GenreChipRadio label="Genre" genres={[]} value={null} onChange={() => {}} />);
    expect(screen.getByText(/Create a genre first/i)).toBeInTheDocument();
  });

  it("selects on click", () => {
    const onChange = vi.fn();
    render(<GenreChipRadio label="Genre" genres={genres} value={1} onChange={onChange} />);
    fireEvent.click(screen.getByText("NU Metal"));
    expect(onChange).toHaveBeenCalledWith(2);
  });
});
```

- [ ] **Step 2: Run, watch fail.**

- [ ] **Step 3: Implement the components**

Create `frontend/src/palette.ts`:

```ts
export const GENRE_PALETTE = [
  "#f2a33a",
  "#e0654a",
  "#8fb996",
  "#5fb3b3",
  "#6fa3e0",
  "#a58be0",
  "#e58fb0",
  "#d8c18a",
] as const;
```

`frontend/src/components/admin/Toast.tsx`:

```tsx
import { useEffect, useRef } from "react";

interface Props {
  message: string;
  onDone: () => void;
}

export function Toast({ message, onDone }: Props) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!message) return;
    timer.current = setTimeout(onDone, 2200);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onDone is stable at call sites
  }, [message]);

  if (!message) return null;
  return (
    <p className="toast" role="status">
      {message}
    </p>
  );
}
```

`frontend/src/components/admin/PaletteSwatches.tsx`:

```tsx
import { GENRE_PALETTE } from "../../palette";

interface Props {
  label: string;
  value: string;
  onChange: (color: string) => void;
}

export function PaletteSwatches({ label, value, onChange }: Props) {
  return (
    <div
      className="swatches"
      role="radiogroup"
      aria-label={label}
      style={{ display: "contents" }}
    >
      {GENRE_PALETTE.map((c, i) => (
        <button
          key={c}
          type="button"
          role="radio"
          className="sw"
          aria-checked={value === c}
          aria-label={`Colour ${i + 1}`}
          style={{ "--gc": c } as React.CSSProperties}
          onClick={() => onChange(c)}
        />
      ))}
    </div>
  );
}
```

(`style={{ display: "contents" }}` keeps the styles grid-friendly; keep it unless it upsets styling, then drop and let `.swatches` flex apply.)

`frontend/src/components/admin/GenreChipRadio.tsx`:

```tsx
import type { Genre } from "../../types";

interface Props {
  label: string;
  genres: Genre[];
  value: number | null;
  onChange: (genreId: number) => void;
}

export function GenreChipRadio({ label, genres, value, onChange }: Props) {
  if (!genres.length) {
    return <p className="hint">Create a genre first, then come back.</p>;
  }
  return (
    <div className="chips" role="radiogroup" aria-label={label}>
      {genres.map((g) => (
        <button
          key={g.id}
          type="button"
          role="radio"
          className="gchip"
          aria-checked={g.id === value}
          style={{ "--gc": g.color || "var(--amber)" } as React.CSSProperties}
          onClick={() => onChange(g.id)}
        >
          <i className="dot" aria-hidden="true" />
          {g.name}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: CSS (append to the admin section of `vintage.css`, before the queue block)**

```css
/* ---------- Admin reference components (Toast, chips, swatches) ---------- */
.toast {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translate(-50%, 8px);
  opacity: 0.98;
  pointer-events: none;
  background: var(--cream);
  color: var(--bg-2);
  padding: 10px 18px;
  border-radius: 999px;
  font-weight: 800;
  font-size: 0.9rem;
  max-width: min(92vw, 480px);
  text-align: center;
  z-index: 30;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.5);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.gchip {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--wood);
  color: var(--cream);
  font-weight: 500;
  cursor: pointer;
}
.gchip[aria-checked="true"] {
  background: var(--gc, var(--amber));
  color: var(--bg-2);
  border-color: var(--gc, var(--amber));
  font-weight: 800;
}
.gchip .dot {
  background: var(--gc, var(--amber));
}
.gchip[aria-checked="true"] .dot {
  background: var(--bg-2);
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--gc, var(--amber));
  flex: 0 0 auto;
  display: inline-block;
}
.dot.big {
  width: 14px;
  height: 14px;
}
.swatches {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.sw {
  width: 26px;
  height: 26px;
  padding: 0;
  border-radius: 50%;
  background: var(--gc, var(--amber));
  border: 2px solid transparent;
  cursor: pointer;
}
.sw[aria-checked="true"] {
  box-shadow: 0 0 0 2px var(--bg-2), 0 0 0 4px var(--cream);
}
.flash {
  animation: flash 1.4s ease-out;
}
@keyframes flash {
  0% {
    box-shadow: 0 0 0 2px var(--amber);
  }
  100% {
    box-shadow: 0 0 0 2px transparent;
  }
}
.spin {
  width: 10px;
  height: 10px;
  border: 2px solid var(--amber-soft);
  border-top-color: var(--amber);
  border-radius: 50%;
  display: inline-block;
  vertical-align: -1px;
  margin-right: 6px;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.hint {
  min-height: 1.2em;
  color: var(--muted);
  font-size: 0.85rem;
}
.hint.err {
  color: var(--danger);
}
.hint.ok {
  color: var(--ok);
}
```

Note: `.hint` may already exist in the admin CSS — if so, rename the new block to `.admin .hint` scope or merge values; do not create duplicate conflicting selectors.

- [ ] **Step 5: Run all frontend checks** — `npm run test`, `npm run typecheck`, `npm run build` green.
- [ ] **Step 6: Commit + changelog.** Frontend-only restart flag.

---

### Task 5: Admin shell — brand header, counted tabs, toast, scroll page

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`
- Modify: `frontend/src/components/admin/Tabs.tsx` (count badge)
- Modify: `frontend/src/styles/vintage.css` (shell/header/tabs/login modal restyle)
- Tests: `frontend/src/pages/AdminPage.dom.test.tsx`, `frontend/src/components/admin/Tabs.dom.test.tsx`

- [ ] **Step 1: Failing tests**

`Tabs.dom.test.tsx` additions:

```tsx
it("renders a count pill when count is provided", () => {
  render(
    <Tabs
      tabs={[
        { id: "playlists", label: "Playlists", count: 4 },
        { id: "now", label: "Now Playing" },
      ]}
      active="now"
      onChange={() => {}}
    />,
  );
  const tab = screen.getByRole("tab", { name: /Playlists/ });
  expect(within(tab).getByText("4")).toBeInTheDocument();
});
```

`AdminPage.dom.test.tsx` additions:

```tsx
it("renders the brand header", async () => {
  render(<AdminPage />);
  await login();
  const brand = screen.getByText(/Nakout/);
  expect(brand).toBeInTheDocument();
  expect(screen.getByText("Admin")).toBeInTheDocument();
});

it("notice feedback renders as a toast, then clears", async () => {
  vi.useFakeTimers();
  // reuse whatever existing notice-triggering flow the file has (e.g. adding
  // a genre); assert the rendering shows `role=status`, then
  // act(() => { vi.advanceTimersByTime(2300); }) → message gone.
  vi.useRealTimers();
});
```

(Implement the notice-flow step by copying the file's existing "shows a notice after adding a genre" test and swapping its `role="alert" assertion for `role="status"` + timer advancement — keep the genre-add flow identical.)

Existing test updates: "shows the tabs after a successful login" currently asserts tab labels — after counts exist the accessible name becomes "Playlists 4" etc. Update those `getByRole("tab", { name: ... })` lookups to `new RegExp("^Playlists")` style or exact new names. Keep ARIA ids `tab-{id}`/`panel-{id}` unchanged.

- [ ] **Step 2: Implement**

`frontend/src/components/admin/Tabs.tsx` — extend the type and render the pill:

```tsx
export interface TabDef {
  id: string;
  label: string;
  count?: number | null;
}
```

and inside the tab button's label node:

```tsx
        <span>{tab.label}</span>
        {tab.count != null && <span className="count">{tab.count}</span>}
```

`frontend/src/pages/AdminPage.tsx` — state additions + toast wiring:

```tsx
  const [playlistCount, setPlaylistCount] = useState<number | null>(null);
  const [slotCount, setSlotCount] = useState<number | null>(null);

  const TABS: TabDef[] = [
    { id: "now", label: "Now Playing" },
    { id: "playlists", label: "Playlists", count: playlistCount },
    { id: "genres", label: "Genres", count: genres.length },
    { id: "schedule", label: "Schedule", count: slotCount },
  ];
```

(TAB moves inside the component — it needs the counts.) Pass setters down:

```tsx
            {tab === "playlists" && (
              <PlaylistsPanel
                genres={genres}
                onGenresChanged={refreshGenres}
                onNotice={onNotice}
                onError={onError}
                onCountChange={setPlaylistCount}
              />
            )}
...
            {tab === "schedule" && (
              <SchedulePanel
                genres={genres}
                onNotice={onNotice}
                onError={onError}
                onCountChange={setSlotCount}
              />
            )}
```

Replace the notice `<p className="notice banner">` block with `<Toast message={notice} onDone={() => setNotice("")} />`; `onNotice` keeps the same signature (it sets the message). Keep global error banner as is.

Header JSX becomes the reference brand:

```tsx
      <header className="admin-top">
        <div className="brand">
          Nakout<span>.</span>Radio <small>Admin</small>
        </div>
        <div className="top-r">
          <a className="back" href="/">
            &larr; Back to radio
          </a>
          <button type="button" className="btn btn-secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
```

Drop the `admin-fixed` body-class toggling effect and the `admin-shell`/`admin-stable` classes from the ready-phase wrapper (login + checking wrappers get `.admin-page`):

```tsx
  // REMOVE this effect:
  // useEffect(() => {
  //   document.body.classList.toggle("admin-fixed", phase === "ready");
  //   ...
  // }, [phase]);
```

Ready-phase wrapper: `<div className="admin-page">`. Login screen keeps its own form markup; restyle only via classes (`.admin-page .admin-login`).

Skeleton/checking wrappers: replace `admin-stable` with `admin-page`.

- [ ] **Step 3: CSS**

In `vintage.css`, replace the admin shell block (`.admin`, `body.admin-fixed`, `.admin-shell`, `.admin-tabpanel` overrides at lines ~300–432) with:

```css
/* ---------- Admin page (reference shell) ---------- */
.admin-page {
  max-width: 1120px;
  margin: 0 auto;
  display: grid;
  gap: 22px;
  width: 100%;
  padding: 10px 16px 80px;
}
.admin-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.top-r {
  display: flex;
  align-items: center;
  gap: 14px;
}
a.back {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9rem;
}
a.back:hover {
  color: var(--cream);
}
.count {
  font: 500 0.68rem var(--font-mono);
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  color: inherit;
}
.tab.active .count {
  background: rgba(28, 17, 10, 0.2);
}
.admin .panel-head h2,
h2.sec {
  margin: 0;
  font: 500 0.72rem var(--font-mono);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--amber);
}
h3.ttl {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.sub {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 0.95rem;
  max-width: 62ch;
}
.card {
  background: var(--wood);
  border-radius: 14px;
  padding: 18px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
  display: grid;
  gap: 14px;
  min-width: 0;
}
.mono {
  font: 400 0.78rem var(--font-mono);
  color: var(--muted);
  overflow-wrap: anywhere;
}
.chip {
  font: 500 0.72rem var(--font-mono);
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--amber-soft);
  color: var(--amber);
  white-space: nowrap;
}
.chip.warn {
  background: rgba(255, 138, 120, 0.14);
  color: var(--danger);
}
.chip.ok {
  background: rgba(143, 209, 158, 0.14);
  color: var(--ok);
}
.admin .badge {
  font: 500 0.66rem var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--cream);
  color: var(--bg-2);
}
.admin .badge.manual {
  background: var(--amber);
}
.admin .badge.source-schedule,
.admin .badge.source-default {
  background: var(--cream);
}
.admin .badge.source-manual {
  background: var(--amber);
}
.admin .badge.source-none {
  background: var(--wood-light);
  color: var(--muted);
}
```

Leave the old `.admin-*` skeleton/login rules and `.admin-tabs` (restyled er). Adjust `.admin-tabs` to reference pills if not already (it already matches the reference).

Delete the now-dead `body.admin-fixed` and `.admin-shell` rules and the `#panel-playlists`/`#panel-now` scroll overrides they supported (search `admin-fixed` across CSS on this task only).

- [ ] **Step 4: Panel prop stubs** — `PlaylistsPanel`/`SchedulePanel` gain the optional `onCountChange` prop now (default no-op) so the page compiles before Tasks 6/7 wire them:

```tsx
interface Props {
  ...
  onCountChange?: (count: number) => void;
}
```

with `onCountChange?.(added.length)` inside `loadAdded` after `setAdded(...)` (Task 6 formalises), `onCountChange?.(slots.length)` in SchedulePanel's `loadSlots`.

- [ ] **Step 5: Run all frontend checks; fix test fallout** (module tests/test fallout belongs here). `npm run test && npm run typecheck && npm run build`.
- [ ] **Step 6: Commit + changelog** — `git commit -m "feat: admin brand shell, counted tabs, toast feedback"`; frontend-only restart; verification lines.

---

### Task 6: Genres panel — cards, swatches, play now, cross-tab jumps

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx` (jump intents plumbing)
- Modify: `frontend/src/components/admin/GenresPanel.tsx`
- Modify: `frontend/src/styles/vintage.css` (gcard family)
- Tests: `frontend/src/pages/AdminPage.dom.test.tsx`, `frontend/src/components/admin/GenresPanel.dom.test.tsx` (create if absent — the existing genre tests live in AdminPage.dom.test.tsx; keep them working, add dedicated cases here)

Design of cross-tab jumps: `AdminPage` holds

```tsx
  const [playlistIntent, setPlaylistIntent] = useState<number | null>(null);
  const [scheduleIntent, setScheduleIntent] = useState<number | null>(null);
  const jump = (
    nextTab: string,
    intent?: { playlistsGenre?: number; scheduleGenre?: number },
  ) => {
    if (intent?.playlistsGenre != null) setPlaylistIntent(intent.playlistsGenre);
    if (intent?.scheduleGenre != null) setScheduleIntent(intent.scheduleGenre);
    setTab(nextTab);
  };
```

`jump` is passed to GenresPanel as `onJump` and PlaylistsPanel/SchedulePanel receive `initialGenre` (from the intents, consumed once on mount via a `useEffect` keyed by a render-epoch or by `initialGenre != null` then cleared by modelling `initialGenre` as the slot-form default).

- [ ] **Step 1: Failing DOM tests** (new `GenresPanel.dom.test.tsx`, with the api-mock pattern of the AdminPage file):

```tsx
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { GenresPanel } from "./GenresPanel";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, api: { ...actual.api } };
});

const genres = [
  { id: 1, name: "Emo Night", slug: "EN", is_default: false, color: "#f2a33a", track_count: 12 },
  { id: 2, name: "NU Metal", slug: "numetal", is_default: false, color: "#e0654a", track_count: 0 },
];
const noop = () => {};

function renderPanel(overrides: Partial<Parameters<typeof GenresPanel>[0]> = {}) {
  render(
    <GenresPanel
      genres={genres}
      onGenresChanged={async () => {}}
      onNotice={noop}
      onError={noop}
      onJump={overrides.onJump ?? noop}
    />,
  );
}

describe("GenresPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders genre cards with colour, stats and slug", () => {
    renderPanel();
    const card = screen.getByText("Emo Night").closest(".gcard");
    expect(card).not.toBeNull();
    expect(card.querySelector(".st-slug")?.textContent).toBe("/EN");
    expect(within(card).getAllByTestId("chip").some((c) => c.textContent?.includes("12"))).toBe(true);
  });

  it("warns and offers quick actions for an empty genre", () => {
    renderPanel();
    const card = screen.getByText("NU Metal").closest(".gcard");
    expect(card?.textContent).toContain("Add one");
    expect(card?.textContent).toContain("Schedule it");
  });

  it("add form includes a colour swatch row and sends it", async () => {
    const created = vi.fn();
    api.createGenre = created;
    renderPanel();
    fireEvent.change(screen.getByLabelText("Genre name"), { target: { value: "Jazz" } });
    fireEvent.change(screen.getByLabelText("Genre slug"), { target: { value: "jazz" } });
    const swatches = screen.getByRole("radiogroup", { name: "Genre colour" });
    fireEvent.click(within(swatches).getAllByRole("radio")[3]);
    fireEvent.click(screen.getByRole("button", { name: "Add genre" }));
    await waitFor(() =>
      expect(created).toHaveBeenCalledWith("Jazz", "jazz", "#6fa3e0"),
    );
  });

  it("slug auto-fills from the name until manually edited", () => {
    renderPanel();
    const name = screen.getByLabelText("Genre name");
    fireEvent.change(name, { target: { value: "Sunday Acoustic" } });
    expect((screen.getByLabelText("Genre slug") as HTMLInputElement).value).toBe("sundayacoustic");
    fireEvent.change(screen.getByLabelText("Genre slug"), { target: { value: "custom" } });
    fireEvent.change(name, { target: { value: "Something Else" } });
    expect((screen.getByLabelText("Genre slug") as HTMLInputElement).value).toBe("custom");
  });

  it("Play now posts the genre's first track", async () => {
    const tracks = [
      { youtube_video_id: "v1", title: "T", artist: "A", thumbnail_url: "", duration_seconds: 3, position: 0 },
      { youtube_video_id: "v2", title: "T2", artist: "A", thumbnail_url: "", duration_seconds: 3, position: 1 },
    ];
    const genreTracks = vi.fn().mockResolvedValue(tracks);
    const play = vi.fn().mockResolvedValue({ status: "ok" });
    api.genreTracks = genreTracks as unknown as typeof api.genreTracks;
    api.play = play as unknown as typeof api.play;
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Play now Emo Night" }));
    await waitFor(() => expect(genreTracks).toHaveBeenCalledWith(1));
    await waitFor(() => expect(play).toHaveBeenCalledWith(1, "v1"));
  });

  it("edit supports changing the colour", async () => {
    const updated = vi.fn().mockResolvedValue({ ...genres[0], color: "#d8c18a" });
    api.updateGenre = updated as unknown as typeof api.updateGenre;
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /Edit Emo Night/ }));
    const swatches = screen.getAllByRole("radiogroup", { name: "Genre colour" })[0];
    fireEvent.click(within(swatches).getAllByRole("radio")[7]);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(updated).toHaveBeenCalledWith(1, expect.objectContaining({ color: "#d8c18a" })));
  });

  it("jump Planning: no-playlist quick link jumps to playlists with intent", () => {
    const onJump = vi.fn();
    renderPanel({ onJump });
    const card = screen.getByText("NU Metal").closest(".gcard");
    fireEvent.click(within(card).getByText("Add one"));
    expect(onJump).toHaveBeenCalledWith("playlists", { playlistsGenre: 2 });
  });
});
```

NOTE on `data-testid="chip"` — the panel DOM test uses it to grab stat chips; add `data-testid="chip"` to the genre stat chips OR import and filter differently. Simpler: assert `within(card).getAllByText(/track/)`. Keep the test code aligned with what's simplest in the component; do not invent test-only DOM unless needed.

- [ ] **Step 2: Implement the panel**

Rebuild `GenresPanel.tsx` to the reference card grid. Key pieces (keep prop names; add `onJump`):

```tsx
interface Props {
  genres: Genre[];
  onGenresChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onJump?: (
    tab: string,
    intent?: { playlistsGenre?: number; scheduleGenre?: number },
  ) => void;
}
```

State: `name`, `slug`, `slugTouched`, `color`, `editId`, `draft {name, slug, color}`, `pendingDelete`. On name change when `!slugTouched`, slug = `name.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 14)`.

Submit: `api.createGenre(name.trim(), slug.trim(), color)` → clear + `onGenresChanged()` + `onNotice("<name> added. Add a playlist and a schedule slot to put it on air.")`.

Card markup per genre:

```tsx
<article
  key={g.id}
  className={flashId === g.id ? "gcard flash" : "gcard"}
  style={{ "--gc": g.color || "var(--amber)" } as React.CSSProperties}
>
  <div className="gtop">
    <i className="dot big" aria-hidden="true" />
    <div>
      <b>{g.name}</b>
      <span className="mono">/{g.slug}</span>
    </div>
  </div>
  <div className="gstats">
    <span className="chip">{g.track_count} tracks</span>
  </div>
  {totalPlaylists === 0 && (
    <div className="gwarn">
      <span className="chip warn">No playlists</span>
      <button type="button" className="btn-link" onClick={() => onJump?.("playlists", { playlistsGenre: g.id })}>
        Add one
      </button>
      <button type="button" className="btn-link" onClick={() => onJump?.("schedule", { scheduleGenre: g.id })}>
        Schedule it
      </button>
    </div>
  )}
  {g.track_count === 0 && !g.is_default && (
    <div className="gwarn">
      <span className="chip warn">No tracks</span>
    </div>
  )}
  <div className="gact">
    <button type="button" className="btn btn-secondary btn-sm" onClick={() => playGenre(g)} aria-label={`Play now ${g.name}`}>
      Play now
    </button>
    <button type="button" className="btn btn-secondary btn-sm" onClick={() => startEdit(g)}>
      Edit
    </button>
    <button type="button" className="btn btn-danger btn-sm" onClick={() => setPendingDelete(g)}>
      Delete
    </button>
  </div>
</article>
```

(The reference also lists "N playlists" from live playlist data; the app's Genre shape carries only `track_count`. Keep chips to tracks-only + warnings computed as above. "No playlists" warning fires when `track_count === 0`.)

`playGenre`:

```tsx
  const playGenre = async (genre: Genre) => {
    try {
      const tracks = await api.genreTracks(genre.id);
      if (!tracks.length) {
        onError(`"${genre.name}" has no tracks yet. Add a playlist.`);
        return;
      }
      await api.play(genre.id, (tracks[0] as { youtube_video_id: string }).youtube_video_id);
      onNotice(`Now playing ${genre.name}.`);
      onJump?.("now");
    } catch (err) {
      onError(messageFor(err));
    }
  };
```

Edit draft includes `color`; Save sends `{ name, slug, color }` (is_default checkbox stays). The "Genre colour" swatch row in edit does NOT need the Badge of default toggle removal — keep everything else.

- [ ] **Step 3: Cross-panel props in AdminPage** — wire `onJump` to the Genres panel now; Pass `initialGenre={playlistIntent}` to PlaylistsPanel and `initialGenre={scheduleIntent}` to SchedulePanel (both optional; Task 6/7 then consume).

- [ ] **Step 4: CSS for the card family (adapted from reference 155–171)**

```css
.gform {
  display: grid;
  gap: 14px;
}
.gf-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 12px;
}
.pre {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pre span {
  font: 500 1rem var(--font-mono);
  color: var(--muted);
}
.ggrid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.gcard {
  background: var(--wood);
  border-radius: 14px;
  padding: 16px 16px 14px;
  display: grid;
  gap: 12px;
  align-content: start;
  box-shadow: inset 0 3px 0 var(--gc, var(--amber));
  min-width: 0;
  border: 1px solid var(--border);
}
.gtop {
  display: flex;
  gap: 10px;
  align-items: center;
}
.gtop b {
  font-size: 1.1rem;
  display: block;
  overflow-wrap: anywhere;
}
.gstats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.gwarn {
  display: flex;
  gap: 6px 12px;
  flex-wrap: wrap;
  align-items: center;
  font-size: 0.85rem;
}
.gact {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 2px;
}
.gedit {
  display: grid;
  gap: 10px;
}
.btn-link {
  border: 0;
  padding: 0;
  background: none;
  color: var(--amber);
  font-weight: 800;
  text-decoration: underline;
  text-underline-offset: 3px;
  font-size: inherit;
  cursor: pointer;
}
```

- [ ] **Step 5: Run checks** — `npm run test`, `npm run typecheck`, `npm run build`. Update old AdminPage genre tests to the new card selectors (e.g. create-genre still types name/slug then clicks "Add genre" — asserts the toast via role=status if pursuing count tests).
- [ ] **Step 6: Commit + changelog** — `feat: genre cards with colour, play now, cross-tab quick links`; frontend-only.

---

### Task 7: Playlists panel — add card w/ chips, groups, refresh-all, channel grid

**Files:**
- Modify: `frontend/src/components/admin/PlaylistsPanel.tsx`
- Modify: `frontend/src/styles/vintage.css` (groups/browse families)
- Tests: `frontend/src/components/admin/PlaylistsPanel.dom.test.tsx` (new) + keep AdminPage playlist tests green

- [ ] **Step 1: Failing tests** (new `PlaylistsPanel.dom.test.tsx`, mock pattern as in Task 5, api methods: listPlaylists/createPlaylist/refreshPlaylist/deletePlaylist/getChannelSource/setChannelSource/listChannelPlaylists):

```tsx
const genres = [
  { id: 1, name: "Emo Night", slug: "EN", is_default: false, color: "#f2a33a", track_count: 12 },
  { id: 2, name: "From Work Drive", slug: "frm", is_default: false, color: "#6fa3e0", track_count: 3 },
];

const added = [
  {
    id: 11, genre_id: 1, genre_name: "Emo Night",
    youtube_playlist_id: "PLGIA_2k2o8yAAAA", label: "",
    track_count: 56, synced_at: "2026-10-09T10:00:00Z",
  },
  {
    id: 12, genre_id: 2, genre_name: "From Work Drive",
    youtube_playlist_id: "PLGIA_2k2o8yBBBB", label: "Work Drive Mix",
    track_count: 37, synced_at: "2026-10-03T10:00:00Z",
  },
];

describe("PlaylistsPanel", () => {
  beforeEach(() => {
    mocked.listPlaylists.mockResolvedValue(added);
    mocked.getChannelSource.mockResolvedValue({ channel_id: null, title: null });
    mocked.listChannelPlaylists.mockResolvedValue([]);
  });

  it("summarises counts", async () => {
    render(<PlaylistsPanel genres={genres} onGenresChanged={async () => {}} onNotice={noop} onError={noop} />);
    expect(await screen.findByText(/2 playlists · 93 tracks across 2 genres/)).toBeInTheDocument();
  });

  it("groups playlists under genre headers with colours", async () => {
    render(...);
    await screen.findByText("Work Drive Mix");
    const group = screen.getByText("Emo Night").closest(".group");
    expect(group).not.toBeNull();
    expect(within(group).getAllByRole("listitem")).toHaveLength(1);
  });

  it("renders 'Synced X ago' per playlist", async () => {
    render(...);
    expect(await screen.findByText(/Synced just now|Synced \d+[mdh]/)).toBeInTheDocument();
  });

  it("selected genre chip highlights with the genre colour", async () => { ... });

  it("Refresh all fans out to each playlist in the group", async () => {
    mocked.refreshPlaylist.mockResolvedValue({ id: 11, synced: 5 });
    render(...);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh all" }));
    await waitFor(() => expect(mocked.refreshPlaylist).toHaveBeenCalledWith(11));
  });

  it("segmented control swaps link/channel modes", async () => { ... });

  it("adds from a genre chip selection", async () => {
    mocked.createPlaylist.mockResolvedValue({ id: 30, youtube_playlist_id: "PLnew", synced: 7, sync_error: null });
    render(...);
    fireEvent.change(screen.getByLabelText(/YouTube playlist link/i), {
      target: { value: "https://www.youtube.com/playlist?list=PLnew" },
    });
    fireEvent.click(screen.getByText("Emo Night"));
    fireEvent.click(screen.getByRole("button", { name: "Add playlist" }));
    await waitFor(() => expect(mocked.createPlaylist).toHaveBeenCalledWith(1, "https://www.youtube.com/playlist?list=PLnew", ""));
  });

  it("surfaces duplicate link hint", async () => { ... });

  it("initial genre intent preselects the chip", async () => { ... });
});
```

Write all the `render(...)` calls fully in the real file (don't leave `...` — spell them out exactly as in the first test).

- [ ] **Step 2: Implement**

Rebuild `PlaylistsPanel.tsx` as a single scroll column (drop the sidebar grid):

1. Header: `h2.sec` "Playlists" + `.sub` summary: `{added.length} playlist{s} · {totalTracks} tracks across {genres.length} genres. Playlists are re-synced with YouTube when you refresh them.`
2. "Add a playlist" card with `.seg` toggle (two buttons `data-mode="link"/"channel"`, `aria-pressed` states).
3. Link mode: URL input (label "YouTube playlist link") + live hint (duplicate = existing same `youtube_playlist_id` → `.hint.err`; valid link → `.hint.ok` "Playlist ID found: ..."), then `<GenreChipRadio>` for the genre, then Add button (disabled until genre + valid unique link).
4. Channel mode: existing channel logic restyled — setup input/handle → after connect: header (`.mono` title) + Change/Refresh; `ul.channel-grid` of `.channel-card` uses the **real** YouTube thumbnail (`p.thumbnail_url`) with `cssCover(p.title)` fallback:

```tsx
  const cover = p.thumbnail_url
    ? `url("${p.thumbnail_url}")`
    : cssCover(p.title);
```

`already_added` shows `<span className="added-badge">Added to <b>{genre_name}</b></span>` (find the added playlist's genre via `added.find((pl) => pl.youtube_playlist_id === p.youtube_playlist_id)`), else the same genre select + Add button (existing logic).
5. "Your playlists" `.head` (h3.ttl + filtered search input, keep `.filter-input`).
6. Groups: one `.group` per genre (style `--gc`), header `<i className="dot big"/> <b>genre name</b> <span className="mono">N playlist(s) · M tracks</span>` + per-group "Refresh all" button (only when N>0) that fires `api.refreshPlaylist(id)` for each row and reports a combined notice ("Refreshing <genre>...").

```tsx
{groups.map((g) => (
  <section key={g.id} className="group" style={{ "--gc": g.color } as React.CSSProperties}>
    <div className="ghead">
      <i className="dot big" aria-hidden="true" />
      <b>{g.name}</b>
      <span className="mono">
        {g.items.length} {g.items.length === 1 ? "playlist" : "playlists"} ·{" "}
        {g.tracks} tracks
      </span>
      <span className="sp" />
      {g.items.length > 0 && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => refreshMany(g.items.map((pl) => pl.id))}>
          Refresh all
        </button>
      )}
    </div>
    {g.items.length === 0 ? (
      <div className="gempty">
        No playlists yet.{" "}
        <button type="button" className="btn-link" onClick={() => { setMode("link"); setAddGenre(String(g.id)); }}>
          Add one
        </button>
      </div>
    ) : (
      g.items.map((p) => (
        <div key={p.id} className={flashId === p.id ? "prow flash" : "prow"}>
          <div className="pm">
            <a className="pid" href={`https://www.youtube.com/playlist?list=${encodeURIComponent(p.youtube_playlist_id)}`} target="_blank" rel="noreferrer">
              {p.label || p.youtube_playlist_id}
            </a>
            {p.syncing ? (
              <span className="chip"><i className="spin" aria-hidden="true" /> Syncing</span>
            ) : (
              <>
                <span className="chip">{p.track_count} tracks</span>
                <span className="mono">Synced {timeAgo(p.synced_at)}</span>
              </>
            )}
          </div>
          <div className="act">
            <select aria-label={`Genre for ${p.label || p.youtube_playlist_id}`} value={String(p.genre_id)} onChange={(e) => movePlaylist(p, Number(e.target.value))}>
              {genres.map((s) => (<option key={s.id} value={s.id}>{s.name}</option>))}
            </select>
            <button type="button" className="btn btn-secondary btn-sm" disabled={p.syncing} onClick={() => refresh(p.id)}>Refresh</button>
            <button type="button" className="btn btn-danger btn-sm" onClick={() => setPendingRemove(p)}>Remove</button>
          </div>
        </div>
      ))
    )}
  </section>
))}
```

`p.syncing` is local state (`syncingIds: number[]`), move = `api.updateGenre`? NO — move = re-create? There is no "move playlist to another genre" endpoint! Existing API: DELETE + create, or the playlist is created with genre_id only. **Check what `move` can use**: currently via `api.updateGenre`?? No. Actual gap: the current panel has no genre move either (the reference and Task earlier explorer noted rows have Move but the app's AddedPlaylist has no endpoint for moving). Discovery: admin.py has no PUT /playlists/{id}. So implementing move honestly requires a backend change. Options:
1. Add `PUT /studio/playlists/{playlist_id}` accepting `{genre_id}` (5 lines in admin.py; must notify radio).
2. Skip move.

Choose 1 — tiny, keeps the reference feature. Add it in Task 8 (backend touch-up task) or here: **this task needs it**, so include in this task's Step 3 (backend), same tests in the batch: `test_move_playlist_updates_genre`.

```python
class PlaylistUpdate(BaseModel):
    genre_id: int


@router.put("/playlists/{playlist_id}", dependencies=[Depends(require_admin)])
def update_playlist(
    playlist_id: int, body: PlaylistUpdate, session: Session = Depends(get_session)
) -> dict:
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="playlist not found")
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    playlist.genre_id = body.genre_id
    session.add(playlist)
    session.commit()
    notify_radio(session)  # mirror the exact call shape used elsewhere in this file
    return {"status": "updated"}
```

(Verify the existing `notify_radio` call shape — admin.py matters here; match the exact used signature. Same caveat as Task 1.)

7. Empty states: `!filtered.length && filter` → `.empty` "No playlists match '<q>'."; genres nonempty but `added` empty → `.empty` "Create a genre first..." (per-group empties already handle the other cases).

`onCountChange?.(added.length)` inside `loadAdded` (and after create/remove/refresh reload) — completes Task 4's optional prop.

`initialGenre` prop consumed in a mount effect (`useEffect(() => { if (initialGenre != null) { setMode("link"); setAddGenre(String(initialGenre)); } }, [initialGenre])`).

`randomOtherColor`: when adding a new genre, palette default isn't needed here — chips only.

- [ ] **Step 3: Backend move endpoint + test** (as above; run backend suite; include in same commit).
- [ ] **Step 4: CSS (groups + browse, adapted from reference 129–153, 71–81)**

```css
.addlink {
  display: grid;
  gap: 12px;
}
.seg {
  display: inline-flex;
  padding: 4px;
  background: var(--bg-2);
  border-radius: 999px;
  gap: 2px;
}
.seg button {
  border: 0;
  padding: 7px 16px;
  font-weight: 500;
  color: var(--muted);
  background: transparent;
  border-radius: 999px;
  cursor: pointer;
}
.seg button[aria-pressed="true"] {
  background: var(--wood-light);
  color: var(--cream);
  font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--amber);
}
.browse {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}
.pcard {
  display: grid;
  gap: 8px;
  padding: 10px;
  border-radius: 12px;
  background: var(--wood-light);
  min-width: 0;
  align-content: start;
}
.pcard .pc {
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  background-size: cover;
  background-position: center;
  background-color: var(--wood-dark);
}
.pcard b {
  font-size: 0.95rem;
  overflow-wrap: anywhere;
}
.added-badge {
  font-size: 0.85rem;
  color: var(--ok);
}
.groups {
  display: grid;
  gap: 14px;
}
.group {
  background: var(--wood);
  border-radius: 14px;
  padding: 6px 6px 8px;
  min-width: 0;
  border: 1px solid var(--border);
}
.ghead {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  flex-wrap: wrap;
}
.ghead b {
  font-size: 1.05rem;
}
.ghead .sp {
  flex: 1;
}
.prow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--wood-light);
  margin: 0 6px 6px;
  flex-wrap: wrap;
  min-width: 0;
}
.prow .pm {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
}
a.pid {
  color: var(--cream);
  font-weight: 800;
  text-decoration: none;
  overflow-wrap: anywhere;
}
a.pid:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.prow .act {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.prow select {
  width: auto;
  padding: 6px 10px;
  font-size: 0.82rem;
}
.gempty {
  padding: 10px 18px 14px;
  color: var(--muted);
  font-size: 0.9rem;
}
.empty {
  padding: 24px;
  text-align: center;
  border: 1px dashed var(--border-strong);
  border-radius: 12px;
  color: var(--muted);
  font-size: 0.95rem;
  display: grid;
  gap: 10px;
  justify-items: center;
}
```

- [ ] **Step 5: Run checks** (`npm run test`, `typecheck`, `build`, `python -m pytest -q`).
- [ ] **Step 6: Commit + changelog** — `feat: playlists reskin (genre groups, chips, refresh-all, move endpoint)`; backend+frontend restart flags.

---

### Task 8: Schedule panel — on-air card, day pills, timeline, sentence form, day list

**Files:**
- Create: `frontend/src/components/admin/ScheduleTimeline.tsx`
- Modify: `frontend/src/components/admin/SchedulePanel.tsx`
- Modify: `frontend/src/styles/vintage.css` (timeline family)
- Tests: `frontend/src/components/admin/ScheduleTimeline.dom.test.tsx` (new), `frontend/src/components/admin/SchedulePanel.dom.test.tsx` (new), AdminPage slot tests kept green

Conventions: `days_of_week` values are Monday=0..Sunday=6 (match existing `DAY_LABELS`). Now-marker/day-dots follow the browser's local time. Sun-first reference order for pills = `[6, 0, 1, 2, 3, 4, 5]`.

- [ ] **Step 1: Failing tests for the timeline component**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScheduleTimeline } from "./ScheduleTimeline";

// Monday-based day ints (0=Mon). 06:00 slot on weekdays only.
const slots = [
  { id: 1, genre_id: 1, genre_name: "Emo Night", days_of_week: [0, 1, 2, 3, 4], start_time: "06:00" },
  { id: 2, genre_id: 2, genre_name: "NU Metal", days_of_week: [0, 1, 2, 3, 4], start_time: "09:30" },
];

const colors = new Map([
  [1, "#f2a33a"],
  [2, "#e0654a"],
]);

describe("ScheduleTimeline", () => {
  it("renders slot blocks with colour and 12h label", () => {
    render(
      <ScheduleTimeline day={0} slots={slots} colours={colors} nowMinutes={300} onOpenSlot={() => {}} onOpenNew={() => {}} />,
    );
    const emo = screen.getByRole("button", { name: /Emo Night/ });
    expect(emo.style.getPropertyValue("--gc")).toBe("#f2a33a");
    expect(screen.getByText("6:00 AM")).toBeInTheDocument();
  });

  it("shows carry-over marker text for the previous day's last slot", () => {
    // Monday sees Sunday's last...
    render(
      <ScheduleTimeline day={0} slots={[{ ...slots[0], days_of_week: [6] }]} colours={colors} nowMinutes={null} onOpenSlot={() => {}} onOpenNew={() => {}} />,
    );
    expect(screen.getByText(/continues/i)).toBeInTheDocument();
  });

  it("renders Now marker only when nowMinutes is a number", () => {
    const { container } = render(
      <ScheduleTimeline day={0} slots={slots} colours={colors} nowMinutes={300} onOpenSlot={() => {}} onOpenNew={() => {}} />,
    );
    expect(container.querySelector(".nowl")).not.toBeNull();
  });

  it("clicking a slot opens it for edit", () => {
    const onOpenSlot = vi.fn();
    render(<ScheduleTimeline day={0} slots={slots} colours={colors} nowMinutes={null} onOpenSlot={onOpenSlot} onOpenNew={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Emo Night/ }));
    expect(onOpenSlot).toHaveBeenCalledWith(1);
  });

  it("clicking the empty strip opens the new form at a rounded time", () => {
    // click at 25% of the strip ≈ 06:00 (360 min) rounded.
    const onOpenNew = vi.fn();
    const { container } = render(
      <ScheduleTimeline day={0} slots={slots} colours={colors} nowMinutes={null} onOpenSlot={() => {}} onOpenNew={onOpenNew} />,
    );
    const tl = container.querySelector(".tl");
    Object.defineProperty(tl, "getBoundingClientRect", {
      value: () => ({ left: 0, width: 1440, top: 0, right: 1440, bottom: 66, height: 66, x: 0, y: 0, toJSON: () => ({}) }),
    });
    fireEvent.click(tl, { clientX: 822, clientY: 20 });
    expect(onOpenNew).toHaveBeenCalledWith(825); // (822/1440*1440)/30*30 → 822 → round to 30 → 810+ hmm
  });
});
```

Careful with the exact rounding assertion: with width 1440, `clientX: 822` → `822/1440 * 24h * 60 = 822 minutes` → round to nearest 30 → 810 or 840? 822/30 = 27.4 → 27 → 810. Assert `810`. Fix the test expectation to `810` OR pick clientX to a clean multiple of 30 (e.g. 360px → 360min → 360). Use `clientX: 361` → 361/30=12.03→12→360. Assert 360. Update the plan's test accordingly.

- [ ] **Step 2: Implement ScheduleTimeline.tsx**

```tsx
import type { ReactNode } from "react";
import { twelveHour } from "../../utils/format";

export interface TimelineSlot {
  id: number;
  genre_id: number;
  genre_name: string;
  days_of_week: number[];
  start_time: string;
}

interface Seg {
  kind: "slot" | "carry" | "gap";
  from: number;
  to: number;
  slot: TimelineSlot | null;
  carryFromName: string | null;
}

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; // Monday=0
const DAY_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function slotsForDay(all: TimelineSlot[], day: number): TimelineSlot[] {
  return all
    .filter((s) => s.days_of_week.includes(day))
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
}

function mins(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

export function ScheduleTimeline({
  day,
  slots,
  colours,
  nowMinutes,
  onOpenSlot,
  onOpenNew,
}: {
  day: number;
  slots: TimelineSlot[];
  colours: Map<number, string>;
  nowMinutes: number | null;
  onOpenSlot: (id: number) => void;
  onOpenNew: (minute: number) => void;
}) {
  const list = slotsForDay(slots, day);
  const segs: ReactNode[] = [];
  const first = list.length ? mins(list[0].start_time) : 0;

  if (first > 0) {
    let carry: { slot: TimelineSlot; day: number } | null = null;
    for (let off = 1; off <= 7 && !carry; off++) {
      const d = (day - off + 7) % 7;
      const prev = slotsForDay(slots, d);
      if (prev.length) carry = { slot: prev[prev.length - 1], day: d };
    }
    segs.push(
      carry ? (
        <div key="carry" className="blk carry" style={{ left: 0, width: `${(first / 1440) * 100}%`, "--gc": colours.get(carry.slot.genre_id) } as React.CSSProperties}>
          <span className="bn">{carry.slot.genre_name}</span>
          <span className="bt">continues</span>
        </div>
      ) : (
        <div key="gap" className="blk none" style={{ left: 0, width: `${(first / 1440) * 100}%` }}>
          <span className="bn">Nothing scheduled</span>
        </div>
      ),
    );
  }

  list.forEach((s, i) => {
    const from = mins(s.start_time);
    const to = i < list.length - 1 ? mins(list[i + 1].start_time) : 1440;
    segs.push(
      <button
        key={s.id}
        type="button"
        className="blk"
        title={`${s.genre_name} · ${twelveHour(from)} to ${twelveHour(to)}`}
        style={{ left: `${(from / 1440) * 100}%`, width: `${((to - from) / 1440) * 100}%`, "--gc": colours.get(s.genre_id) } as React.CSSProperties}
        onClick={() => onOpenSlot(s.id)}
      >
        <span className="bn">{s.genre_name}</span>
        <span className="bt">{twelveHour(from)}</span>
      </button>,
    );
  });

  return (
    <div className="tlscroll">
      <div className="tlinner">
        <div
          className="tl"
          aria-label={`Timeline for ${DAY_FULL[(day + 6) % 7]}`}
          onClick={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest("button")) return;
            const rect = e.currentTarget.getBoundingClientRect();
            const min = Math.round(((e.clientX - rect.left) / rect.width * 1440) / 30) * 30;
            onOpenNew(Math.min(1410, Math.max(0, min)));
          }}
        >
          {segs}
          {nowMinutes != null && (
            <i className="nowl" style={{ left: `${(nowMinutes / 1440) * 100}%` }}>
              <b>Now</b>
            </i>
          )}
        </div>
        <div className="ticks" aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => i * 3).map((h) => (
            <span key={h} className={h === 0 ? "f" : h === 24 ? "l" : ""} style={{ left: `${(h / 24) * 100}%` }}>
              {twelveHour(h * 60)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Failing tests for the panel** (new `SchedulePanel.dom.test.tsx`; mock listSlots/createSlot/updateSlot/deleteSlot/scheduleNow/now):

```tsx
describe("SchedulePanel", () => {
  const slots = [
    { id: 1, genre_id: 1, genre_name: "Emo Night", days_of_week: [0, 1, 2, 3, 4], start_time: "06:00" },
    { id: 2, genre_id: 2, genre_name: "NU Metal", days_of_week: [0], start_time: "22:00" },
  ];

  beforeEach(() => {
    mocked.listSlots.mockResolvedValue(structuredClone(slots));
    mocked.scheduleNow.mockResolvedValue({
      genre: { ...genres[0] },
      track: null,
      cursor: null,
      source: "schedule",
      offset_seconds: 0,
      server_time: "2026-10-09T04:00:00+00:00",
    });
  });

  it("shows the on-air card with genre and source", async () => {
    render(...);
    expect(await screen.findByText(/On air/)).toBeInTheDocument();
    expect(screen.getByText(/Emo Night/)).toBeInTheDocument();
  });

  it("day pills carry Sun-first order and today-dot exists", async () => {
    render(...);
    const seg = screen.getByRole("group", { name: /Day of the week/i });
    const pills = within(seg).getAllByRole("button");
    expect(pills[0]).toHaveTextContent("Sun");
    const today = new Date().getDay(); // Sunday=0
    const todayLabel = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][today];
    expect(pills.find((p) => p.textContent?.startsWith(todayLabel))?.querySelector(".tdot")).not.toBeNull();
  });

  it("timeline renders for the selected day", async () => {
    render(...);
    expect(await screen.findByRole("button", { name: /Emo Night · 6:00 AM/ })).toBeInTheDocument();
  });

  it("clicking a timeline block opens that slot in the form", async () => {
    render(...);
    fireEvent.click(await screen.findByRole("button", { name: /Emo Night · 6:00 AM/ }));
    expect(await screen.findByText("Edit slot")).toBeInTheDocument();
    expect(screen.getByLabelText(/Start/i)).toHaveValue("06:00");
  });

  it("form shows the sentence preview once genre chosen", async () => {
    render(...);
    fireEvent.click(await screen.findByText("Edit slot") ? screen.getByText("Cancel") : null); // deterministic: open form via pill + "+ Add slot"
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Genre" })).getByText("From Work Drive"));
    expect(screen.getByTestId("sentence")).toHaveTextContent(/will start at/i);
  });

  it("weekday/weekend/every presets set the days", async () => {
    render(...);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    fireEvent.click(screen.getByRole("button", { name: "Weekends" }));
    fireEvent.click(screen.getByRole("button", { name: "Add slot" })); // submit at bottom
    await waitFor(() => expect(mocked.createSlot).toHaveBeenCalledWith(expect.objectContaining({ days_of_week: [5, 6] })));
  });

  it("409 conflict surfaces as an inline error", async () => {
    mocked.createSlot.mockRejectedValue(new ApiError(409, "schedule slot conflict"));
    render(...);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    expect(await screen.findByText(/conflict/i)).toBeInTheDocument();
  });

  it("delete keeps confirm dialog", async () => { ... });
});
```

Spell each render call out fully; drop the awkward "Cancel" disambiguation (open the form with `+ Add slot` only).

- [ ] **Step 4: Implement SchedulePanel rebuild**

Structure:

```tsx
<section className="admin-panel" aria-label="Schedule">
  <h2 className="sec">Schedule</h2>
  <p className="sub">
    Each slot starts a genre, and it plays until the next slot begins.{" "}
    {tzLabel}
  </p>

  <div className="card onair">
    {onAir ? (
      <>
        <span className="led live" aria-hidden="true" />
        <div>
          <div className="big">
            On air: {onAir.genre?.name ?? "Nothing"} …
          </div>
          <div className="next">{nextText}</div>
        </div>
      </>
    ) : (
      <> ... nothing scheduled ... </>
    )}
  </div>

  <div className="head">
    <div className="dayseg" role="group" aria-label="Day of the week">
      {DORDER.map((d) => (
        <button key={d} type="button" className={d === selDay ? "pill active" : "pill"} aria-pressed={d === selDay} onClick={() => setSelDay(d)}>
          {DAY_LABELS[d]}
          {d === todayIdx && <i className="tdot" title="Today" aria-hidden="true" />}
        </button>
      ))}
    </div>
    <button type="button" className="btn btn-primary" onClick={() => openAdd(null)}>
      + Add slot
    </button>
  </div>

  <div className="card">
    <ScheduleTimeline
      day={selDay}
      slots={slots}
      colours={colours}
      nowMinutes={selDay === todayIdx ? nowMinutes : null}
      onOpenSlot={(id) => openEdit(id)}
      onOpenNew={(min) => openAdd(min)}
    />
  </div>

  {formOpen && (
    <form className="card sform" ...> // genre chips, day presets, time, sentence, error, cancel/save
  )}

  <div className="daylist"> // per-segment rows: slot / carry / gap + Add slot button
</section>
```

Data details:
- `colours: Map<number, string>` from `genres`.
- On-air: `useEffect` fetch `api.scheduleNow()` on mount + every 60 s (`setInterval`, clear on unmount). `since`/`next` are computed from `slots` (find today's latest slot with `start_time <= nowHHMM`, else last slot of previous days — same logic as the timeline carry search). For the "since" text use `twelveHour(minutesOf(slot.start_time))`; for next text use the next slot after now (today first, else next days in order) formatted `${gname} at ${twelveHour(mins)} today|tomorrow|<weekday>`.
- `initialGenre` prop: when set and form opened fresh, preselect that genre chip (consume once, keep simple: `useEffect` sets `formGenre` when prop changes to non-null).
- openAdd(minute): `formOpen=true; editId=null; setFormGenre(initialGenre ?? null); setFormDays([selDay]); setFormTime(minuteToHHMM(minute ?? freeStart()))`. `freeStart()`: first free 30-min boundary from 06:00 upward on the selected day (mirror reference `freeTime()`).
- openEdit(id): fill form from the slot (edit mode).
- Sentence via `dayLabel()` (existing `formatDays`) + `twelveHour(mins)` → e.g. `Emo Night will start at 6:00 AM on weekdays and play until the next slot begins.` — `data-testid="sentence"` on the element so tests can target it.
- Submit: create or update endpoints as today; on success `onCountChange?.(updated)`; on 409 → `.hint.err` inline message (already surfaced via onError → adapt to local inline error: `setFormError(messageFor(err))` and render inside the form, keeping the global toast for success only).
- Day list: segments mirror the timeline (`carry` row dim with "continues from <day>", gap row dim with "Add slot" button at that minute → openAdd(min)), slot rows show `time range · genre · <chip duration> · <formatDays repeat>` + Edit/Delete (existing confirm dialog for delete).
- Keep `formatDays()` for repeat labels (already correct with Monday=0).

- [ ] **Step 5: CSS (timeline family, adapted from reference 173–207)**

```css
.onair {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
}
.onair .big {
  font-size: 1.15rem;
  font-weight: 800;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.onair .next {
  color: var(--muted);
  font-size: 0.92rem;
}
.led.live {
  background: var(--led);
  box-shadow: 0 0 10px 2px rgba(255, 74, 58, 0.7);
}
.tlscroll {
  overflow-x: auto;
  padding-bottom: 4px;
}
.tlinner {
  min-width: 640px;
  position: relative;
}
.tl {
  position: relative;
  height: 66px;
  border-radius: 12px;
  background: var(--bg-2);
  overflow: hidden;
  cursor: copy;
  border: 1px solid var(--border);
}
.blk {
  position: absolute;
  top: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  padding: 6px 10px;
  text-align: left;
  border: 0;
  border-radius: 0;
  background: var(--gc, var(--amber));
  color: var(--bg-2);
  overflow: hidden;
  box-shadow: inset -2px 0 0 var(--bg-2);
  min-width: 0;
  cursor: pointer;
  font-family: var(--font-display);
}
.blk:hover:not(:disabled) {
  filter: brightness(1.08);
}
.blk .bn {
  font-weight: 800;
  font-size: 0.85rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.blk .bt {
  font: 500 0.68rem var(--font-mono);
  opacity: 0.75;
  white-space: nowrap;
}
.blk.carry,
.blk.none {
  background: repeating-linear-gradient(135deg, rgba(255, 255, 255, 0.07) 0 6px, transparent 6px 12px);
  color: var(--muted);
}
.blk.carry {
  box-shadow: inset 3px 0 0 var(--gc, var(--amber)), inset -2px 0 0 var(--bg-2);
}
.blk.none {
  box-shadow: inset 0 0 0 1px var(--border);
  cursor: copy;
  pointer-events: none;
}
.nowl {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--led);
  z-index: 2;
  pointer-events: none;
}
.nowl b {
  position: absolute;
  bottom: 3px;
  left: 5px;
  font: 500 0.62rem var(--font-mono);
  background: var(--led);
  color: #fff;
  padding: 1px 5px;
  border-radius: 3px;
}
.ticks {
  position: relative;
  height: 20px;
  margin-top: 8px;
}
.ticks span {
  position: absolute;
  font: 400 0.68rem var(--font-mono);
  color: var(--muted);
  transform: translateX(-50%);
  white-space: nowrap;
}
.ticks span.f {
  transform: none;
}
.ticks span.l {
  transform: translateX(-100%);
}
.sform {
  border: 1px solid var(--amber);
}
.dayseg {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.pill {
  padding: 7px 15px;
  font-weight: 500;
  color: var(--muted);
  border-color: var(--border);
}
.pill[aria-pressed="true"] {
  background: var(--amber);
  color: var(--bg-2);
  border-color: var(--amber);
  font-weight: 800;
}
.pill .tdot {
  position: absolute;
  top: 5px;
  right: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--led);
}
.pill {
  position: relative;
}
.presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.sentence {
  font-size: 1rem;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--bg-2);
  line-height: 1.4;
}
.sentence b {
  color: var(--amber);
}
.dayrow {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.srow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--wood);
  flex-wrap: wrap;
  min-width: 0;
  box-shadow: inset 4px 0 0 var(--gc, var(--border));
}
.srow.dim {
  box-shadow: none;
  background: transparent;
  border: 1px dashed var(--border-strong);
  color: var(--muted);
}
.srow .sm {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}
.srow .tr {
  font: 500 0.82rem var(--font-mono);
  color: var(--cream);
  min-width: 150px;
  font-variant-numeric: tabular-nums;
}
.srow .sa {
  display: flex;
  gap: 8px;
}
```

- [ ] **Step 6: Run checks** — `npm run test`, `typecheck`, `build`.
- [ ] **Step 7: Commit + changelog** — `feat: admin schedule timeline, on-air card, day pills, sentence form`; frontend-only.

---

### Task 9: Now Playing polish to reference markup

**Files:**
- Modify: `frontend/src/components/admin/NowPlayingPanel.tsx`
- Modify: `frontend/src/styles/vintage.css` (only admin-scoped rules)
- Tests: `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` (update assertions that the decorated knobs existed; add `.nowcard` presence)

- [ ] **Step 1: Failing test additions/updates**

In the existing `NowPlayingPanel.dom.test.tsx`:

```tsx
it("renders the reference nowcard layout and drops decorative knobs", () => {
  // render with a playing track...
  expect(document.querySelector(".admin-np-col .nowcard")).not.toBeNull();
  expect(document.querySelector(".knob-row .deck-knob")).toBeNull();
});
```

Replace any existing assertion like `expect(screen.getAllByClassName...)` on the knobs (there was one for the mixer row if contributed earlier; search "deck-knob" in the test file). Also verify the source badge texts still populate (`SOURCE_LABELS`) — assert `[data-testid]`-free but visible in `.admin .badge`.

- [ ] **Step 2: Implement**

- Remove the three `span.deck-knob` elements from the admin mixer block (keep `VolumeKnob`/`VolumeFader` on the public page).
- Rebuild the on-air card as `.nowcard` (admin-scoped): cover 96px left; right column: `h3` title, `.mono` artist, `.meta` row with "Genre: X" (`.mono`) + source badge; `.bar` progress bottom. Keep the existing `livePct` bar mechanics (`role="progressbar"` a11y from the prior work stays!).
- XButton section classes check-up — ensure `Sync all playlists` shows the spinner chip while awaiting the sync response (`syncing` state already exists for it if the panel tracks it — check; add boolean `syncingAll` if absent).

Adjust CSS: keep the existing admin block working (`#panel-now` overrides) with `.nowcard` added under the admin block:

```css
.nowcard {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
  background: var(--wood);
  border-radius: 14px;
  padding: 16px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border);
}
.nowcard .cover {
  width: 96px;
  aspect-ratio: 1;
  border-radius: 4px;
  background-size: cover;
  background-position: center;
  background-color: var(--wood-dark);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.55);
}
.nowcard h3 {
  margin: 0 0 3px;
  font-size: 1.35rem;
  letter-spacing: -0.02em;
  font-weight: 800;
  overflow-wrap: anywhere;
  line-height: 1.1;
}
.nowcard .meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}
```

(and `.bar`/`.bar i`-equivalent if not already present from the existing np-bar — reuse existing `.np-bar/.np-bar-fill` classes and map `.nowcard .bar` to them, or simply keep `.np-bar` and let `.nowcard .np-bar { grid-column: 1 / -1; }` hold.)

- [ ] **Step 3: Run checks** — `npm run test`, `typecheck`, `build`.
- [ ] **Step 4: Commit + changelog** — `fix: now playing nowcard per reference, decorative knobs removed`; frontend-only.

---

### Task 10: Whole-branch review, umbrella changelog, deploy

- [ ] **Step 1: Full verification pass**

- `python -m pytest -q` (backend)
- `npm run test` / `npm run typecheck` / `npm run build` (frontend)
- Cross-check the spec `docs/superpowers/specs/2026-10-09-admin-deck-ui-design.md` item by item.

- [ ] **Step 2: Umbrella changelog entry** at the top summarising the reskin (most-recent-first ordering already handled per-task).

- [ ] **Step 3: Deploy the containers** (`docker compose up -d --build backend frontend`) after user merge.

- [ ] **Step 4: Final UI sweep** on `https://localhost:8010/studio` — login, each tab, colours visible, timeline interaction, toast.

---

## Self-review notes (kept visible on purpose)

- Spec coverage: colours (T1), synced_at (T2), shapes (T3), primitives (T4), shell (T5), genres (T6), playlists (T7), schedule (T8), now-playing (T9), rollout (T10). ☑
- The reference's undo-toasts were dropped by design (user decision); confirm dialogs everywhere instead. ☑
- The reference's "N playlists" chip on genre cards was cut (Genre shape lacks playlist_count; not worth an API roundtrip for one chip). Revisit if the API ever grows `playlist_count`.
- Task 6 depends on Task 5's `onJump` plumbing; Task 4's components are consumed by 6–8 as planned. Task 7 consumes `initialGenre` provided by Task 5's intents.
