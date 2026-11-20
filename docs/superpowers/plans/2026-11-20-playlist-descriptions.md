# Nakout Playlist Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each Nakout playlist (genre) an editorial description and show it, with three auto-derived top artists, in a listener-facing modal opened from the live show and Today's schedule.

**Architecture:** `Genre.description` is the single source of truth. The Studio Genres panel edits it. `GET /api/genres/{slug}` returns the description plus a computed `top_artists` list. The radio page opens a small accessible dialog from clickable genre names; no track list is rendered.

**Tech Stack:** FastAPI, SQLModel, Alembic, SQLite, React 18, TypeScript, Vitest, pytest.

---

## File map

Backend:

- `backend/app/models.py` — add `Genre.description`.
- `backend/alembic/versions/e8f9a0b1c2d3_genre_description.py` — new migration.
- `backend/app/routers/admin.py` — accept/save descriptions.
- `backend/app/schemas.py` — expose description, top artists and schedule slug.
- `backend/app/routers/genres.py` — compute top artists and include description.
- `backend/app/routers/schedule.py` — include `genre_slug`.
- `backend/app/routers/now.py` — include description in the on-air genre.
- `backend/tests/test_migration_genre_description.py` — new migration test.
- `backend/tests/test_admin.py` — description write tests.
- `backend/tests/test_genres.py` — description/top-artist response tests.
- `backend/tests/test_schedule_today.py` — slug test plus updated carry expectation.

Frontend:

- `frontend/src/types.ts` — `Genre.description`, `GenreDetail.top_artists`, `SlotToday.genre_slug`.
- `frontend/src/api/client.ts` — description in create/update calls.
- `frontend/src/utils/deck.ts` — carry the slug into schedule rows.
- `frontend/src/components/admin/GenresPanel.tsx` — description editor and card preview.
- `frontend/src/components/PlaylistAboutDialog.tsx` — new modal.
- `frontend/src/pages/RadioPage.tsx` — clickable entry points and dialog state.
- `frontend/src/styles/vintage.css` — textarea, preview, clickable rows and modal styles.
- Tests: `GenresPanel.dom.test.tsx`, `PlaylistAboutDialog.dom.test.tsx`,
  `RadioPage.dom.test.tsx`, `useTodaySchedule.dom.test.ts`, `deck.unit.test.ts`.

Docs:

- `docs/changelog.md` — rollout entry at the end.

---

### Task 1: Genre description column and migration

**Files:**
- Create: `backend/tests/test_migration_genre_description.py`
- Create: `backend/alembic/versions/e8f9a0b1c2d3_genre_description.py`
- Modify: `backend/app/models.py:25-32`

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/test_migration_genre_description.py`:

```python
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic(db_url: str, *args: str) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
        capture_output=True,
    )


def test_genre_description_migration_defaults_empty(tmp_path):
    db_path = tmp_path / "genre-description.db"
    db_url = f"sqlite:///{db_path}"
    _alembic(db_url, "upgrade", "b7c1d2e3f4a5")

    con = sqlite3.connect(db_path)
    con.execute(
        """
        INSERT INTO genre (name, slug, is_default, sort_order, color)
        VALUES ('Jazz', 'jazz', 0, 0, '#f2a33a')
        """
    )
    con.commit()
    con.close()

    _alembic(db_url, "upgrade", "head")

    con = sqlite3.connect(db_path)
    assert con.execute(
        "SELECT description FROM genre WHERE slug = 'jazz'"
    ).fetchone() == ("",)
    columns = {
        row[1]: row for row in con.execute("PRAGMA table_info(genre)")
    }
    assert columns["description"][3] == 1  # notnull flag
    con.close()
```

- [ ] **Step 2: Run the test and watch it fail**

Run from `backend`:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_migration_genre_description.py -v
```

Expected: FAIL — `sqlite3.OperationalError: no such column: description` or
`sqlite3.OperationalError: no such column: description` when selecting.

- [ ] **Step 3: Add the model field**

In `backend/app/models.py`, add `description` after `color`:

```python
class Genre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    is_default: bool = False
    sort_order: int = 0
    color: str | None = Field(default=None)
    description: str = ""
```

- [ ] **Step 4: Add the Alembic migration**

Create `backend/alembic/versions/e8f9a0b1c2d3_genre_description.py`:

```python
"""genre description

Revision ID: e8f9a0b1c2d3
Revises: b7c1d2e3f4a5
Create Date: 2026-11-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.add_column(
            sa.Column(
                "description",
                sa.String(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.drop_column("description")
```

