# Nakout Radio — Start-Only Schedule — Design Specification

Date: 2026-10-07
Status: Approved for planning

## 1. Overview

Today each schedule slot carries both a start and an end time, and slots are
matched independently: a slot is either "on" or "off", overlaps are resolved by
letting the latest-starting match win, and a slot that crosses midnight needs a
special overnight branch. When no slot matches, the station falls back to the
`is_default` genre.

This change reduces a slot to a **genre plus a start time** on one or more days
of the week. A slot now means "at this moment, switch to this genre." The genre
runs until the next scheduled start, wrapping across midnight and across the
week. Once at least one slot exists the schedule is always on; there is no
"off" state and no overnight special case.

## 2. Goals

- A schedule slot is defined by `genre_id`, `days_of_week`, and `start_time`.
  No end time.
- At any instant the active genre is the genre of the **most recent** scheduled
  start at or before the current local time.
- Transitions work naturally across midnight and across the week boundary.
- The default genre is only used when the schedule is empty, or when the
  scheduled genre has no cached tracks.
- The admin UI no longer asks for an end time.

## 3. Non-Goals

- No "next genre at HH:MM" preview in the public or admin UI (the resolver is
  stateless; there is no exposed rotation object).
- No crossfade, jingle, or any other transition behavior change. Existing
  broadcast logic still finishes the current song before switching.
- No change to how playlists are fetched or how the broadcast clock advances.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Run semantics | A genre runs until the next scheduled start (weekly rotation, always on) |
| End time | Removed from the model, API, and UI entirely |
| Duplicate starts | Disallowed: a slot may not share a start time with another slot on any common day |
| Resolution | Stateless "most recent start wins"; no stored ordering |
| Default genre | Fallback only when the schedule is empty or the scheduled genre has no tracks |

## 5. Architecture

### 5.1 Data model

`ScheduleSlot` (backend/app/models.py) loses `end_time`:

```python
class ScheduleSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    days_of_week: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    start_time: str
```

`days_of_week` keeps its meaning: the days on which the genre **starts**, using
Monday = 0 through Sunday = 6.

### 5.2 Migration

A new Alembic revision drops `end_time` from `scheduleslot` using
`op.batch_alter_table` so it works on SQLite regardless of the SQLite version
(native `ALTER TABLE ... DROP COLUMN` is not assumed). The downgrade re-adds the
column as a non-nullable `String` (existing rows would need a value; the
downgrade is best-effort and documented as such).

Existing slots keep `genre_id`, `days_of_week`, and `start_time`; only the end
time is discarded. This is the accepted behavior change: an existing
`16:07–17:00 Mon–Fri` slot becomes "Classic Rock every weekday from 16:07 until
the next start," which, absent other slots, is effectively continuous.

## 6. Scheduler Algorithm

`backend/app/scheduler.py` replaces `matches()` and the old `resolve_genre_id()`
with a single resolution function. The overnight branch is deleted.

```python
def _most_recent_occurrence(now: datetime, day: int, start: str) -> datetime:
    start_t = _to_time(start)
    days_back = (now.weekday() - day) % 7
    candidate = datetime.combine(
        now.date() - timedelta(days=days_back), start_t, now.tzinfo
    )
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def resolve_genre_id(
    slots: list[Slot], now: datetime, default_id: int | None
) -> int | None:
    best: tuple[datetime, int, int] | None = None  # (occurrence, slot_id, genre)
    for index, (genre_id, days, start) in enumerate(slots):
        for day in days:
            occurrence = _most_recent_occurrence(now, day, start)
            candidate = (occurrence, index, genre_id)
            if best is None or candidate > best:
                best = candidate
    return best[2] if best is not None else default_id
```

`Slot` becomes `tuple[int, list[int], str]` (genre_id, days, start).

Rationale:

- Iterating every `(slot, day)` pair and taking the maximum occurrence gives
  the "most recent start wins" answer directly. A weekday-only slot correctly
  resolves from a previous day's occurrence, which is what produces the
  overnight and week-wrap behavior without a special branch.
