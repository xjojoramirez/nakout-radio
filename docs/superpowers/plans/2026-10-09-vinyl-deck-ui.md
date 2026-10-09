# Vinyl Deck UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the listener homepage as the vinyl turntable deck from `UI reference/Nakout Vinyl Deck.html` (minus listener skip/stop), move the whole admin studio onto the same dark theme, and rebuild the admin Now Playing tab as the deck with all of its functionality intact.

**Architecture:** Single global stylesheet takeover (`vintage.css`) switches the site to the dark "vinyl deck" tokens and the Bricolage Grotesque / DM Mono fonts. New presentational components (`TurntableDeck`, `VolumeKnob`) render the deck and an ARIA volume knob. `RadioPage` is rebuilt around them with a Tune in / Tune out mute-control and a today-schedule list fed by a new public backend endpoint `GET /api/schedule/today`. The admin `NowPlayingPanel` reuses the same deck components and keeps every control it has today. No player/broadcast backend logic changes.

**Tech Stack:** React 18 + Vite + TypeScript, plain CSS (`vintage.css`), Vitest + Testing Library; FastAPI + SQLModel (backend), pytest.

**Worktree note:** Work on branch `vinyl-deck-ui` (already checked out). **Never stage `UI reference/` — it stays untracked.** The spec lives at `docs/superpowers/specs/2026-10-09-vinyl-deck-ui-design.md`.

**Commands:**
- Frontend tests: `npm run test` (workdir `frontend`), typecheck+build: `npm run build`
- Backend tests: `python -m pytest -q` (workdir `backend`)

---

### Task 1: Backend — public `GET /api/schedule/today`

**Files:**
- Create: `backend/tests/test_schedule_today.py`
- Modify: `backend/app/schemas.py` (append two models at the end, after `AddedPlaylistOut`-area classes; file currently ends at line ~158 after `ChannelPlaylistOut`)
- Modify: `backend/app/routers/schedule.py`
- Reference conventions: `backend/tests/test_admin.py:12-26` (the `_client` fixture pattern below mirrors it exactly)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_schedule_today.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import create_app

TZ = ZoneInfo("Asia/Manila")  # conftest pins GENRE_TZ


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
    day = datetime.now(TZ).weekday()
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_schedule_today.py -q` (workdir `backend`)
Expected: FAIL — `404 Not Found` for `/api/schedule/today`.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas.py`, append at the end (it currently ends with `ChannelPlaylistOut` around line 143):

```python
class SlotTodayOut(BaseModel):
    id: int
    genre_id: int
    genre_name: str
    start_time: str


class ScheduleTodayOut(BaseModel):
    current_id: int | None = None
    slots: list[SlotTodayOut] = []
```

- [ ] **Step 4: Add the route**

In `backend/app/routers/schedule.py` — add imports at the top (merge with existing ones):

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.broadcast import get_current, utcnow
from app.config import get_settings
from app.db import get_session
from app.models import Genre, ScheduleSlot
from app.routers.genres import tracks_for_genre
from app.schemas import (
    CurrentGenreOut,
    GenreOut,
    ScheduleTodayOut,
    SlotTodayOut,
    TrackOut,
)
```

(The file's current imports are lines 1–9; only add `ZoneInfo`, `select`, `get_settings`, `Genre`, `ScheduleSlot`, `ScheduleTodayOut`, `SlotTodayOut` — keep the existing `get_session` import from `app.db`.)

Append the new route at the bottom of the file:

```python
@router.get("/today", response_model=ScheduleTodayOut)
def schedule_today(session: Session = Depends(get_session)) -> ScheduleTodayOut:
    """Today's schedule slots for the public homepage.

    Slots are filtered by the weekday of ``GENRE_TZ`` and sorted by start
    time. ``current_id`` is the latest slot that already started today, or
    ``None`` when none has (an overnight slot from yesterday governs but is
    not part of today's list).
    """
    tz = ZoneInfo(get_settings().genre_tz)
    now = datetime.now(tz)
    now_str = f"{now.hour:02d}:{now.minute:02d}"
    weekday = now.weekday()
    genre_names = {g.id: g.name for g in session.exec(select(Genre)).all()}
    today = [
        SlotTodayOut(
            id=slot.id,
            genre_id=slot.genre_id,
            genre_name=genre_names.get(slot.genre_id, ""),
            start_time=slot.start_time,
        )
        for slot in session.exec(select(ScheduleSlot)).all()
        if weekday in slot.days_of_week
    ]
    today.sort(key=lambda s: s.start_time)
    started = [s for s in today if s.start_time <= now_str]
    return ScheduleTodayOut(
        current_id=started[-1].id if started else None,
        slots=today,
    )
```

Note: `HH:MM` strings are zero-padded and therefore compare correctly as strings.

- [ ] **Step 5: Run the new tests**

Run: `python -m pytest tests/test_schedule_today.py -q` (workdir `backend`)
Expected: 4 passed.

- [ ] **Step 6: Run the full backend suite**

Run: `python -m pytest -q` (workdir `backend`)
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/schedule.py backend/tests/test_schedule_today.py
git commit -m "feat: public schedule/today endpoint for homepage deck"
```

---

### Task 2: Frontend — schedule/today types, client method, hook

**Files:**
- Modify: `frontend/src/types.ts` (append after `ScheduleSlot`, line 66)
- Modify: `frontend/src/api/client.ts` (add one method to the `api` object, next to `scheduleNow` at line 52)
- Create: `frontend/src/hooks/useTodaySchedule.ts`
- Create: `frontend/src/hooks/useTodaySchedule.dom.test.ts`

- [ ] **Step 1: Add types**

Append to `frontend/src/types.ts`:

```ts
export interface SlotToday {
  id: number;
  genre_id: number;
  genre_name: string;
  start_time: string;
}

export interface ScheduleToday {
  current_id: number | null;
  slots: SlotToday[];
}
```

- [ ] **Step 2: Add the client method**

In `frontend/src/api/client.ts`, inside the `api` object on the line after `now: () => request<BroadcastNow>("/now"),` (line 53):

```ts
  scheduleToday: () => request<ScheduleToday>("/schedule/today"),
```

And extend the type-only import at the top (line 1–11) by adding `ScheduleToday` (and later `SlotToday` too) to the braces:

```ts
import type {
  AddedPlaylist,
  BroadcastNow,
  ChannelPlaylist,
  ChannelSource,
  CurrentGenre,
  Genre,
  GenreDetail,
  ScheduleSlot,
  ScheduleToday,
  SlotToday,
  Track,
} from "../types";
```

- [ ] **Step 3: Write the failing hook test**

Create `frontend/src/hooks/useTodaySchedule.dom.test.ts`:

