# Start-Only Schedule Slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce schedule slots to a genre plus start time so a genre runs until the next scheduled start, wrapping across midnight and the week.

**Architecture:** `ScheduleSlot` loses `end_time`. A single stateless resolver finds the most recent `(day, start)` occurrence at or before now and returns its genre; otherwise the default genre. The broadcast layer feeds that resolver and finishes the current song before switching, exactly as it does today. The admin API rejects duplicate starts, and the admin UI drops the End field.

**Tech Stack:** Python 3 / FastAPI / SQLModel / Alembic / pytest; React 18 / TypeScript / Vite / Vitest.

---

## Spec reference

`docs/superpowers/specs/2026-10-07-schedule-start-time-only-design.md`

## Task 1: Rotation resolver + broadcast wiring

**Files:**
- Modify: `backend/app/scheduler.py` (full rewrite)
- Modify: `backend/app/broadcast.py:20` (import) and `backend/app/broadcast.py:136-140` (`_resolve`)
- Test: `backend/tests/test_scheduler.py` (full rewrite)

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `backend/tests/test_scheduler.py` with:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from app.scheduler import resolve_genre_id

TZ = ZoneInfo("Asia/Manila")


def _dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_resolve_within_run():
    slots = [(1, [0, 1, 2, 3, 4], "06:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 9), default_id=9) == 1  # Mon


def test_empty_slots_returns_default():
    assert resolve_genre_id([], _dt(2026, 1, 5, 9), default_id=9) == 9


def test_later_same_day_start_wins():
    slots = [(1, [0], "06:00"), (2, [0], "12:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 8), default_id=9) == 1
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 13), default_id=9) == 2


def test_before_first_start_wraps_to_previous_week():
    # Monday 03:00 is before Monday 06:00, so the last start was a week ago.
    slots = [(1, [0], "06:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 5, 3), default_id=9) == 1


def test_overnight_wraps_to_previous_day():
    # Monday 22:00 runs into Tuesday early morning.
    slots = [(1, [0], "22:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 6, 1), default_id=9) == 1


def test_weekday_slot_carries_into_weekend():
    # With only a weekday slot, the most recent start on Saturday is Friday's.
    slots = [(1, [0, 1, 2, 3, 4], "06:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 10, 9), default_id=9) == 1  # Sat


def test_most_recent_day_wins():
    slots = [(1, [0], "08:00"), (2, [2], "08:00")]
    assert resolve_genre_id(slots, _dt(2026, 1, 7, 9), default_id=9) == 2  # Wed
    assert resolve_genre_id(slots, _dt(2026, 1, 6, 9), default_id=9) == 1  # Tue
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_genre_id'` is not the failure (it already exists), but the tests fail because the old `resolve_genre_id` expects 4-tuples and `matches`. Old tuple `(1, [0], "06:00")` unpacks to a 3-tuple where the old code reads `s[3]` → `IndexError`.

- [ ] **Step 3: Rewrite `backend/app/scheduler.py`**

Replace the entire file with:

```python
from datetime import datetime, time, timedelta

Slot = tuple[int, list[int], str]  # genre_id, days, start


def _to_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def _most_recent_occurrence(now: datetime, day: int, start: str) -> datetime:
    """Most recent datetime <= now at ``start`` on weekday ``day``.

    Looks back at most one week, so it also covers the case where today's start
    time has not happened yet.
    """
    days_back = (now.weekday() - day) % 7
    candidate = datetime.combine(
        now.date() - timedelta(days=days_back), _to_time(start), now.tzinfo
    )
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def resolve_genre_id(
    slots: list[Slot], now: datetime, default_id: int | None
) -> int | None:
    """Return the genre whose most recent scheduled start is latest at ``now``.

    Returns ``default_id`` when no slot has any applicable start.
    """
    best: tuple[datetime, int, int] | None = None
    for index, (genre_id, days, start) in enumerate(slots):
        for day in days:
            candidate = (_most_recent_occurrence(now, day, start), index, genre_id)
            if best is None or candidate > best:
                best = candidate
    return best[2] if best is not None else default_id
```

- [ ] **Step 4: Update `backend/app/broadcast.py`**

Change the import at line 20 from:

```python
from app.scheduler import matches, resolve_genre_id
```

to:

```python
from app.scheduler import resolve_genre_id
```

Then replace the body of `_resolve` (currently lines 136-140):

```python
    slots = session.exec(select(ScheduleSlot)).all()
    rows = [(s.genre_id, s.days_of_week, s.start_time, s.end_time) for s in slots]
    matched = [s for s in rows if matches(s[1], s[2], s[3], local)]
    genre_id = resolve_genre_id(rows, local, default.id if default else None)
    return genre_id, bool(matched)
```

with:

```python
    slots = session.exec(select(ScheduleSlot)).all()
    rows = [(s.genre_id, s.days_of_week, s.start_time) for s in slots]
    matched = any(days for _, days, _ in rows)
    genre_id = resolve_genre_id(rows, local, default.id if default else None)
    return genre_id, matched
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_scheduler.py tests/test_broadcast.py -v`
Expected: PASS (all scheduler and broadcast tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/scheduler.py backend/app/broadcast.py backend/tests/test_scheduler.py
git commit -m "feat: resolve schedule by most recent start time"
```

---

## Task 2: Drop `end_time` from the model + migration

**Files:**
- Modify: `backend/app/models.py:38-43`
- Create: `backend/alembic/versions/d4e5f6a7b8c9_drop_schedule_end_time.py`
- Test: `backend/tests/test_models.py:36-59`
- Test: `backend/tests/test_migration_station_to_genre.py:100`

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_models.py`, replace `test_schedule_slot_stores_days_list` and `test_schedule_slot_days_round_trip` (lines 36-59) with:

```python
def test_schedule_slot_stores_days_list():
    slot = ScheduleSlot(
        genre_id=1,
        days_of_week=[0, 1, 2, 3, 4],
        start_time="06:00",
    )
    assert slot.days_of_week == [0, 1, 2, 3, 4]


def test_schedule_slot_days_round_trip(session):
    st, _ = _genre_with_playlist(session)
    slot = ScheduleSlot(
        genre_id=st.id,
        days_of_week=[0, 1, 2, 3, 4],
        start_time="06:00",
    )
    session.add(slot)
    session.commit()
    slot_id = slot.id
    session.expire(slot)
    loaded = session.exec(select(ScheduleSlot).where(ScheduleSlot.id == slot_id)).one()
    assert loaded.days_of_week == [0, 1, 2, 3, 4]
    assert not hasattr(loaded, "end_time")
```

In `backend/tests/test_migration_station_to_genre.py`, add after the `indexes` assertion block (before `con.close()`, line 99):

```python
    columns = {r[1] for r in cur.execute("PRAGMA table_info(scheduleslot)")}
    assert "end_time" not in columns
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `assert not hasattr(loaded, "end_time")` fails (the column still exists).

- [ ] **Step 3: Remove `end_time` from the model**

In `backend/app/models.py`, change `ScheduleSlot` (lines 38-43) to:

```python
class ScheduleSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    days_of_week: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    start_time: str
```

- [ ] **Step 4: Create the migration**

Create `backend/alembic/versions/d4e5f6a7b8c9_drop_schedule_end_time.py`:

```python
"""drop schedule end_time

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3c4d5e6
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scheduleslot") as batch_op:
        batch_op.drop_column("end_time")


def downgrade() -> None:
    with op.batch_alter_table("scheduleslot") as batch_op:
        batch_op.add_column(
            sa.Column(
                "end_time", sa.String(), nullable=False, server_default="00:00"
            )
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_models.py tests/test_migration_station_to_genre.py -v`
Expected: PASS. (The migration test writes a legacy row with `end_time`, then `upgrade head` runs the rename migration and this drop; the column is gone.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/d4e5f6a7b8c9_drop_schedule_end_time.py backend/tests/test_models.py backend/tests/test_migration_station_to_genre.py
git commit -m "feat: drop end_time from schedule slots"
```

---

## Task 3: Schemas, admin API, and duplicate-start validation

**Files:**
- Modify: `backend/app/schemas.py:58-112`
- Modify: `backend/app/routers/admin.py` (add `DAY_LABELS`, helper, `create_slot`, `update_slot`, `_slot_out`)
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_admin.py`:

1. Remove `end_time` from the `_create_slot` helper payload (line 189-197):

```python
def _create_slot(client, genre_id, **overrides):
    payload = {
        "genre_id": genre_id,
        "days_of_week": [0],
        "start_time": "06:00",
    }
    payload.update(overrides)
    return client.post("/api/admin/slots", json=payload)
```

2. Add these tests after `test_update_slot_rejects_bad_time` (line 319):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_admin.py -k slot -v`
Expected: FAIL — the new duplicate tests get `201`/`200` instead of `409`, and many existing tests still send `end_time` (which is accepted today, so those pass until schema removal in step 3 — that is fine).

- [ ] **Step 3: Update schemas**

In `backend/app/schemas.py`, replace `SlotIn`, `SlotOut`, and `SlotUpdate` (lines 58-112) with:

```python
class SlotIn(BaseModel):
    genre_id: int
    days_of_week: list[int]
    start_time: str

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int]) -> list[int]:
        if any(d not in range(7) for d in v):
            raise ValueError("days_of_week entries must be 0-6")
        return v

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError as exc:
            raise ValueError("time must be HH:MM") from exc
        return v


class SlotOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    days_of_week: list[int]
    start_time: str


class SlotUpdate(BaseModel):
    genre_id: int | None = None
    days_of_week: list[int] | None = None
    start_time: str | None = None

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and any(d not in range(7) for d in v):
            raise ValueError("days_of_week entries must be 0-6")
        return v

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError as exc:
            raise ValueError("time must be HH:MM") from exc
        return v
```

- [ ] **Step 4: Add duplicate validation and drop `end_time` in the router**

In `backend/app/routers/admin.py`, add a module-level constant after the imports (before the first route/helper), e.g. after line 40:

```python
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
```

Add this helper just above `_slot_out` (currently line 315):

```python
def _assert_unique_start(
    session: Session,
    days: list[int],
    start_time: str,
    exclude_id: int | None = None,
) -> None:
    for other in session.exec(select(ScheduleSlot)).all():
        if exclude_id is not None and other.id == exclude_id:
            continue
        if other.start_time != start_time:
            continue
        shared = sorted(set(other.days_of_week) & set(days))
        if shared:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"a slot already starts at {start_time} "
                    f"on {DAY_LABELS[shared[0]]}"
                ),
            )
```

Replace `_slot_out` (lines 315-323) with:

```python
def _slot_out(slot: ScheduleSlot, genre_names: dict[int, str]) -> SlotOut:
    return SlotOut(
        id=slot.id,
        genre_id=slot.genre_id,
        genre_name=genre_names.get(slot.genre_id, ""),
        days_of_week=slot.days_of_week,
        start_time=slot.start_time,
    )
```

Replace `create_slot` (lines 343-351) with:

```python
def create_slot(body: SlotIn, session: Session = Depends(get_session)) -> SlotOut:
    genre = session.get(Genre, body.genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="genre not found")
    _assert_unique_start(session, body.days_of_week, body.start_time)
    slot = ScheduleSlot(**body.model_dump())
    session.add(slot)
    session.commit()
    session.refresh(slot)
    return _slot_out(slot, {genre.id: genre.name})
```

Replace the validation section of `update_slot` (lines 359-375) with:

```python
def update_slot(
    slot_id: int, body: SlotUpdate, session: Session = Depends(get_session)
) -> SlotOut:
    slot = session.get(ScheduleSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    updates = body.model_dump(exclude_unset=True)
    if updates.get("genre_id") is not None:
        if session.get(Genre, updates["genre_id"]) is None:
            raise HTTPException(status_code=404, detail="genre not found")
    final_days = updates.get("days_of_week", slot.days_of_week)
    final_start = updates.get("start_time", slot.start_time)
    if final_start is not None:
        _assert_unique_start(
            session, final_days or [], final_start, exclude_id=slot_id
        )
    for field, value in updates.items():
        setattr(slot, field, value)
    session.add(slot)
    session.commit()
    session.refresh(slot)
    genre_names = {s.id: s.name for s in session.exec(select(Genre)).all()}
    return _slot_out(slot, genre_names)
```

- [ ] **Step 5: Update the remaining `end_time` usages in the admin tests**

In `backend/tests/test_admin.py`:

- `test_create_slot_unknown_genre_404` payload (lines 179-184): remove the `"end_time": "12:00",` line.
- `test_delete_genre_removes_children` `ScheduleSlot(...)` (line 84-86): remove `end_time="12:00"`.
- `test_list_slots_includes_genre_name_and_fields` (line 228): delete the line `assert body[0]["end_time"] == "12:00"`.
- `test_list_slots_orders_by_id` `ScheduleSlot(...)` (lines 250 and 256): remove `end_time="02:00"` and `end_time="04:00"`.
- `test_update_slot` request body and asserts (lines 277-285): change the PUT body to and assertions to:

```python
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
```

- `test_mutating_endpoints_require_auth` parametrize payload (line 377): change to
  `{"genre_id": 1, "days_of_week": [0], "start_time": "06:00"}`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_admin.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/admin.py backend/tests/test_admin.py
git commit -m "feat: reject duplicate schedule starts and drop end_time from API"
```

---

## Task 4: Update remaining backend fixtures and run the full suite

**Files:**
- Test: `backend/tests/test_now.py:77-116`
- Test: `backend/tests/test_genres.py:90-133`
- Test: `backend/tests/test_now.py` (add end-to-end rotation integration test)

- [ ] **Step 1: Update `test_now.py`**

Replace `test_now_uses_matching_slot` (lines 77-93) with:

```python
def test_now_uses_matching_slot(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        night = _seed_genre(s, "night", video="nv")
        s.add(
            ScheduleSlot(
                genre_id=night.id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                start_time="00:00",
            )
        )
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["source"] == "schedule"
    assert body["genre"]["slug"] == "night"
```

Replace `test_now_falls_back_to_default_when_slot_genre_empty` (lines 96-116) with:

```python
def test_now_falls_back_to_default_when_slot_genre_empty(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        _seed_genre(s, "morning", default=True, video="mv")
        empty = Genre(name="Empty", slug="empty")
        s.add(empty)
        s.commit()
        s.refresh(empty)
        s.add(
            ScheduleSlot(
                genre_id=empty.id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                start_time="00:00",
            )
        )
        s.commit()
    body = _client(engine).get("/api/now").json()
    assert body["genre"]["slug"] == "morning"
    assert body["source"] == "default"
```

- [ ] **Step 2: Add an end-to-end rotation integration test to `test_now.py`**

Append this test (it exercises `get_current` -> `_desired` -> `_resolve` -> `resolve_genre_id` through a real session, proving the schedule actually switches genres at a start boundary). Times are naive UTC; `Asia/Manila` is UTC+8, so `2026-01-04 22:30 UTC` is Monday `06:30` local and `2026-01-05 05:00 UTC` is Monday `13:00` local.

```python
def test_now_switches_between_scheduled_genres(tmp_path):
    engine = _engine(tmp_path)
    every_day = [0, 1, 2, 3, 4, 5, 6]
    with Session(engine) as s:
        alpha = _seed_genre(s, "alpha", video="av")
        beta = _seed_genre(s, "beta", video="bv")
        s.add(
            ScheduleSlot(
                genre_id=alpha.id, days_of_week=every_day, start_time="06:00"
            )
        )
        s.add(
            ScheduleSlot(genre_id=beta.id, days_of_week=every_day, start_time="12:00")
        )
        s.commit()
    with Session(engine) as s:
        morning = get_current(s, datetime(2026, 1, 4, 22, 30))  # Mon 06:30 Manila
        assert morning.genre.slug == "alpha"
        afternoon = get_current(s, datetime(2026, 1, 5, 5, 0))  # Mon 13:00 Manila
        assert afternoon.genre.slug == "beta"
```

- [ ] **Step 3: Update `test_genres.py`**

Replace the two `ScheduleSlot(...)` adds in `test_schedule_now_uses_matching_slot` (lines 110-127) with a single slot:

```python
        # One slot at midnight keeps Night playing all week.
        s.add(
            ScheduleSlot(
                genre_id=night.id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                start_time="00:00",
            )
        )
        s.commit()
```

- [ ] **Step 4: Run the full backend suite**

Run: `python -m pytest -v`
Expected: PASS (no failures, no `end_time` references).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_now.py backend/tests/test_genres.py
git commit -m "test: update remaining fixtures for start-only schedule"
```

---

## Task 5: Frontend types, API client, and SchedulePanel

**Files:**
- Modify: `frontend/src/types.ts:60-67`
- Modify: `frontend/src/api/client.ts:144-166`
- Modify: `frontend/src/components/admin/SchedulePanel.tsx`

- [ ] **Step 1: Update the type**

In `frontend/src/types.ts`, change `ScheduleSlot` to:

```typescript
export interface ScheduleSlot {
  id: number;
  genre_id: number;
  genre_name: string;
  days_of_week: number[];
  start_time: string;
}
```

- [ ] **Step 2: Update the API client**

In `frontend/src/api/client.ts`, replace `createSlot` and `updateSlot` (lines 144-166) with:

```typescript
  createSlot: (slot: {
    genre_id: number;
    days_of_week: number[];
    start_time: string;
  }) =>
    request<ScheduleSlot>("/admin/slots", {
      method: "POST",
      body: JSON.stringify(slot),
    }),
  updateSlot: (
    id: number,
    updates: Partial<{
      genre_id: number;
      days_of_week: number[];
      start_time: string;
    }>,
  ) =>
    request<ScheduleSlot>(`/admin/slots/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),
```

- [ ] **Step 3: Update `SchedulePanel.tsx`**

Remove the end-form state. Replace line 39:

```typescript
  const [start, setStart] = useState("06:00");
  const [end, setEnd] = useState("12:00");
```

with:

```typescript
  const [start, setStart] = useState("06:00");
```

Remove `end_time` from the `Draft` interface (line 20) so it reads:

```typescript
interface Draft {
  genre_id: string;
  days_of_week: number[];
  start_time: string;
}
```

Update the initial draft state (lines 42-47):

```typescript
  const [draft, setDraft] = useState<Draft>({
    genre_id: "",
    days_of_week: [],
    start_time: "",
  });
```

Update `addSlot` (lines 80-85):

```typescript
      await api.createSlot({
        genre_id: Number(genre),
        days_of_week: days,
        start_time: start,
      });
```

Update `startEdit` (lines 95-100):

```typescript
    setDraft({
      genre_id: String(slot.genre_id),
      days_of_week: [...slot.days_of_week],
      start_time: slot.start_time,
    });
```

Update `saveEdit` (lines 106-111):

```typescript
      await api.updateSlot(editId, {
        genre_id: Number(draft.genre_id),
        days_of_week: [...draft.days_of_week].sort((a, b) => a - b),
        start_time: draft.start_time,
      });
```

In the edit form, replace the `time-pair` block (lines 172-201) with just the Start field:

```tsx
              <div className="time-pair">
                <label className="field">
                  Start
                  <input
                    type="time"
                    aria-label="Edit slot start"
                    value={draft.start_time}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        start_time: e.target.value,
                      }))
                    }
                  />
                </label>
              </div>
```

Change the list row label (lines 224-226) to:

```tsx
              <span className="count-pill">from {slot.start_time}</span>
```

In the add form, replace the `time-pair` block (lines 268-285) with:

```tsx
      <div className="time-pair">
        <label className="field">
          Start
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
      </div>
```

Update the delete confirmation message (lines 300-302):

```tsx
          message={`Delete the ${pendingDelete.genre_name} slot (${formatDays(
            pendingDelete.days_of_week,
          )}, from ${pendingDelete.start_time})?`}
```

- [ ] **Step 4: Typecheck**

Run (in `frontend`): `npm run typecheck`
Expected: PASS (no references to `end_time`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts frontend/src/components/admin/SchedulePanel.tsx
git commit -m "feat: remove end time from schedule slot UI"
```

---

## Task 6: Frontend tests

**Files:**
- Test: `frontend/src/pages/AdminPage.dom.test.tsx:359-464`

- [ ] **Step 1: Update the mock data and expectations**

In `frontend/src/pages/AdminPage.dom.test.tsx`:

- `"adds a schedule slot and refreshes the list"` (lines 372-379): change the expected payload to:

```tsx
      expect(mocked.createSlot).toHaveBeenCalledWith({
        genre_id: 1,
        days_of_week: [0, 1, 2, 3, 4],
        start_time: "06:00",
      }),
```

- `"lists schedule slots with genre, days, and time"` (lines 388-397): remove the `end_time: "12:00",` line from the mocked slot.
- In the same test, change the time assertion (line 403) to:

```tsx
    expect(screen.getByText("from 06:00")).toBeInTheDocument();
```

- `"edits a schedule slot"` (lines 411-420): remove the `end_time: "12:00",` line from the mocked slot.
- In the same test, change the expected update payload (lines 431-438) to:

```tsx
      expect(mocked.updateSlot).toHaveBeenCalledWith(5, {
        genre_id: 1,
        days_of_week: [0, 2],
        start_time: "08:00",
      }),
```

- `"deletes a schedule slot after confirmation"` (lines 446-455): remove the `end_time: "12:00",` line from the mocked slot.

- [ ] **Step 2: Run the frontend tests**

Run (in `frontend`): `npm test`
Expected: PASS.

- [ ] **Step 3: Run the typecheck**

Run (in `frontend`): `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/AdminPage.dom.test.tsx
git commit -m "test: update admin schedule slot tests for start-only"
```

---

## Task 7: Changelog and rebuild

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Add the changelog entry**

Prepend to `docs/changelog.md` (after the intro paragraph, before the current top entry):

```markdown
## 2026-10-07 — Start-only schedule slots

- A schedule slot is now just a genre, days of the week, and a start time. The
  genre plays until the next scheduled start, wrapping across midnight and the
  week. The default genre is used only when the schedule is empty or a
  scheduled genre has no cached tracks.
- Removed the per-slot `end_time` (model, migration, API, and admin UI). The
  admin Schedule tab no longer asks for an end time; list rows read
  `from 16:07`. Creating or editing a slot whose start collides with another
  slot on a shared day now returns HTTP 409.
- Files touched:
  - `backend/app/scheduler.py`, `backend/app/broadcast.py`
  - `backend/app/models.py`, `backend/app/schemas.py`,
    `backend/app/routers/admin.py`
  - `backend/alembic/versions/d4e5f6a7b8c9_drop_schedule_end_time.py`
  - `frontend/src/types.ts`, `frontend/src/api/client.ts`,
    `frontend/src/components/admin/SchedulePanel.tsx`
  - `docs/superpowers/specs/2026-10-07-schedule-start-time-only-design.md`
    (docs)
  - `docs/changelog.md` (docs)
- **Container restart required:
  `docker compose up -d --build backend frontend`**
- Verification: `pytest` all pass; `npm test` all pass; `npm run typecheck`
  pass.
```

- [ ] **Step 2: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: changelog for start-only schedule slots"
```

- [ ] **Step 3: Rebuild containers**

Run:

```bash
docker compose up -d --build backend frontend
```

Then open the admin Schedule tab, confirm no End field, and add a slot to verify the rotation.

---

## Self-review notes

- **Spec coverage:** model (Task 2), migration (Task 2), resolver (Task 1), broadcast integration (Task 1), API + duplicate validation (Task 3), frontend (Tasks 5-6), tests (Tasks 1-6), behavior-change/rollout (Task 7). All spec sections map to tasks.
- **Placeholder scan:** no TBD/TODO; every code step contains complete code.
- **Type consistency:** `Slot` is `tuple[int, list[int], str]` everywhere; `resolve_genre_id(slots, now, default_id)` keeps its signature; `_assert_unique_start(session, days, start_time, exclude_id=None)` is used once in create and once in update; the frontend `createSlot`/`updateSlot` shapes match `SlotIn`/`SlotUpdate`.