- The tie-break key includes the slot's index so the result is deterministic
  even if duplicate starts somehow exist in legacy data. The API prevents
  duplicates going forward.
- `now` is a timezone-aware local datetime (already produced by
  `broadcast._resolve` using `ZoneInfo(settings.genre_tz)`).

### 6.1 Broadcast integration

`broadcast._resolve` builds rows as `(s.genre_id, s.days_of_week, s.start_time)`
instead of including `end_time`, and computes `matched` as "any slot exists."
No other change to `advance()`, `_desired()`, `_snapshot()`, or `_source()`.
`_desired()` keeps its existing fallback: if the resolved genre has no cached
tracks, fall back to the default genre; if that also has none, return the
resolved id.

Because the schedule is always on when a slot exists, `_source()` will report
`"schedule"` whenever the playing genre equals the resolved genre, and
`"default"` when the default genre was substituted (empty schedule or empty
genre).

## 7. API and Validation

`backend/app/schemas.py`:

- `SlotIn`: `genre_id`, `days_of_week` (0–6), `start_time` (`HH:MM`).
- `SlotUpdate`: all three optional.
- `SlotOut`: `id`, `genre_id`, `genre_name`, `days_of_week`, `start_time`.
- Remove all `end_time` fields and drop `end_time` from the time validator's
  field list.

`backend/app/routers/admin.py`:

- `_slot_out` no longer sets `end_time`.
- `create_slot` and `update_slot` validate against duplicate starts. For the
  incoming slot, compare against every other slot (excluding the slot being
  edited) and return **409** with a message like
  `"a slot already starts at 16:07 on Wed"` if any shared day has the same
  `start_time`.
- Dependencies (`require_admin`), response codes, and query ordering are
  unchanged.

## 8. Frontend

- `frontend/src/types.ts`: drop `end_time` from `ScheduleSlot`.
- `frontend/src/api/client.ts`: drop `end_time` from `createSlot` and
  `updateSlot` request bodies.
- `frontend/src/components/admin/SchedulePanel.tsx`:
  - Remove the `end` add-form state and both End inputs (add and edit).
  - Drop `end_time` from the `Draft` interface.
  - The list row shows `from {start_time}` instead of
    `{start_time}–{end_time}`.
  - The delete confirmation message drops the end time.
  - Surface a 409 duplicate-start error inline via the existing `onError`
    path (`messageFor`).

## 9. Testing

Backend (pytest):

- `tests/test_scheduler.py` — rewrite for rotation semantics:
  - inside a run resolves to its genre;
  - before the first start of the day resolves to the previous day's genre
    (week wrap);
  - weekday-only slot still active on a later weekday morning;
  - a later same-day start overrides an earlier one;
  - empty slot list returns the default id.
- `tests/test_admin.py`, `tests/test_models.py`, `tests/test_now.py`,
  `tests/test_genres.py` — drop `end_time` from slot fixtures and add a
  duplicate-start rejection test (create and update returning 409).
- `tests/test_broadcast.py` — unchanged behavior; confirm no regressions.

Frontend (vitest):

- `frontend/src/pages/AdminPage.dom.test.tsx` — remove `end_time` from slot
  mocks; assert the list renders `from HH:MM`.

Verification commands: `pytest` (backend) and `npm test` + `npm run typecheck`
(frontend), matching the existing setup.

## 10. Behavior Change and Rollout

- Existing `end_time` values are permanently dropped by the migration.
- An existing single bounded slot becomes an open-ended weekly rotation.
- Manual ("Auto"/override) broadcast state is independent of this change; the
  resolver only affects the schedule-driven path.
- Container rebuilds required: `backend` (model, scheduler, schemas, router,
  migration) and `frontend` (types, API client, SchedulePanel) — i.e.
  `docker compose up -d --build backend frontend`.