```ts
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SlotToday } from "../types";
import { api } from "../api/client";
import { REFRESH_MS, useTodaySchedule } from "./useTodaySchedule";

vi.mock("../api/client", () => ({
  api: { scheduleToday: vi.fn() },
}));

const mocked = api as unknown as {
  scheduleToday: ReturnType<typeof vi.fn>;
};

const slot = (id: number): SlotToday => ({
  id,
  genre_id: 1,
  genre_name: "Morning",
  start_time: "05:00",
});

describe("useTodaySchedule", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads the schedule on mount", async () => {
    mocked.scheduleToday.mockResolvedValue({ current_id: 1, slots: [slot(1)] });
    const { result } = renderHook(() => useTodaySchedule());
    await waitFor(() => expect(result.current.today?.current_id).toBe(1));
    await waitFor(() => expect(result.current.today?.slots).toHaveLength(1));
  });

  it("refreshes on an interval", async () => {
    vi.useFakeTimers();
    mocked.scheduleToday.mockResolvedValue({ current_id: null, slots: [] });
    renderHook(() => useTodaySchedule());
    await vi.advanceTimersByTimeAsync(0);
    expect(mocked.scheduleToday).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    expect(mocked.scheduleToday).toHaveBeenCalledTimes(2);
  });

  it("keeps the last good schedule when a refresh fails", async () => {
    vi.useFakeTimers();
    mocked.scheduleToday
      .mockResolvedValueOnce({ current_id: 2, slots: [slot(2)] })
      .mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useTodaySchedule());
    await vi.advanceTimersByTimeAsync(0);
    await waitFor(() => expect(result.current.today?.current_id).toBe(2));
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    expect(result.current.today?.current_id).toBe(2);
  });
});
```

- [ ] **Step 4: Run to verify it fails**

Run: `npm run test -- useTodaySchedule` (workdir `frontend`)
Expected: FAIL — module `./useTodaySchedule` does not exist.

- [ ] **Step 5: Implement the hook**

Create `frontend/src/hooks/useTodaySchedule.ts`:

```ts
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ScheduleToday } from "../types";

export const REFRESH_MS = 5 * 60 * 1000;

export function useTodaySchedule(): { today: ScheduleToday | null } {
  const [today, setToday] = useState<ScheduleToday | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .scheduleToday()
        .then((data) => {
          if (!cancelled) setToday(data);
        })
        .catch(() => {
          // keep the last known schedule; the next tick retries
        });
    };
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { today };
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `npm run test -- useTodaySchedule` (workdir `frontend`)
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts frontend/src/hooks/useTodaySchedule.ts frontend/src/hooks/useTodaySchedule.dom.test.ts
git commit -m "feat: today-schedule fetch + five-minute refresh hook"
```

---

### Task 3: Frontend — fonts + dark theme token takeover

**Files:**
- Modify: `frontend/index.html` (font `<link>`, line 45-48)
- Modify: `frontend/src/styles/vintage.css` — replace `:root` (lines 1–33), then apply the per-rule edits listed below. Values come straight from `UI reference/Nakout Vinyl Deck.html:6-18`.

This task intentionally does not change any TSX markup; all dom tests must still pass because they target roles/text, not colors. Some transient class styling of pages rebuilt in Tasks 5–6 will look mid-flight after this task — that is expected and fixed later.

- [ ] **Step 1: Swap the fonts in `index.html`**

Replace the stylesheet link (lines 45–48):

```html
    <link
      href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,200..800&family=DM+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
```

- [ ] **Step 2: Replace the whole `:root` block (vintage.css lines 1–33)**

```css
:root {
  /* Palette — vinyl deck dark theme */
  --bg-1: #2b1a10;
  --bg-2: #140c07;
  --wood: #2b1a10;
  --wood-light: #3a2416;
  --wood-dark: #17100b;
  --wood-edge: #0d0704;
  --cream: #f1e4d0;
  --cream-soft: #241609;
  --ink: #f1e4d0;
  --muted: #a8917a;
  --amber: #f2a33a;
  --amber-strong: #ffc169;
  --amber-soft: rgba(242, 163, 58, 0.18);
  --vinyl: #0c0807;
  --led: #ff4a3a;
  --danger: #d05b50;
  --danger-soft: rgba(179, 55, 44, 0.2);
  --ok: #8bc79b;
  --ok-soft: rgba(47, 107, 70, 0.24);
  --border: rgba(241, 228, 208, 0.14);
  --border-strong: rgba(241, 228, 208, 0.32);

  /* Type */
  --font-display: "Bricolage Grotesque", "Helvetica Neue", Arial, sans-serif;
  --font-mono: "DM Mono", ui-monospace, Menlo, Consolas, monospace;
  --font-body: "Bricolage Grotesque", system-ui, "Segoe UI", sans-serif;

  /* Shape + depth */
  --radius-sm: 8px;
  --radius: 12px;
  --radius-lg: 20px;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.4);
  --shadow-md: 0 10px 30px rgba(0, 0, 0, 0.5);
  color-scheme: dark;
}
```

- [ ] **Step 3: Headings + selection**

Replace lines 53–70 (`h1,h2,h3` block and `::selection` block) with:

```css
h1,
h2,
h3 {
  font-family: var(--font-display);
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0;
}

:focus-visible {
  outline: 3px solid var(--amber);
  outline-offset: 2px;
}

::selection {
  background: var(--amber);
  color: var(--bg-2);
}
```

- [ ] **Step 4: Buttons and inputs on dark**

Edit `.btn-primary` (lines 95–99) to set an explicit dark-on-amber label:

```css
.btn-primary {
  background: var(--amber);
  color: #1c110a;
  box-shadow: var(--shadow-sm);
}
```

Edit `.btn-primary:hover:not(:disabled)` (lines 101–103):

```css
.btn-primary:hover:not(:disabled) {
  background: var(--amber-strong);
}
```

Edit `.btn-secondary` (lines 105–109):

```css
.btn-secondary {
  background: transparent;
  border-color: var(--border-strong);
  color: var(--cream);
}
```

Edit `.btn-secondary:hover:not(:disabled)` (lines 111–114):

```css
.btn-secondary:hover:not(:disabled) {
  border-color: var(--amber);
  background: rgba(241, 228, 208, 0.08);
}
```

Edit the input rule (lines 151–166) — the `background: #fff;` line becomes `#241609` and `font-family` switches to the mono for the deck look, color to cream:

```css
.field input,
.field select,
.admin input,
.admin select {
  display: block;
  width: 100%;
  margin: 6px 0 0;
  padding: 10px 12px;
  font-family: var(--font-body);
  font-size: 0.95rem;
  color: var(--cream);
  border: 1.5px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: #241609;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
```

Edit `.admin input:focus, .admin select:focus` margin note — only the `outline: none;` body stays as-is (lines 168–173), no change needed beyond tokens.

Edit `.btn-danger` hover body (lines 132–135) to comment out the light soft fill:

```css
.btn-danger:hover:not(:disabled) {
  background: transparent;
  border-color: var(--danger);
}
```

- [ ] **Step 5: Admin card, banners, progress**

Edit `.admin` (lines 534–541):

```css
.admin {
  width: min(1100px, 88vw);
  padding: 28px 32px;
  border-radius: var(--radius-lg);
  background: linear-gradient(160deg, var(--wood-light), var(--wood-dark));
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
}
```

Edit `.admin .error` (lines 185–189) — background/borders now come from tokens, keep:

```css
.admin .error {
  background: var(--danger-soft);
  border: 1px solid rgba(179, 55, 44, 0.35);
  color: var(--danger);
}
```

Edit `.admin .notice` similarly stays token-driven (lines 191–195, no edit needed).

Edit `.progress-track` (lines 331–336):

```css
.progress-track {
  height: 8px;
  border-radius: 4px;
  background: rgba(241, 228, 208, 0.16);
  overflow: hidden;
}
```