- [ ] **Step 5: Run the migration test**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_migration_genre_description.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```powershell
git add app/models.py alembic/versions/e8f9a0b1c2d3_genre_description.py tests/test_migration_genre_description.py
git commit -m "feat: add genre description column"
```

---

### Task 2: Studio create/update accepts descriptions

**Files:**
- Modify: `backend/app/routers/admin.py:91-104`
- Test: `backend/tests/test_admin.py` (append near the genre tests)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_admin.py`:

```python
def test_create_genre_saves_description(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    resp = client.post(
        "/api/studio/genres",
        json={
            "name": "Jazz",
            "slug": "jazz",
            "description": "Late-night jazz for slow hours.",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "Late-night jazz for slow hours."


def test_update_genre_description_keeps_and_clears(tmp_path):
    client, _ = _client(tmp_path)
    client.post("/api/studio/login", json={"password": "test-pass"})
    gid = client.post(
        "/api/studio/genres",
        json={
            "name": "Jazz",
            "slug": "jazz",
            "description": "First copy.",
        },
    ).json()["id"]

    untouched = client.put(
        f"/api/studio/genres/{gid}", json={"name": "Late Jazz"}
    )
    assert untouched.status_code == 200
    assert untouched.json()["description"] == "First copy."

    cleared = client.put(
        f"/api/studio/genres/{gid}", json={"description": ""}
    )
    assert cleared.status_code == 200
    assert cleared.json()["description"] == ""
```

- [ ] **Step 2: Run the tests and watch them fail**

Run from `backend`:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_admin.py -k "description" -v
```

Expected: FAIL — the response has no `description` key.

- [ ] **Step 3: Add the fields to the admin models**

In `backend/app/routers/admin.py`:

```python
class GenreIn(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    is_default: bool = False
    sort_order: int = 0
    color: str | None = None
    description: str = Field(default="", max_length=500)


class GenreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None
    sort_order: int | None = None
    color: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=500)
```

The existing `Genre(**body.model_dump())` and the `updates` loop in
`update_genre` already persist both fields; no other handler change is needed.

- [ ] **Step 4: Run the tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_admin.py -k "description" -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add app/routers/admin.py tests/test_admin.py
git commit -m "feat: save genre descriptions from Studio"
```

---

### Task 3: Public description, top artists and schedule slug

**Files:**
- Modify: `backend/app/schemas.py:27-38, 183-188`
- Modify: `backend/app/routers/genres.py:93-124`
- Modify: `backend/app/routers/schedule.py:73-99`
- Modify: `backend/app/routers/now.py:15-26`
- Test: `backend/tests/test_genres.py`
- Test: `backend/tests/test_schedule_today.py`

- [ ] **Step 1: Write failing public API tests**

Append to `backend/tests/test_genres.py`:

```python
def test_genre_detail_includes_description_and_top_artists(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = Genre(
            name="Jazz",
            slug="jazz",
            description="Late-night jazz for slow hours.",
        )
        s.add(genre)
        s.commit()
        s.refresh(genre)
        pl = Playlist(genre_id=genre.id, youtube_playlist_id="PLJ")
        s.add(pl)
        s.commit()
        s.refresh(pl)
        rows = [
            ("v1", "A"),
            ("v2", "A"),
            ("v3", "B"),
            ("v4", "B"),
            ("v5", "C"),
            ("v6", "D"),
            ("v7", "   "),
        ]
        for position, (video_id, artist) in enumerate(rows):
            s.add(
                TrackCache(
                    playlist_id=pl.id,
                    youtube_video_id=video_id,
                    title=video_id,
                    artist=artist,
                    position=position,
                )
            )
        s.commit()
    client = _client_from_engine(engine)
    body = client.get("/api/genres/jazz").json()
    assert body["description"] == "Late-night jazz for slow hours."
    assert body["top_artists"] == ["A", "B", "C"]


def test_top_artists_count_distinct_videos_once(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        genre = Genre(name="Rock", slug="rock")
        s.add(genre)
        s.commit()
        s.refresh(genre)
        first = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        second = Playlist(genre_id=genre.id, youtube_playlist_id="PL2")
        s.add(first)
        s.add(second)
        s.commit()
        s.refresh(first)
        s.refresh(second)
        s.add(
            TrackCache(
                playlist_id=first.id,
                youtube_video_id="shared",
                title="Shared",
                artist="A",
                position=0,
            )
        )
        s.add(
            TrackCache(
                playlist_id=first.id,
                youtube_video_id="a-only",
                title="A only",
                artist="A",
                position=1,
            )
        )
        s.add(
            TrackCache(
                playlist_id=second.id,
                youtube_video_id="shared",
                title="Shared",
                artist="A",
                position=0,
            )
        )
        s.add(
            TrackCache(
                playlist_id=second.id,
                youtube_video_id="b-only",
                title="B only",
                artist="B",
                position=1,
            )
        )
        s.commit()
        client = _client_from_engine(engine)
        body = client.get("/api/genres/rock").json()
        assert body["top_artists"] == ["A", "B"]
```

In `backend/tests/test_schedule_today.py`, update the carry expectation:

```python
    assert body["carry"] == {
        "id": night_slot,
        "genre_id": night,
        "genre_name": "Night",
        "genre_slug": "night",
        "start_time": "22:00",
    }
```

Add to `test_today_lists_todays_slots_sorted_with_current`:

```python
    assert body["slots"][0]["genre_slug"] == "morning"
    assert body["slots"][1]["genre_slug"] == "evening"
```

- [ ] **Step 2: Run the tests and watch them fail**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_genres.py tests/test_schedule_today.py -v
```

Expected: FAIL — missing `description`/`top_artists`/`genre_slug` keys.

- [ ] **Step 3: Extend the response schemas**

In `backend/app/schemas.py`:

```python
class GenreOut(BaseModel):
    id: int
    name: str
    slug: str
    is_default: bool
    color: str = ""
    description: str = ""
    track_count: int


class GenreDetail(GenreOut):
    track: TrackOut | None = None
    cursor: str | None = None
    top_artists: list[str] = []
```

And:

```python
class SlotTodayOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    genre_slug: str
    start_time: str
```

- [ ] **Step 4: Add the top-artist helper and response fields**

At the top of `backend/app/routers/genres.py`, add:

```python
from collections import Counter
```

Then after `tracks_for_genre` add:

```python
def top_artists_for_genre(
    session: Session, genre_id: int, limit: int = 3
) -> list[str]:
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for track in tracks_for_genre(session, genre_id):
        name = track.artist.strip()
        if not name:
            continue
        key = name.casefold()
        counts[key] += 1
        display.setdefault(key, name)
    ordered = sorted(counts, key=lambda key: (-counts[key], key))
    return [display[key] for key in ordered[:limit]]
```

In `list_genres`, include the description:

```python
        GenreOut(
            id=s.id,
            name=s.name,
            slug=s.slug,
            is_default=s.is_default,
            color=s.color or "",
            description=s.description,
            track_count=len(tracks_for_genre(session, s.id)),
        )
```

In `get_genre`, include both new fields:

```python
    return GenreDetail(
        id=genre.id,
        name=genre.name,
        slug=genre.slug,
        is_default=genre.is_default,
        color=genre.color or "",
        description=genre.description,
        track_count=total,
        track=track,
        cursor=cursor,
        top_artists=top_artists_for_genre(session, genre.id),
    )
```

- [ ] **Step 5: Include the description in on-air payloads**

In `backend/app/routers/now.py`, add to `GenreOut(...)`:

```python
            color=state.genre.color or "",
            description=state.genre.description,
            track_count=len(tracks_for_genre(session, state.genre.id)),
```

In `backend/app/routers/schedule.py`, add a small helper above
`schedule_today`:

```python
def _slot_today(slot: ScheduleSlot, genres: dict[int, Genre]) -> SlotTodayOut:
    genre = genres.get(slot.genre_id)
    return SlotTodayOut(
        id=slot.id,
        genre_id=slot.genre_id,
        genre_name=genre.name if genre else "",
        genre_slug=genre.slug if genre else "",
        start_time=slot.start_time,
    )
```

Replace the genre-name map and the slot construction in `schedule_today`:

```python
    genres = {g.id: g for g in session.exec(select(Genre)).all()}
    all_slots = session.exec(select(ScheduleSlot)).all()
    today = [
        _slot_today(slot, genres)
        for slot in all_slots
        if weekday in slot.days_of_week
    ]
```

Use the same helper for `carry`:

```python
            carry = _slot_today(previous, genres)
```

And in `schedule_now`, add `description=state.genre.description` to its `GenreOut(...)`.

- [ ] **Step 6: Run the public API tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_genres.py tests/test_schedule_today.py tests/test_now.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add app/schemas.py app/routers/genres.py app/routers/schedule.py app/routers/now.py tests/test_genres.py tests/test_schedule_today.py
git commit -m "feat: expose playlist descriptions and top artists"
```

---

### Task 4: Frontend types, API client and schedule slug plumbing

**Files:**
- Modify: `frontend/src/types.ts:12-24, 95-107`
- Modify: `frontend/src/api/client.ts:168-180`
- Modify: `frontend/src/utils/deck.ts:24-54`
- Test fixtures: `frontend/src/hooks/useTodaySchedule.dom.test.ts`,
  `frontend/src/pages/RadioPage.dom.test.tsx`,
  `frontend/src/utils/deck.unit.test.ts`

- [ ] **Step 1: Add the types**

In `frontend/src/types.ts`:

```ts
export interface Genre {
  id: number;
  name: string;
  slug: string;
  is_default: boolean;
  track_count: number;
  color: string;
  description?: string;
}

export interface GenreDetail extends Genre {
  track: Track | null;
  cursor: string | null;
  top_artists: string[];
}
```

And:

```ts
export interface SlotToday {
  id: number;
  genre_id: number;
  genre_name: string;
  genre_slug: string;
  start_time: string;
}
```

- [ ] **Step 2: Update the API client**

In `frontend/src/api/client.ts`:

```ts
  createGenre: (
    name: string,
    slug: string,
    color?: string,
    description = "",
  ) =>
    request<Genre>("/studio/genres", {
      method: "POST",
      body: JSON.stringify({
        name,
        slug,
        ...(color ? { color } : {}),
        description,
      }),
    }),
  updateGenre: (
    id: number,
    updates: Partial<
      Pick<Genre, "name" | "slug" | "is_default" | "color" | "description">
    >,
  ) =>
    request<Genre>(`/studio/genres/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),
```

- [ ] **Step 3: Carry the slug into schedule rows**

In `frontend/src/utils/deck.ts`:

```ts
export interface ScheduleRow {
  id: number;
  name: string;
  slug: string;
  range: string;
  isNow: boolean;
}
```

In the normal rows map add `slug: slot.genre_slug,`:

```ts
  const rows = today.slots.map((slot, index) => ({
    id: slot.id,
    name: slot.genre_name,
    slug: slot.genre_slug,
    range: slotRange(times, index),
    isNow: today.current_id === slot.id,
  }));
```

In the carry row add `slug: today.carry.genre_slug,`:

```ts
    rows.unshift({
      id: today.carry.id,
      name: today.carry.genre_name,
      slug: today.carry.genre_slug,
      range: first
        ? `${hourLabel(today.carry.start_time)} – ${hourLabel(first)}`
        : hourLabel(today.carry.start_time),
      isNow: today.current_id === today.carry.id,
    });
```

- [ ] **Step 4: Update schedule fixtures for the new field**

In `frontend/src/hooks/useTodaySchedule.dom.test.ts`, add `genre_slug: "morning",` to the `slot` helper.

In `frontend/src/pages/RadioPage.dom.test.tsx`, update `slots`:

```ts
const slots: SlotToday[] = [
  {
    id: 1,
    genre_id: 1,
    genre_name: "Morning",
    genre_slug: "morning",
    start_time: "05:00",
  },
  {
    id: 2,
    genre_id: 2,
    genre_name: "Evening",
    genre_slug: "evening",
    start_time: "17:00",
  },
];
```

In `frontend/src/utils/deck.unit.test.ts`, add slugs to `today.slots`, both carry fixtures
(`genre_slug: "night"`), and add `slug` to every expected row:

```ts
const today = {
  current_id: 2,
  slots: [
    {
      id: 1,
      genre_id: 1,
      genre_name: "Morning",
      genre_slug: "morning",
      start_time: "05:00",
    },
    {
      id: 2,
      genre_id: 2,
      genre_name: "Evening",
      genre_slug: "evening",
      start_time: "17:00",
    },
  ],
};
```

The expected row objects in that file become:

```ts
{ id: 1, name: "Morning", slug: "morning", range: "5 am – 5 pm", isNow: false }
{ id: 2, name: "Evening", slug: "evening", range: "5 pm – 5 am", isNow: true }
{ id: 1, name: "Morning", slug: "morning", range: "5 am", isNow: false }
{ id: 9, name: "Night", slug: "night", range: "10 pm – 5 am", isNow: true }
{ id: 1, name: "Morning", slug: "morning", range: "5 am", isNow: false }
{ id: 9, name: "Night", slug: "night", range: "10 pm", isNow: true }
```

- [ ] **Step 5: Typecheck**

Run from `frontend`:

```powershell
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/types.ts src/api/client.ts src/utils/deck.ts src/hooks/useTodaySchedule.dom.test.ts src/pages/RadioPage.dom.test.tsx src/utils/deck.unit.test.ts
git commit -m "feat: type playlist descriptions and schedule slugs"
```

---

### Task 5: Studio description editor

**Files:**
- Modify: `frontend/src/components/admin/GenresPanel.tsx`
- Modify: `frontend/src/styles/vintage.css`
- Test: `frontend/src/components/admin/GenresPanel.dom.test.tsx`
- Test: `frontend/src/pages/AdminPage.dom.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `GenresPanel.dom.test.tsx`, add a description to the first fixture:

```ts
  {
    id: 1,
    name: "Emo Night",
    slug: "EN",
    is_default: false,
    color: "#f2a33a",
    description: "Heartbreak anthems for the drive home.",
    track_count: 12,
  },
```

In the first test (`renders genre cards...`), add:

```ts
    expect(
      within(card as HTMLElement).getByText(
        "Heartbreak anthems for the drive home.",
      ),
    ).toBeInTheDocument();
```

In the existing `add form sends the chosen colour and reports the notice`
test, insert the description change after the colour swatch click and before
`Add genre`:

```ts
    fireEvent.change(screen.getByLabelText("Genre description"), {
      target: { value: "Rainy-day emo and slow burns." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add genre" }));
```

Replace the existing `toHaveBeenCalledWith("Jazz", "jazz", "#5fb3b3")`
assertion with:

```ts
      expect(mocked.createGenre).toHaveBeenCalledWith(
        "Jazz",
        "jazz",
        "#5fb3b3",
        "Rainy-day emo and slow burns.",
      ),
```

Add a new edit test:

```ts
  it("edits and saves the description", async () => {
    mocked.updateGenre.mockResolvedValue({
      ...genres[0],
      description: "New copy for listeners.",
    });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Edit Emo Night" }));
    const box = screen.getByLabelText(
      "Edit genre description",
    ) as HTMLTextAreaElement;
    expect(box.value).toBe("Heartbreak anthems for the drive home.");
    fireEvent.change(box, {
      target: { value: "New copy for listeners." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(mocked.updateGenre).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ description: "New copy for listeners." }),
      ),
    );
  });
```

Update the two exact call expectations in
`frontend/src/pages/AdminPage.dom.test.tsx`:

```ts
      expect(mocked.createGenre).toHaveBeenCalledWith(
        "Chill",
        "chill",
        "#f2a33a",
        "",
      ),
```

```ts
      expect(mocked.updateGenre).toHaveBeenCalledWith(1, {
        name: "Chillhop",
        slug: "chillhop",
        is_default: true,
        color: "#f2a33a",
        description: "",
      }),
```

- [ ] **Step 2: Run the tests and watch them fail**

Run from `frontend`:

```powershell
npm test -- GenresPanel.dom.test.tsx
```

Expected: FAIL — no description textarea or preview.

- [ ] **Step 3: Add the state and save logic**

In `GenresPanel.tsx`:

```ts
interface Draft {
  name: string;
  slug: string;
  color: string;
  is_default: boolean;
  description: string;
}
```

Add next to the name/slug state:

```ts
  const [description, setDescription] = useState("");
```

In `addGenre`:

```ts
      const created = await api.createGenre(
        trimmedName,
        trimmedSlug,
        color,
        description.trim(),
      );
      setName("");
      setSlug("");
      setDescription("");
```

In `startEdit`:

```ts
    setDraft({
      name: genre.name,
      slug: genre.slug,
      color: genre.color,
      is_default: genre.is_default,
      description: genre.description ?? "",
    });
```

In the initial `draft` state add `description: "",`. In `saveEdit` add:

```ts
        color: draft.color,
        description: draft.description.trim(),
```

- [ ] **Step 4: Add the two textareas and the card preview**

In the **New genre** form, after the `.gf-grid` block:

```tsx
        <label className="field">
          Description
          <textarea
            aria-label="Genre description"
            placeholder="What listeners will hear, in one or two sentences."
            rows={3}
            maxLength={500}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <div className="hint">
          Shown to listeners when they open this playlist.
        </div>
```

In the edit card, after the slug field:

```tsx
                  <label className="field">
                    Description
                    <textarea
                      aria-label="Edit genre description"
                      placeholder="What listeners will hear, in one or two sentences."
                      rows={3}
                      maxLength={500}
                      value={draft.description}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          description: e.target.value,
                        }))
                      }
                    />
                  </label>
                  <div className="hint">
                    Shown to listeners when they open this playlist.
                  </div>
```

In the read-only card, after the `.gtop` block:

```tsx
                {g.description?.trim() && (
                  <p className="gdesc">{g.description}</p>
                )}
```

- [ ] **Step 5: Add the styles**

In `frontend/src/styles/vintage.css`, after the `.field input, .field select` rules:

```css
.field textarea {
  display: block;
  width: 100%;
  margin: 0;
  padding: 11px 13px;
  font-family: var(--font-body);
  font-size: 0.95rem;
  color: var(--cream);
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--field);
  line-height: 1.45;
  resize: vertical;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.field textarea::placeholder {
  color: #75604d;
}

.field textarea:focus {
  border-color: var(--amber-strong);
  box-shadow: 0 0 0 3px var(--amber-soft);
  outline: none;
}
```

After `.gtop .mono`:

```css
.gdesc {
  margin: 0;
  color: var(--muted);
  font-size: 0.85rem;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

In the mobile media query that sets input font sizes, add
`.field textarea` with `font-size: 16px;`:

```css
  .field input:not([type="checkbox"]),
  .field textarea,
  .admin input:not([type="checkbox"]),
  .admin select {
    font-size: 16px;
    min-height: 44px;
  }
```

- [ ] **Step 6: Run the panel tests and typecheck**

```powershell
npm test -- GenresPanel.dom.test.tsx AdminPage.dom.test.tsx
npm run typecheck
```

Expected: both PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/components/admin/GenresPanel.tsx src/styles/vintage.css src/components/admin/GenresPanel.dom.test.tsx
git commit -m "feat: edit playlist descriptions in Studio"
```

---

### Task 6: PlaylistAboutDialog component

**Files:**
- Create: `frontend/src/components/PlaylistAboutDialog.tsx`
- Test: `frontend/src/components/PlaylistAboutDialog.dom.test.tsx`
- Modify: `frontend/src/styles/vintage.css`

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/components/PlaylistAboutDialog.dom.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { GenreDetail } from "../types";
import { PlaylistAboutDialog } from "./PlaylistAboutDialog";

vi.mock("../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: { ...actual.api, getGenre: vi.fn() },
  };
});

const mocked = api as unknown as {
  getGenre: ReturnType<typeof vi.fn>;
};

const detail: GenreDetail = {
  id: 1,
  name: "Emo Night",
  slug: "EN",
  is_default: false,
  color: "#f2a33a",
  description: "Heartbreak anthems for the drive home.",
  track_count: 12,
  track: null,
  cursor: null,
  top_artists: ["Paramore", "Taking Back Sunday", "Jimmy Eat World"],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("PlaylistAboutDialog", () => {
  it("shows the playlist description and top artists without tracks", async () => {
    mocked.getGenre.mockResolvedValue(detail);
    render(<PlaylistAboutDialog slug="EN" onClose={vi.fn()} />);
    expect(await screen.findByText("Emo Night")).toBeInTheDocument();
    expect(
      screen.getByText("Heartbreak anthems for the drive home."),
    ).toBeInTheDocument();
    expect(screen.getByText("Paramore")).toBeInTheDocument();
    expect(screen.getByText("Taking Back Sunday")).toBeInTheDocument();
    expect(
      screen.getByText("Top artists in this playlist"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Track list")).not.toBeInTheDocument();
  });

  it("shows the empty description state and hides empty artists", async () => {
    mocked.getGenre.mockResolvedValue({
      ...detail,
      description: "",
      top_artists: [],
    });
    render(<PlaylistAboutDialog slug="EN" onClose={vi.fn()} />);
    expect(await screen.findByText("No description yet.")).toBeInTheDocument();
    expect(
      screen.queryByText("Top artists in this playlist"),
    ).not.toBeInTheDocument();
  });

  it("closes with Escape, the overlay and the Close button", async () => {
    mocked.getGenre.mockResolvedValue(detail);
    const onClose = vi.fn();
    render(<PlaylistAboutDialog slug="EN" onClose={onClose} />);
    await screen.findByText("Emo Night");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    const overlay = document.querySelector(".modal-overlay");
    if (!overlay) throw new Error("overlay not rendered");
    fireEvent.mouseDown(overlay);
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("shows the request error and retries", async () => {
    mocked.getGenre
      .mockRejectedValueOnce(new ApiError(500, "boom"))
      .mockResolvedValueOnce(detail);
    render(<PlaylistAboutDialog slug="EN" onClose={vi.fn()} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mocked.getGenre).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Paramore")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests and watch them fail**

```powershell
npm test -- PlaylistAboutDialog.dom.test.tsx
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the component**

Create `frontend/src/components/PlaylistAboutDialog.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { GenreDetail } from "../types";
import { messageFor } from "../utils/errors";

interface Props {
  slug: string;
  onClose: () => void;
}

export function PlaylistAboutDialog({ slug, onClose }: Props) {
  const [detail, setDetail] = useState<GenreDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setDetail(await api.getGenre(slug));
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const description = detail?.description?.trim() ?? "";

  return createPortal(
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal-card playlist-about"
        role="dialog"
        aria-modal="true"
        aria-labelledby="playlist-about-title"
      >
        <div
          className="pa-head"
          style={
            { "--gc": detail?.color || "var(--amber)" } as CSSProperties
          }
        >
          <i className="dot big" aria-hidden="true" />
          <h2 id="playlist-about-title" className="modal-title">
            {detail?.name ?? "Playlist"}
          </h2>
        </div>

        {loading ? (
          <p className="muted">Loading playlist…</p>
        ) : error ? (
          <>
            <p className="error banner" role="alert">
              {error}
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void load()}
              >
                Retry
              </button>
            </div>
          </>
        ) : (
          <>
            {description ? (
              <p className="pa-desc">{description}</p>
            ) : (
              <p className="pa-empty">No description yet.</p>
            )}
            {detail && detail.top_artists.length > 0 && (
              <section className="pa-artists">
                <h3>Top artists in this playlist</h3>
                <ul>
                  {detail.top_artists.map((artist) => (
                    <li key={artist} className="chip">
                      {artist}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        <div className="modal-actions">
          <button
            type="button"
            ref={closeRef}
            className="btn btn-secondary"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
```

- [ ] **Step 4: Add the modal styles**

At the end of the modal section in `vintage.css` (after `.modal-actions`):

```css
.playlist-about {
  width: min(520px, 100%);
}

.pa-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pa-head .modal-title {
  margin: 0;
}

.pa-desc {
  margin: 0;
  color: var(--cream);
  font-size: 0.98rem;
  line-height: 1.55;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.pa-empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.95rem;
}

.pa-artists {
  display: grid;
  gap: 8px;
}

.pa-artists h3 {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

.pa-artists ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
```

- [ ] **Step 5: Run the dialog tests and typecheck**

```powershell
npm test -- PlaylistAboutDialog.dom.test.tsx
npm run typecheck
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/components/PlaylistAboutDialog.tsx src/components/PlaylistAboutDialog.dom.test.tsx src/styles/vintage.css
git commit -m "feat: add playlist about dialog"
```

---

### Task 7: Wire the dialog into the radio page

**Files:**
- Modify: `frontend/src/pages/RadioPage.tsx`
- Modify: `frontend/src/styles/vintage.css`
- Test: `frontend/src/pages/RadioPage.dom.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `RadioPage.dom.test.tsx`, add `getGenre: vi.fn()` to the mock and to the
`mocked` type. In `beforeEach`:

```ts
  mocked.getGenre.mockResolvedValue({
    id: 1,
    name: "Morning",
    slug: "morning",
    is_default: true,
    color: "#f2a33a",
    description: "Sunrise songs to start the day.",
    track_count: 1,
    track: null,
    cursor: null,
    top_artists: ["Paramore", "The Cure"],
  });
```

Add tests:

```tsx
  it("opens the playlist about modal from the live kicker", async () => {
    render(<RadioPage />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "About Morning playlist",
      }),
    );
    expect(mocked.getGenre).toHaveBeenCalledWith("morning");
    expect(
      await screen.findByText("Sunrise songs to start the day."),
    ).toBeInTheDocument();
    expect(screen.getByText("Top artists in this playlist")).toBeInTheDocument();
    expect(screen.getByText("Paramore")).toBeInTheDocument();
  });

  it("opens the playlist about modal from a schedule row", async () => {
    mocked.scheduleToday.mockResolvedValue({ current_id: 1, slots });
    mocked.getGenre.mockResolvedValue({
      id: 2,
      name: "Evening",
      slug: "evening",
      is_default: false,
      color: "#e0654a",
      description: "Wind-down records for the evening.",
      track_count: 4,
      track: null,
      cursor: null,
      top_artists: ["C"],
    });
    render(<RadioPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "About Evening playlist" }),
    );
    expect(mocked.getGenre).toHaveBeenCalledWith("evening");
    expect(
      await screen.findByText("Wind-down records for the evening."),
    ).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the tests and watch them fail**

```powershell
npm test -- RadioPage.dom.test.tsx
```

Expected: FAIL — no buttons named `About Morning playlist` / `About Evening playlist`.

- [ ] **Step 3: Add dialog state and the import**

In `RadioPage.tsx`:

```tsx
import { useCallback, useState } from "react";
```

```tsx
import { PlaylistAboutDialog } from "../components/PlaylistAboutDialog";
```

Inside `RadioPage`:

```tsx
  const [aboutSlug, setAboutSlug] = useState<string | null>(null);
  const closeAbout = useCallback(() => setAboutSlug(null), []);
```

- [ ] **Step 4: Make the live kicker clickable**

Replace the existing `<div className="kicker">…</div>` with:

```tsx
                    {genreName ? (
                      <button
                        type="button"
                        className="kicker kicker-btn"
                        aria-label={`About ${genreName} playlist`}
                        onClick={() =>
                          setAboutSlug(state?.genre?.slug ?? null)
                        }
                      >
                        {genreName} · live now
                      </button>
                    ) : (
                      <div className="kicker">Live now</div>
                    )}
```

- [ ] **Step 5: Make the dock genre clickable**

Replace the dock's `<strong>{genreName ?? "Nakout Radio"}</strong>` with:

```tsx
          {genreName ? (
            <button
              type="button"
              className="dj-btn"
              aria-label={`About ${genreName} playlist from the dock`}
              onClick={() => setAboutSlug(state?.genre?.slug ?? null)}
            >
              <strong>{genreName}</strong>
            </button>
          ) : (
            <strong>Nakout Radio</strong>
          )}
```

- [ ] **Step 6: Make each schedule row clickable**

Replace the schedule `<li>` body with:

```tsx
                    <li key={row.id} className={row.isNow ? "now" : undefined}>
                      <button
                        type="button"
                        className="sched-btn"
                        aria-label={`About ${row.name} playlist`}
                        onClick={() => setAboutSlug(row.slug)}
                      >
                        <span>{row.name}</span>
                        <span>{row.range}</span>
                      </button>
                    </li>
```

- [ ] **Step 7: Render the dialog**

Just before the closing `</>` of the page:

```tsx
      {aboutSlug && (
        <PlaylistAboutDialog slug={aboutSlug} onClose={closeAbout} />
      )}
```

- [ ] **Step 8: Add clickable styles**

In `vintage.css`, after `.kicker`:

```css
.kicker-btn {
  display: block;
  width: fit-content;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: none;
  text-align: left;
  cursor: pointer;
}

.kicker-btn:hover,
.kicker-btn:focus-visible {
  color: var(--cream);
  text-decoration: underline;
  text-underline-offset: 3px;
}
```

After the `.dj strong` rules:

```css
.dj-btn {
  display: block;
  min-width: 0;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.dj-btn:hover strong,
.dj-btn:focus-visible strong {
  color: var(--amber);
}
```

After `.sched li.now`:

```css
.sched-btn {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.sched-btn:hover,
.sched-btn:focus-visible {
  color: var(--cream);
}

.sched-btn:focus-visible {
  outline: 2px solid var(--amber);
  outline-offset: 2px;
  border-radius: 6px;
}
```

- [ ] **Step 9: Run the page tests and the full frontend checks**

```powershell
npm test -- RadioPage.dom.test.tsx
npm run typecheck
npm run lint
```

Expected: all PASS.

- [ ] **Step 10: Commit**

```powershell
git add src/pages/RadioPage.tsx src/pages/RadioPage.dom.test.tsx src/styles/vintage.css
git commit -m "feat: open playlist details from the radio page"
```

---

### Task 8: Changelog, verification and pull request

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Run the full backend suite and lint**

From `backend`:

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
```

Expected: ruff clean; all tests pass.

- [ ] **Step 2: Run the full frontend suite and build**

From `frontend`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all pass and the build writes `dist/`.

- [ ] **Step 3: Add the changelog entry**

At the top of `docs/changelog.md` (most recent first), add an entry with
today's date, the summary, files, restart command and verification:

```markdown
## 2026-11-20 — Playlist descriptions for listeners

Nakout playlists (genres) now carry an editorial description and three
automatically chosen top artists. Listeners can open an **About this
playlist** modal from the live show name and from every row in Today's
schedule. The modal never shows the track list.

**Files:** backend model, migration, admin/genres/schedule/now routers and
schemas; backend tests. Frontend types, API client, schedule-row helper,
Genres panel, new `PlaylistAboutDialog`, radio page and styles; frontend
tests.

**Container restart:** Yes — both services changed:
`docker compose up -d --build backend frontend`

**Verification:** `ruff check .` clean; `pytest -q` all pass;
`npm test`, `npm run typecheck`, `npm run lint`, `npm run build` all pass.
```

- [ ] **Step 4: Commit**

```powershell
git add docs/changelog.md
git commit -m "docs: record playlist descriptions"
```

- [ ] **Step 5: Push and open the pull request**

Confirm the GitHub account first:

```powershell
gh auth status
gh auth switch --user xjojoramirez
git push -u origin feat/playlist-descriptions
gh pr create --base main --head feat/playlist-descriptions --title "feat: playlist descriptions for listeners" --body "Adds an editorial description to each Nakout playlist (genre) and an **About this playlist** modal with three auto-derived top artists, opened from the live show and Today's schedule. No track list is shown.

## Container restart
Yes — both services changed: `docker compose up -d --build backend frontend`"
```

The PR body must end with that `Container restart` section.