- [ ] **Step 6: Skeletons, tabs, modal, lists**

Edit `.skeleton` (lines 627–639):

```css
.skeleton {
  border-radius: var(--radius-sm);
  background:
    linear-gradient(
      100deg,
      rgba(241, 228, 208, 0.05) 35%,
      rgba(241, 228, 208, 0.12) 45%,
      rgba(241, 228, 208, 0.05) 55%
    ),
    var(--cream-soft);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s ease-in-out infinite;
}
```

Edit `.admin-tabs` background (line 948): `rgba(59, 36, 23, 0.08)` → `rgba(241, 228, 208, 0.07)`.

Edit `.modal-overlay` background (line 858): `rgba(20, 10, 4, 0.55)` → `rgba(12, 7, 4, 0.66)`.

Edit `.modal-card` (lines 863–871):

```css
.modal-card {
  width: min(420px, 100%);
  background: var(--cream-soft);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  padding: 20px 22px;
  animation: modal-pop-in 0.15s ease;
}
```

Edit `.modal-message` (lines 879–883) to explicitly color text:

```css
.modal-message {
  margin: 8px 0 18px;
  font-size: 0.95rem;
  overflow-wrap: anywhere;
  color: var(--cream);
}
```

Edit `.badge` (lines 1602–1610):

```css
.badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--amber);
  color: #1c110a;
}
```

Edit `.queue-row.current` (lines 1583–1586):

```css
.queue-row.current {
  background: rgba(241, 228, 208, 0.06);
  border-radius: var(--radius-sm);
}
```

Edit `.back-link:hover` (lines 732–735):

```css
.back-link:hover {
  color: var(--cream);
  background: rgba(241, 228, 208, 0.07);
}
```

Edit `.channel-card` (lines 1127–1135) and its `img` background (line 1142): `background: #fff` → `background: #241609`; `background: rgba(59, 36, 23, 0.08)` → `background: rgba(241, 228, 208, 0.06)`.

Edit `.genre-admin-list li.slot-editing` (lines 1223–1231): `background: #fff;` → `background: #241609;`.

Edit the two scrollbar thumbs (lines 1113–1116 and 1569–1572): `background: rgba(59, 36, 23, 0.25)` → `background: rgba(241, 228, 208, 0.22)`.

Edit `.channel-scroll::-webkit-scrollbar` width stays; no other change.

- [ ] **Step 7: Verify**

Run: `npm run test` (workdir `frontend`) — Expected: all existing dom tests pass.
Run: `npm run build` (workdir `frontend`) — Expected: succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/index.html frontend/src/styles/vintage.css
git commit -m "style: vinyl deck dark tokens + Bricolage/DM Mono takeover"
```

---

### Task 4: Frontend — deck CSS + `TurntableDeck` + `VolumeKnob`

**Files:**
- Modify: `frontend/src/styles/vintage.css` (append the "Vinyl deck" section before the `/* ---------- Mobile` block, i.e. before line 1272)
- Create: `frontend/src/components/deck/TurntableDeck.tsx`
- Create: `frontend/src/components/deck/TurntableDeck.dom.test.tsx`
- Create: `frontend/src/components/deck/VolumeKnob.tsx`
- Create: `frontend/src/components/deck/VolumeKnob.dom.test.tsx`

- [ ] **Step 1: Write the failing `VolumeKnob` test**

Create `frontend/src/components/deck/VolumeKnob.dom.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VolumeKnob } from "./VolumeKnob";

describe("VolumeKnob", () => {
  it("has slider semantics and reports its value", () => {
    render(<VolumeKnob value={50} onChange={() => {}} label="Volume" />);
    const knob = screen.getByRole("slider", { name: "Volume" });
    expect(knob).toHaveAttribute("aria-valuemin", "0");
    expect(knob).toHaveAttribute("aria-valuemax", "100");
    expect(knob).toHaveAttribute("aria-valuenow", "50");
  });

  it("changes value with arrow keys", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
    });
    expect(onChange).toHaveBeenLastCalledWith(52);
  });

  it("uses shift for bigger keyboard steps", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
      shiftKey: true,
    });
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it("drags vertically to change value", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={50} onChange={onChange} label="Volume" />);
    const knob = screen.getByRole("slider", { name: "Volume" });
    fireEvent.pointerDown(knob, { pointerId: 1, clientY: 100 });
    fireEvent.pointerMove(knob, { pointerId: 1, clientY: 80 });
    fireEvent.pointerUp(knob, { pointerId: 1, clientY: 80 });
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it("clamps to 0-100", () => {
    const onChange = vi.fn();
    render(<VolumeKnob value={100} onChange={onChange} label="Volume" />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
    });
    expect(onChange).toHaveBeenLastCalledWith(100);
  });

  it("ignores keys when disabled", () => {
    const onChange = vi.fn();
    render(
      <VolumeKnob value={50} onChange={onChange} label="Volume" disabled />,
    );
    fireEvent.keyDown(screen.getByRole("slider", { name: "Volume" }), {
      key: "ArrowUp",
    });
    expect(onChange).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm run test -- VolumeKnob` (workdir `frontend`)
Expected: FAIL — cannot resolve `./VolumeKnob`.

- [ ] **Step 3: Implement `VolumeKnob`**

Create `frontend/src/components/deck/VolumeKnob.tsx`:

```tsx
import {
  useRef,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

interface Props {
  value: number;
  onChange: (value: number) => void;
  label: string;
  disabled?: boolean;
}

function clamp(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

export function VolumeKnob({ value, onChange, label, disabled }: Props) {
  const dragRef = useRef<{ startY: number; startValue: number } | null>(null);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    dragRef.current = { startY: event.clientY, startValue: value };
    if (typeof event.currentTarget.setPointerCapture === "function") {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const drag = dragRef.current;
    if (!drag) return;
    onChange(clamp(drag.startValue + (drag.startY - event.clientY) / 2));
  };

  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const step = event.shiftKey ? 10 : 2;
    let next: number | null = null;
    if (event.key === "ArrowUp" || event.key === "ArrowRight") {
      next = value + step;
    } else if (event.key === "ArrowDown" || event.key === "ArrowLeft") {
      next = value - step;
    } else if (event.key === "PageUp") {
      next = value + 10;
    } else if (event.key === "PageDown") {
      next = value - 10;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = 100;
    }
    if (next === null) return;
    event.preventDefault();
    onChange(clamp(next));
  };

  const angle = -135 + (value / 100) * 270;

  return (
    <div
      className={disabled ? "deck-knob interactive disabled" : "deck-knob interactive"}
      role="slider"
      tabIndex={disabled ? -1 : 0}
      aria-label={label}
      aria-disabled={disabled || undefined}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      aria-valuetext={`${value}%`}
      style={{ "--r": `${angle.toFixed(1)}deg` } as CSSProperties}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onKeyDown={onKeyDown}
    />
  );
}
```

- [ ] **Step 4: Run the knob tests**

Run: `npm run test -- VolumeKnob` (workdir `frontend`)
Expected: 6 passed.

- [ ] **Step 5: Write the failing `TurntableDeck` test**

Create `frontend/src/components/deck/TurntableDeck.dom.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TurntableDeck } from "./TurntableDeck";

describe("TurntableDeck", () => {
  it("puts the cover art on the record label", () => {
    const { container } = render(
      <TurntableDeck playing={false} artUrl="http://img/cover.png" />,
    );
    const label = container.querySelector(".deck .label") as HTMLElement;
    expect(label).not.toBeNull();
    expect(label.style.backgroundImage).toContain("cover.png");
  });

  it("toggles playing state for arm + spin classes", () => {
    const { container, rerender } = render(
      <TurntableDeck playing={false} artUrl={null} />,
    );
    const deck = container.querySelector(".deck") as HTMLElement;
    expect(deck.classList.contains("playing")).toBe(false);
    rerender(<TurntableDeck playing artUrl={null} />);
    expect(deck.classList.contains("playing")).toBe(true);
  });
});
```

- [ ] **Step 6: Run to verify failure**

Run: `npm run test -- TurntableDeck` (workdir `frontend`)
Expected: FAIL — cannot resolve `./TurntableDeck`.

- [ ] **Step 7: Implement `TurntableDeck`**

Create `frontend/src/components/deck/TurntableDeck.tsx`:

```tsx
import { useEffect, useRef } from "react";

interface Props {
  playing: boolean;
  artUrl: string | null;
}

/** 33 and a third RPM = 200 deg/sec, with spin-up / spin-down inertia. */
const DEG_PER_SECOND = 200;

export function TurntableDeck({ playing, artUrl }: Props) {
  const recordRef = useRef<HTMLDivElement | null>(null);
  const angleRef = useRef(0);
  const playingRef = useRef(playing);
  playingRef.current = playing;

  useEffect(() => {
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    let raf = 0;
    let last = performance.now();
    let omega = 0;
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const target = playingRef.current ? DEG_PER_SECOND : 0;
      omega +=
        (target - omega) * Math.min(1, dt * (playingRef.current ? 1.6 : 1.1));
      if (Math.abs(omega) < 0.2 && target === 0) omega = 0;
      angleRef.current = (angleRef.current + omega * dt) % 360;
      const el = recordRef.current;
      if (el) {
        el.style.transform = `rotate(${angleRef.current.toFixed(2)}deg)`;
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className={playing ? "deck playing" : "deck"}>
      <div className="platter">
        <div className="record" ref={recordRef}>
          <div
            className="label"
            style={
              artUrl ? { backgroundImage: `url(${artUrl})` } : undefined
            }
          />
        </div>
        <div className="sheen" />
      </div>
      <div className="pivot" />
      <div className="arm" />
      <div className="deck-rpm" aria-hidden="true">
        <b className="on">33</b>
        <b>45</b>
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Append the deck CSS**

In `frontend/src/styles/vintage.css`, insert this entire section directly before the `/* ---------- Mobile: phones (≤600px) ---------- */` comment (currently at line 1272):

```css
/* ---------- Vinyl deck (reference: Nakout Vinyl Deck.html) ---------- */

.radio-page {
  width: min(1080px, 96vw);
  display: grid;
  gap: 24px;
  color: var(--cream);
}

.radio-page.offline {
  filter: saturate(0.6) brightness(0.85);
}

.radio-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.brand {
  font-family: var(--font-display);
  font-weight: 800;
  font-size: 1.5rem;
  letter-spacing: -0.02em;
}

.brand span {
  color: var(--amber);
}

.onair {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

.led {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #4a2a22;
  transition: background 0.3s, box-shadow 0.3s;
}

.led.on {
  background: var(--led);
  box-shadow: 0 0 10px 2px rgba(255, 74, 58, 0.7);
}

.deck-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 32px;
  align-items: start;
}

.deck {
  position: relative;
  aspect-ratio: 1.15 / 1;
  width: 100%;
  border-radius: 18px;
  background: linear-gradient(145deg, var(--wood-light), var(--wood) 60%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.07),
    0 24px 50px rgba(0, 0, 0, 0.5);
}

.platter {
  position: absolute;
  left: 4%;
  top: 7.5%;
  width: 74%;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #17100b;
  box-shadow: 0 0 0 6px #120c08, 0 10px 30px rgba(0, 0, 0, 0.6);
}

.record {
  position: absolute;
  inset: 4%;
  border-radius: 50%;
  will-change: transform;
  background:
    repeating-radial-gradient(
      circle at center,
      rgba(255, 255, 255, 0.035) 0 1px,
      transparent 1px 3px
    ),
    radial-gradient(circle at center, #1b1411 0 40%, var(--vinyl) 41% 100%);
}

.record::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(
    circle at center,
    transparent 0 41%,
    rgba(0, 0, 0, 0.55) 41.5% 42.5%,
    transparent 43%
  );
}

.record .label {
  position: absolute;
  inset: 31%;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.5);
}

.record .label::after {
  content: "";
  position: absolute;
  left: 50%;
  top: 50%;
  width: 9%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: #0c0807;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.25);
}

.sheen {
  position: absolute;
  inset: 4%;
  border-radius: 50%;
  pointer-events: none;
  background: conic-gradient(
    from 20deg,
    transparent 0 8%,
    rgba(255, 255, 255, 0.13) 14%,
    transparent 22% 58%,
    rgba(255, 255, 255, 0.1) 64%,
    transparent 72%
  );
}

.pivot {
  position: absolute;
  left: 88%;
  top: 11.5%;
  width: 9%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #6b5646, #241812 70%);
  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.5);
}

.arm {
  position: absolute;
  left: 88%;
  top: 11.5%;
  width: 10px;
  height: 60%;
  margin-left: -5px;
  transform-origin: 50% 0;
  transform: rotate(-4deg);
  transition: transform 1.3s cubic-bezier(0.45, 0.05, 0.25, 1);
}

.deck.playing .arm {
  transform: rotate(26deg);
}

.arm::before {
  content: "";
  position: absolute;
  inset: -14% 1px 0;
  border-radius: 4px;
  background: linear-gradient(90deg, #8d7a68, #d8c7b3 45%, #7a6757);
  box-shadow: 0 8px 12px rgba(0, 0, 0, 0.45);
}

.arm::after {
  content: "";
  position: absolute;
  left: -5px;
  bottom: -4px;
  width: 20px;
  height: 26px;
  border-radius: 3px;
  background: linear-gradient(90deg, #2a2019, #4c3d31);
  transform: rotate(8deg);
}

.deck-rpm {
  position: absolute;
  right: 5%;
  bottom: 5%;
  display: flex;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--muted);
}

.deck-rpm b {
  padding: 3px 7px;
  border-radius: 4px;
  border: 1px solid #5b4433;
  font-weight: 500;
}

.deck-rpm b.on {
  color: var(--bg-2);
  background: var(--amber);
  border-color: var(--amber);
}

.mixer {
  margin-top: 18px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 18px;
  align-items: center;
  padding: 14px 18px;
  border-radius: 14px;
  background: var(--wood);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.mixer .vu-meter {
  height: 44px;
}

.dj {
  display: grid;
  gap: 2px;
}

.dj small {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

.dj strong {
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.knob-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.deck-knob {
  position: relative;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #5d4837, #1c130d);
  box-shadow: 0 3px 6px rgba(0, 0, 0, 0.5);
}

.deck-knob::after {
  content: "";
  position: absolute;
  left: 50%;
  top: 3px;
  width: 2px;
  height: 9px;
  background: var(--amber);
  border-radius: 1px;
  transform-origin: 1px 10px;
  transform: translateX(-1px) rotate(var(--r, 0deg));
}

.deck-knob.interactive {
  width: 34px;
  height: 34px;
  cursor: grab;
  touch-action: none;
}

.deck-knob.interactive:active {
  cursor: grabbing;
}

.deck-knob.interactive.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.deck-knob.interactive:focus-visible {
  outline: 2px solid var(--amber);
  outline-offset: 3px;
}

.np-col {
  display: grid;
  gap: 18px;
  align-content: start;
}

.sleeve {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}

.np-cover {
  width: 112px;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.55);
}

.kicker {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--amber);
}

.np-title {
  margin: 6px 0 4px;
  font-size: clamp(1.6rem, 4.5vw, 2.4rem);
  line-height: 1.05;
  letter-spacing: -0.03em;
  font-weight: 800;
  text-wrap: balance;
  overflow-wrap: anywhere;
}

.np-artist {
  color: var(--muted);
  font-size: 1rem;
}

.np-bar {
  height: 4px;
  border-radius: 2px;
  background: #3b281b;
  overflow: hidden;
}

.np-bar-fill {
  display: block;
  height: 100%;
  width: 0;
  background: var(--amber);
  transition: width 0.4s linear;
}

.np-times {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.np-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.tune-btn {
  font-family: var(--font-display);
  font-weight: 800;
  font-size: 0.95rem;
  cursor: pointer;
  border-radius: 999px;
  padding: 12px 22px;
  min-width: 120px;
  background: var(--amber);
  color: var(--bg-2);
  border: 1px solid var(--amber);
}

.tune-btn:hover:not(:disabled) {
  filter: brightness(1.08);
}

.tune-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.sched {
  display: grid;
  gap: 10px;
}

.sched h2 {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
}

.sched ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.sched li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--wood);
  color: var(--muted);
  font-size: 0.95rem;
}

.sched li span:last-child {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  align-self: center;
}

.sched li.now {
  background: var(--wood-light);
  color: var(--cream);
  box-shadow: inset 3px 0 0 var(--amber);
}

@media (max-width: 820px) {
  .deck-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .arm,
  .np-bar-fill,
  .led {
    transition: none;
  }
}
```

Note: the global `@media (prefers-reduced-motion: reduce)` block later in the file handles buttons/skeletons already; the new addition covers the deck bits.

- [ ] **Step 9: Run the deck tests + full suite**

Run: `npm run test` (workdir `frontend`)
Expected: all pass (old suite untouched).

Run: `npm run build` (workdir `frontend`)
Expected: succeeds.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/styles/vintage.css frontend/src/components/deck/TurntableDeck.tsx frontend/src/components/deck/TurntableDeck.dom.test.tsx frontend/src/components/deck/VolumeKnob.tsx frontend/src/components/deck/VolumeKnob.dom.test.tsx
git commit -m "feat: turntable deck + volume knob components and deck styles"
```

---

### Task 5: Frontend — homepage rebuild (Tune in / Tune out, no skip/stop)

**Files:**
- Create: `frontend/src/utils/deck.ts`
- Create: `frontend/src/utils/deck.unit.test.ts`
- Modify: `frontend/src/pages/RadioPage.tsx` (full rewrite)
- Modify: `frontend/src/pages/RadioPage.dom.test.tsx` (rewrite tests)
- Modify: `frontend/src/styles/vintage.css` (replace homepage-only rules in the mobile blocks; delete obsolete homepage rules)
- Delete: `frontend/src/components/NowPlaying.tsx` (superseded; no other importer — verified via `rg "NowPlaying" frontend/src`)

- [ ] **Step 1: Write the failing helpers test**

Create `frontend/src/utils/deck.unit.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatClock, hourLabel, slotRange, todayScheduleRows } from "./deck";

const today = {
  current_id: 2,
  slots: [
    { id: 1, genre_id: 1, genre_name: "Morning", start_time: "05:00" },
    { id: 2, genre_id: 2, genre_name: "Evening", start_time: "17:00" },
  ],
};

describe("deck formatting helpers", () => {
  it("formats mm:ss clock", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(73)).toBe("1:13");
    expect(formatClock(-5)).toBe("0:00");
  });

  it("formats hours", () => {
    expect(hourLabel("05:00")).toBe("5 am");
    expect(hourLabel("17:30")).toBe("5:30 pm");
    expect(hourLabel("00:15")).toBe("12:15 am");
  });

  it("renders slot ranges with wraparound for the last slot", () => {
    const rows = todayScheduleRows(today);
    expect(rows[0]).toEqual({
      id: 1,
      name: "Morning",
      range: "5 am – 5 pm",
      isNow: false,
    });
    expect(rows[1]).toEqual({
      id: 2,
      name: "Evening",
      range: "5 pm – 5 am",
      isNow: true,
    });
  });

  it("renders a single slot without a range", () => {
    expect(
      todayScheduleRows({
        current_id: null,
        slots: [today.slots[0]],
      }),
    ).toEqual([
      { id: 1, name: "Morning", range: "5 am", isNow: false },
    ]);
  });

  it("returns no rows before data arrives", () => {
    expect(todayScheduleRows(null)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm run test -- src/utils/deck` (workdir `frontend`)
Expected: FAIL — cannot resolve `./deck`.

- [ ] **Step 3: Implement the helpers**

Create `frontend/src/utils/deck.ts`:

```ts
import type { ScheduleToday } from "../types";

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function hourLabel(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h < 12 ? "am" : "pm";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return m === 0
    ? `${hour12} ${suffix}`
    : `${hour12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function slotRange(times: string[], index: number): string {
  const start = hourLabel(times[index]);
  if (times.length === 1) return start;
  const next = times[(index + 1) % times.length];
  return `${start} – ${hourLabel(next)}`;
}

export interface ScheduleRow {
  id: number;
  name: string;
  range: string;
  isNow: boolean;
}

export function todayScheduleRows(
  today: ScheduleToday | null,
): ScheduleRow[] {
  if (!today) return [];
  const times = today.slots.map((s) => s.start_time);
  return today.slots.map((slot, index) => ({
    id: slot.id,
    name: slot.genre_name,
    range: slotRange(times, index),
    isNow: today.current_id === slot.id,
  }));
}
```

- [ ] **Step 4: Run the helpers test**

Run: `npm run test -- src/utils/deck` (workdir `frontend`)
Expected: 5 passed.

- [ ] **Step 5: Rewrite the RadioPage tests first**

Replace the contents of `frontend/src/pages/RadioPage.dom.test.tsx` with:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SlotToday, Track } from "../types";
import { api } from "../api/client";
import { RadioPage } from "./RadioPage";

vi.mock("../api/client", () => ({
  api: {
    now: vi.fn(),
    scheduleToday: vi.fn(),
  },
}));

const mocked = api as unknown as {
  now: ReturnType<typeof vi.fn>;
  scheduleToday: ReturnType<typeof vi.fn>;
};

function track(id: string): Track {
  return {
    youtube_video_id: id,
    title: id,
    artist: "",
    thumbnail_url: "",
    duration_seconds: 200,
    position: 0,
  };
}

const slots: SlotToday[] = [
  { id: 1, genre_id: 1, genre_name: "Morning", start_time: "05:00" },
  { id: 2, genre_id: 2, genre_name: "Evening", start_time: "17:00" },
];

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(_url: string) {
    FakeWebSocket.instances.push(this);
  }
}

class FakePlayer {
  opts: { videoId: string };
  loadVideoById = vi.fn();
  playVideo = vi.fn();
  pauseVideo = vi.fn();
  mute = vi.fn();
  unMute = vi.fn();
  setVolume = vi.fn();
  seekTo = vi.fn();
  getPlayerState = vi.fn(() => 1);
  getCurrentTime = vi.fn(() => 0);
  destroy = vi.fn();
  constructor(_el: string, opts: { videoId: string }) {
    this.opts = opts;
  }
}

window.matchMedia =
  window.matchMedia ||
  ((query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }) as unknown as MediaQueryList);

beforeEach(() => {
  window.localStorage.clear();
  FakeWebSocket.instances = [];
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  (window as unknown as { YT: unknown }).YT = {
    PlayerState: { PLAYING: 1, ENDED: 8 },
    Player: FakePlayer,
  };
  mocked.now.mockResolvedValue({
    genre: {
      id: 1,
      name: "Morning",
      slug: "morning",
      is_default: true,
      track_count: 1,
    },
    track: track("live"),
    offset_seconds: 0,
    server_time: "2026-01-01T00:00:00+00:00",
    source: "schedule",
  });
  mocked.scheduleToday.mockResolvedValue({ current_id: null, slots: [] });
});

afterEach(() => {
  vi.clearAllMocks();
  delete (globalThis as unknown as { WebSocket?: unknown }).WebSocket;
  delete (window as unknown as { YT?: unknown }).YT;
});

describe("RadioPage", () => {
  it("shows the live broadcast track and genre kicker", async () => {
    render(<RadioPage />);
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(await screen.findByText("Morning · live now")).toBeInTheDocument();
  });

  it("opens with Tune in and flips to Tune out on click", async () => {
    render(<RadioPage />);
    const tune = await screen.findByRole("button", { name: "Tune in" });
    fireEvent.click(tune);
    expect(
      await screen.findByRole("button", { name: "Tune out" }),
    ).toBeInTheDocument();
  });

  it("offers a volume knob slider", async () => {
    render(<RadioPage />);
    const slider = await screen.findByRole("slider", { name: "Volume" });
    expect(slider).toHaveAttribute("aria-valuemax", "100");
  });

  it("has no next-record or stop station controls", async () => {
    render(<RadioPage />);
    await screen.findByRole("button", { name: "Tune in" });
    expect(
      screen.queryByRole("button", { name: /next record/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /stop/i }),
    ).not.toBeInTheDocument();
  });

  it("renders today's schedule and highlights the current slot", async () => {
    mocked.scheduleToday.mockResolvedValue({ current_id: 1, slots });
    render(<RadioPage />);
    expect(await screen.findByText("Evening")).toBeInTheDocument();
    expect(await screen.findByText("5 am – 5 pm")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows[0].className).toContain("now");
    expect(rows[1].className).not.toContain("now");
  });

  it("falls back gracefully when the schedule request fails", async () => {
    mocked.scheduleToday.mockRejectedValue(new Error("boom"));
    mocked.now.mockResolvedValue({
      genre: {
        id: 1,
        name: "Morning",
        slug: "morning",
        is_default: true,
        track_count: 1,
      },
      track: track("live"),
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "schedule",
    });
    render(<RadioPage />);
    expect(await screen.findByText("live")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("shows the offline notice with a disabled tune control", async () => {
    mocked.now.mockResolvedValue({
      genre: null,
      track: null,
      offset_seconds: 0,
      server_time: "2026-01-01T00:00:00+00:00",
      source: "none",
    });
    render(<RadioPage />);
    expect(await screen.findByText(/radio offline/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tune in" })).toBeDisabled();
    expect(screen.queryByText(/off air/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run to verify failure**

Run: `npm run test -- RadioPage` (workdir `frontend`)
Expected: FAIL — buttons named "Tune in"/"Tune out" not found (old page renders Unmute/Mute), no schedule list.

- [ ] **Step 7: Rewrite `RadioPage.tsx`**

Replace the whole contents of `frontend/src/pages/RadioPage.tsx`:

```tsx
import { OfflineNotice } from "../components/OfflineNotice";
import { VUMeter } from "../components/VUMeter";
import { TurntableDeck } from "../components/deck/TurntableDeck";
import { VolumeKnob } from "../components/deck/VolumeKnob";
import { useBroadcast } from "../hooks/useBroadcast";
import { useListenerCount } from "../hooks/useListenerCount";
import { useTodaySchedule } from "../hooks/useTodaySchedule";
import { useYouTubePlayer } from "../hooks/useYouTubePlayer";
import type { CSSProperties } from "react";
import { formatClock, todayScheduleRows } from "../utils/deck";

export function RadioPage() {
  const listeners = useListenerCount();
  const { today } = useTodaySchedule();
  const { state, refresh } = useBroadcast();
  const player = useYouTubePlayer("yt-player", state, refresh);

  const offline = state != null && (state.source === "none" || !state.track);
  const track = player.error ? null : player.track;
  const genreName = state?.genre?.name ?? null;
  const duration = track?.duration_seconds ?? 0;
  const pct =
    duration > 0
      ? Math.min(100, Math.max(0, (player.progress / duration) * 100))
      : 0;
  const rows = todayScheduleRows(today);

  return (
    <div className={offline ? "radio-page offline" : "radio-page"}>
      <header className="radio-top">
        <div className="brand">
          Nakout<span>.</span>Radio
        </div>
        <div className="onair">
          <span
            className={player.playing ? "led on" : "led"}
            aria-hidden="true"
          />
          <span>{player.playing ? "On air" : "Standing by"}</span>
          <span>{listeners} listening</span>
        </div>
      </header>

      <div id="yt-player" className="hidden-player" />

      <main className="deck-grid">
        <section className="deck-side" aria-label="Turntable">
          <TurntableDeck
            playing={player.playing}
            artUrl={track?.thumbnail_url ?? null}
          />
          <div className="mixer">
            <div className="dj">
              <small>On the decks</small>
              <strong>{genreName ?? "Nakout Radio"}</strong>
            </div>
            <VUMeter playing={player.playing} seed={0} />
            <div className="knob-row">
              <VolumeKnob
                label="Volume"
                value={player.volume}
                onChange={player.setVolume}
              />
              <span className="deck-knob" aria-hidden="true" />
              <span
                className="deck-knob"
                aria-hidden="true"
                style={{ "--r": "20deg" } as CSSProperties}
              />
              <span
                className="deck-knob"
                aria-hidden="true"
                style={{ "--r": "70deg" } as CSSProperties}
              />
            </div>
          </div>
        </section>

        <section className="np-col">
          {offline ? (
            <>
              <OfflineNotice />
              <p className="np-artist">
                The deck is at rest. Come back for the next show.
              </p>
            </>
          ) : (
            <>
              <div className="sleeve">
                {track?.thumbnail_url && (
                  <img className="np-cover" src={track.thumbnail_url} alt="" />
                )}
                <div>
                  <div className="kicker">
                    {genreName ? `${genreName} · live now` : "Live now"}
                  </div>
                  <h1 className="np-title">{track?.title ?? "Tune in"}</h1>
                  <div className="np-artist">
                    {track?.artist || "Nakout Radio"}
                  </div>
                </div>
              </div>
              <div>
                <div className="np-bar">
                  <div
                    className="np-bar-fill"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(pct)}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="np-times">
                  <span>{formatClock(player.progress)}</span>
                  <span>{formatClock(duration)}</span>
                </div>
              </div>
            </>
          )}

          <div className="np-controls">
            {player.error && !offline ? (
              <button type="button" className="tune-btn" onClick={refresh}>
                Retry
              </button>
            ) : (
              <button
                type="button"
                className="tune-btn"
                onClick={player.toggleMute}
                disabled={offline}
              >
                {player.muted ? "Tune in" : "Tune out"}
              </button>
            )}
          </div>

          <section className="sched" aria-label="Today's schedule">
            <h2>Today's schedule</h2>
            {rows.length > 0 ? (
              <ul>
                {rows.map((row) => (
                  <li key={row.id} className={row.isNow ? "now" : undefined}>
                    <span>{row.name}</span>
                    <span>{row.range}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="np-artist">No schedule slots yet.</p>
            )}
          </section>
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 8: Delete obsolete `NowPlaying.tsx` and prune stale CSS**

Delete `frontend/src/components/NowPlaying.tsx`.

In `frontend/src/styles/vintage.css`:

1. Delete the block `.now-playing { ... }` (lines 247–255), `.now-playing.empty` (257–264), `.radio-cabinet.offline` (266–268), `.now-playing .art` (300–306), `.now-playing .title` (308–311), `.now-playing .artist` (313–316), `.now-playing .source` (318–322), `.genre-row` (385–393), `.tuned-label` (395–401), `.genre-list` rules (403–434), `.auto` (436–446), `.controls` rules (448–506), `.genre-error` (508–512), `.radio-cabinet` (204–212), `.radio-header` (214–228), `.listeners` (230–237).

2. Delete the now-dead homepage rules inside the mobile blocks:
   - In `@media (max-width: 600px)` (lines 1274+): remove `.radio-cabinet { padding: 20px; }` (1321–1323), the merged `.radio-cabinet { border-width… }` (1330–1333), `.radio-header` rules (1335–1341), `.genre-row` (1343–1345), `.controls button` (1347–1350), `.volume` rules (1352–1361). Add instead:

```css
  .radio-page {
    width: min(1080px, 100vw - 16px);
  }

  .brand {
    font-size: 1.3rem;
  }

  .tune-btn {
    min-height: 44px;
  }
```

   - In `@media (max-width: 380px)` (lines 1465+): remove `.radio-cabinet { … }` (1466–1469), `.now-playing { … }` (1471–1474), `.now-playing .art` (1476–1479), `.now-playing .title` (1481–1487), `.volume input[type="range"]` (1512–1514). Add instead:

```css
  .radio-page {
    padding-inline: 8px;
  }

  .sleeve {
    grid-template-columns: 84px minmax(0, 1fr);
  }

  .np-cover {
    width: 84px;
  }

  .np-title {
    font-size: 1.4rem;
  }
```

3. Delete the `.admin .now-playing` override (lines 324–329) — Task 6 restyles the admin now-playing block; leaving it would style a class that no longer exists. (Safe deletion: after Task 6 no markup uses `.now-playing`.)

Run `rg "now-playing|radio-cabinet|genre-row|tuned-label|volume" frontend/src` afterwards to confirm nothing references deleted classes from TSX.

- [ ] **Step 9: Run the full frontend suite**

Run: `npm run test` (workdir `frontend`)
Expected: all pass (`AdminPage.dom.test.tsx`, `NowPlayingPanel.dom.test.tsx` unaffected; if any fail from the AP client shape, re-check the mock list ordering — only `RadioPage.dom.test.tsx` should differ).

- [ ] **Step 10: Build + typecheck**

Run: `npm run build` (workdir `frontend`)
Expected: succeeds.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/utils/deck.ts frontend/src/utils/deck.unit.test.ts frontend/src/pages/RadioPage.tsx frontend/src/pages/RadioPage.dom.test.tsx frontend/src/styles/vintage.css
git rm frontend/src/components/NowPlaying.tsx
git commit -m "feat: vinyl deck homepage with tune in/out and today's schedule"
```

(Staging is explicit — `UI reference/` stays out.)

---

### Task 6: Frontend — whole studio dark + Now Playing deck rebuild

**Files:**
- Modify: `frontend/src/components/admin/NowPlayingPanel.tsx` (rebuild the JSX return; all logic/handlers stay)
- Modify: `frontend/src/styles/vintage.css` (admin deck layout rules + mobile + `#panel-now` flex updates)
- Test file `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx` needs **no changes** — every assertion targets text/roles that remain.

- [ ] **Step 1: Rebuild the NowPlayingPanel JSX**

In `frontend/src/components/admin/NowPlayingPanel.tsx`:

1. Add imports at the top:

```tsx
import { VUMeter } from "../VUMeter";
import { TurntableDeck } from "../deck/TurntableDeck";
import type { CSSProperties } from "react";
```

(`useState/useEffect/useRef/api` etc. stay as they are.)

2. Replace the entire `return (...)` block (from `return (` at line 195 to the closing `);` at line 366) with:

```tsx
  return (
    <section className="admin-panel np-panel" aria-label="Now playing">
      <div className="panel-head">
        <h2>Now playing</h2>
        {syncButton}
      </div>

      <div className="deck-grid admin-deck">
        <div className="deck-side admin-deck-side">
          <TurntableDeck
            playing={Boolean(state?.track)}
            artUrl={state?.track?.thumbnail_url ?? null}
          />
          <div className="mixer">
            <div className="dj">
              <small>On the decks</small>
              <strong>{state?.genre?.name ?? "Station"}</strong>
            </div>
            <VUMeter playing={Boolean(state?.track)} seed={1} />
            <div className="knob-row" aria-hidden="true">
              <span className="deck-knob" />
              <span
                className="deck-knob"
                style={{ "--r": "20deg" } as CSSProperties}
              />
              <span
                className="deck-knob"
                style={{ "--r": "70deg" } as CSSProperties}
              />
            </div>
          </div>
        </div>

        <div className="np-col admin-np-col">
          {genres.length > 0 && (
            <label className="field admin-genre-field">
              Genre
              <select
                aria-label="Genre to control"
                value={selectedId ?? ""}
                onChange={(e) => {
                  userSelectedRef.current = true;
                  setSelectedId(Number(e.target.value));
                }}
              >
                {genres.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {state?.genre && state.track ? (
            <>
              <div className="sleeve admin-sleeve">
                {state.track.thumbnail_url && (
                  <img
                    className="np-cover"
                    src={state.track.thumbnail_url}
                    alt=""
                  />
                )}
                <div>
                  <div className="kicker">Genre: {state.genre.name}</div>
                  <h2 className="np-title">{state.track.title}</h2>
                  <div className="np-artist">{state.track.artist}</div>
                </div>
              </div>
              <div>
                <div className="np-bar">
                  <div
                    className="np-bar-fill"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.max(
                          0,
                          ((state.offset ?? 0) /
                            (state.track.duration_seconds || 1)) *
                            100,
                        ),
                      )}%`,
                    }}
                  />
                </div>
                <div className="np-times">
                  <span>{formatClock(state.offset)}</span>
                  <span className={`badge source-${state.source}`}>
                    {SOURCE_LABELS[state.source] ?? state.source}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="muted">
              {failed ? "Could not load playback status." : "Nothing scheduled."}
            </p>
          )}

          <div className="transport">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => transport("prev")}
              disabled={tracks.length === 0}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => transport("next")}
              disabled={tracks.length === 0}
            >
              Next
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={stopPlayback}
              disabled={!state?.track}
            >
              Stop
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={goAuto}
              disabled={
                state == null ||
                state.source === "schedule" ||
                state.source === "default"
              }
            >
              Auto
            </button>
          </div>

          <div className="queue-head">
            <h3>Queue</h3>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => saveOrder(shuffle(tracks))}
              disabled={tracks.length < 2}
            >
              Shuffle
            </button>
          </div>

          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <ol className="queue-list" ref={queueRef}>
              {tracks.map((t, i) => {
                const isCurrent = i === currentIndex;
                return (
                  <li
                    key={`${t.youtube_video_id}-${i}`}
                    ref={isCurrent ? currentRowRef : undefined}
                    className={isCurrent ? "queue-row current" : "queue-row"}
                    draggable
                    onDragStart={() => setDragIndex(i)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (dragIndex !== null && dragIndex !== i) {
                        saveOrder(reorder(tracks, dragIndex, i));
                      }
                      setDragIndex(null);
                    }}
                    onDragEnd={() => setDragIndex(null)}
                  >
                    <span className="drag-handle" aria-hidden="true">
                      ⋮⋮
                    </span>
                    {t.thumbnail_url && (
                      <img className="art small" src={t.thumbnail_url} alt="" />
                    )}
                    <span className="queue-title">{t.title}</span>
                    <span className="queue-artist">{t.artist}</span>
                    <span className="queue-duration">
                      {formatDuration(t.duration_seconds)}
                    </span>
                    {isCurrent &&
                      (isMobileView ? (
                        <span
                          className="on-air-dot"
                          role="img"
                          aria-label="On air"
                        />
                      ) : (
                        <span className="badge">On air</span>
                      ))}
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => playTrack(t)}
                    >
                      Play
                    </button>
                  </li>
                );
              })}
            </ol>
          )}

          {pendingTrack && selectedId !== null && (
            <ConfirmDialog
              title="Interrupt playback?"
              message={`A song is playing — play "${pendingTrack.title}" now?`}
              confirmLabel="Play now"
              onConfirm={() => {
                const track = pendingTrack;
                const genreId = selectedId;
                setPendingTrack(null);
                void playNow(genreId, track);
              }}
              onCancel={() => setPendingTrack(null)}
            />
          )}
        </div>
      </div>
    </section>
  );
```

Important: the broadcast hook state carries the offset as `state.offset`
(`frontend/src/hooks/useBroadcast.ts:9-19` maps `offset_seconds` → `offset`),
so the panel reads `state.offset` — never `state.offset_seconds`.

3. Extend `frontend/src/utils/format.ts` by appending:

```ts
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
```

…and in NowPlayingPanel import it together with formatDuration:

```tsx
import { formatClock, formatDuration } from "../../utils/format";
```

4. The queue rows keep using `formatDuration` for their duration badges
(`3:20`), and the sleeve shows the elapsed clock via `formatClock(state.offset)`.
The existing test suite asserts only queue `3:20` values, so this is safe.

Note on the "On air" test at line 87: the sleeve does **not** render an extra "On air" chip — the badge there shows source labels (Schedule/Manual/…), so `getByText("On air")` still resolves to the unique queue badge.

- [ ] **Step 2: Add admin deck CSS**

In `frontend/src/styles/vintage.css`, immediately after the `#panel-now .queue-list { … }` rules (lines 619–623), append:

```css
#panel-now .admin-deck {
  flex: 1 1 auto;
  min-height: 0;
}

#panel-now .admin-deck > .np-col {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

#panel-now .admin-deck .queue-list {
  flex: 1 1 auto;
}

.admin-deck {
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  padding-top: 18px;
}

.admin-deck-side {
  min-width: 0;
}

.admin-deck-side .deck {
  max-width: 460px;
}

.admin-sleeve {
  grid-template-columns: 84px minmax(0, 1fr);
}

.admin-deck .np-title {
  font-size: clamp(1.2rem, 2vw, 1.6rem);
}

.admin-deck .np-col {
  gap: 14px;
}
```

And inside the existing `@media (max-width: 600px)` block, append:

```css
  .admin-deck {
    display: block;
  }

  .admin-deck-side .deck {
    max-width: none;
  }
```

- [ ] **Step 3: Verify**

Run: `npm run test` (workdir `frontend`)
Expected: all pass — queue/critical assertions (Play, Prev, Next, Stop, Auto, Shuffle, Sync, drag/drop, genre select) are markup-independent.

Run: `npm run build` (workdir `frontend`)
Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/admin/NowPlayingPanel.tsx frontend/src/utils/format.ts frontend/src/styles/vintage.css
git commit -m "feat: admin Now Playing deck rebuild, studio on dark theme"
```

---

### Task 7: Changelog + full verification

**Files:**
- Modify: `docs/changelog.md` (prepend entry, most recent first)

- [ ] **Step 1: Run everything once more**

- `npm run test` (workdir `frontend`) — all pass.
- `npm run build` (workdir `frontend`) — succeeds.
- `python -m pytest -q` (workdir `backend`) — all pass.

- [ ] **Step 2: Prepend the changelog entry**

At the top of `docs/changelog.md`:

```markdown
## 2026-10-09 — Vinyl deck UI

Re-skinned the homepage as the vinyl turntable deck from the UI reference:
deck + mixer with VU meter, Tune in/Tune out mute control (no listener
Next record / Stop), draggable volume knob, today's schedule via the new
public endpoint `GET /api/schedule/today`. Entire admin studio moved onto the
same dark theme; the Now Playing tab was rebuilt as the deck while keeping
all functionality (Prev / Next / Stop / Auto, genre select, queue
reorder/shuffle/per-row play, sync). Fonts switched site-wide to Bricolage
Grotesque + DM Mono.

Files: `frontend/index.html`, `frontend/src/styles/vintage.css`,
`frontend/src/pages/RadioPage.tsx` (+test), `frontend/src/utils/deck.ts`
(+test), `frontend/src/utils/format.ts`, `frontend/src/hooks/useTodaySchedule.ts`
(+test), `frontend/src/api/client.ts`, `frontend/src/types.ts`,
`frontend/src/components/deck/*` (new + tests),
`frontend/src/components/admin/NowPlayingPanel.tsx`,
`frontend/src/components/NowPlaying.tsx` (removed), `backend/app/routers/schedule.py`,
`backend/app/schemas.py`, `backend/tests/test_schedule_today.py` (new).

Restart: **both** containers required —

    docker compose up -d --build backend frontend

Verification: `npm run test` + `npm run build` (frontend) and `python -m pytest -q`
(backend) all green.
```

(Adjust the header style to match the existing changelog format if it differs — inspect the top of the file first and mirror it.)

- [ ] **Step 3: Commit**

```bash
git add docs/changelog.md
git commit -m "docs: changelog for vinyl deck UI"
```

- [ ] **Step 4: Do NOT push or merge** — leave the branch for review unless the user asks.
