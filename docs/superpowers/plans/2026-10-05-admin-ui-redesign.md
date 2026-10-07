# Admin UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the admin page into tabs and add two views: all added playlists (with refresh/remove) and a live now-playing status.

**Architecture:** Backend gains two admin endpoints (`GET /api/admin/playlists`, `DELETE /api/admin/playlists/{id}`) backed by the existing `Playlist`/`TrackCache` tables. The React `AdminPage` becomes a thin shell owning auth, notices, station state, and the active tab; each tab is its own focused component under `src/components/admin/`.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, pytest, React 18, TypeScript, Vitest, Testing Library.

**Note on commits:** This project is not a git repository. Each task ends with a **Checkpoint** (tests green) instead of a commit. Run `git init` first if you want per-task commits; then replace each Checkpoint with `git add`/`git commit`.

**Reference spec:** `docs/superpowers/specs/2026-10-05-admin-ui-redesign-design.md`

---

## File Structure

**Backend**
- Modify `backend/app/schemas.py` — add `PlaylistOut`.
- Modify `backend/app/routers/admin.py` — add `GET /playlists`, `DELETE /playlists/{id}`.
- Modify `backend/tests/test_admin.py` — endpoint tests.

**Frontend**
- Modify `frontend/src/types.ts` — add `AddedPlaylist`.
- Modify `frontend/src/api/client.ts` — add `listPlaylists`, `refreshPlaylist`, `deletePlaylist`.
- Create `frontend/src/components/admin/Tabs.tsx`
- Create `frontend/src/components/admin/StationSelect.tsx` (shared dropdown, extracted from `AdminPage`)
- Create `frontend/src/components/admin/NowPlayingPanel.tsx`
- Create `frontend/src/components/admin/StationsPanel.tsx`
- Create `frontend/src/components/admin/SchedulePanel.tsx`
- Create `frontend/src/components/admin/PlaylistsPanel.tsx`
- Modify `frontend/src/pages/AdminPage.tsx` — tabbed shell.
- Modify `frontend/src/styles/vintage.css` — tab/panel styles.
- Tests: `frontend/src/components/admin/Tabs.dom.test.tsx`, `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`, rewrite `frontend/src/pages/AdminPage.dom.test.tsx`, extend `frontend/src/api/client.test.ts`.

---

## Task 1: Backend — list added playlists endpoint

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin.py`:

```python
def test_list_added_playlists_requires_auth(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/admin/playlists").status_code == 401


def test_list_added_playlists(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/stations", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch(
            [TrackData("v1", "One", "A", "u", 0), TrackData("v2", "Two", "A", "u", 1)]
        ),
    )
    client.post(
        "/api/admin/playlists",
        json={"station_id": sid, "youtube_playlist_url": "PL1", "label": "L"},
    )
    resp = client.get("/api/admin/playlists")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["station_id"] == sid
    assert body[0]["station_name"] == "S"
    assert body[0]["youtube_playlist_id"] == "PL1"
    assert body[0]["label"] == "L"
    assert body[0]["track_count"] == 2


def test_list_added_playlists_counts_zero_without_tracks(tmp_path):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/stations", json={"name": "S", "slug": "s"}
    ).json()["id"]
    with Session(engine) as s:
        s.add(Playlist(station_id=sid, youtube_playlist_id="PL1"))
        s.commit()
    resp = client.get("/api/admin/playlists")
    assert resp.status_code == 200
    assert resp.json()[0]["track_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `backend`): `pytest tests/test_admin.py::test_list_added_playlists -v`
Expected: FAIL with `404 Not Found` (route does not exist yet).

- [ ] **Step 3: Add the `PlaylistOut` schema**

In `backend/app/schemas.py`, append at the end:

```python
class PlaylistOut(BaseModel):
    id: int
    station_id: int
    station_name: str
    youtube_playlist_id: str
    label: str
    track_count: int
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/routers/admin.py`, update imports. Change:

```python
from sqlmodel import Session, delete, select
```

to:

```python
from sqlalchemy import func
from sqlmodel import Session, delete, select
```

Add `PlaylistOut` to the schema import:

```python
from app.schemas import (
    ChannelIn,
    ChannelOut,
    ChannelPlaylistOut,
    PlaylistIn,
    PlaylistOut,
    SlotIn,
)
```

Add the endpoint after `create_playlist` (before `refresh_playlist`):

```python
@router.get(
    "/playlists",
    response_model=list[PlaylistOut],
    dependencies=[Depends(require_admin)],
)
def list_added_playlists(
    session: Session = Depends(get_session),
) -> list[PlaylistOut]:
    playlists = session.exec(
        select(Playlist).order_by(Playlist.station_id, Playlist.id)
    ).all()
    station_names = {s.id: s.name for s in session.exec(select(Station)).all()}
    counts = dict(
        session.exec(
            select(TrackCache.playlist_id, func.count(TrackCache.id)).group_by(
                TrackCache.playlist_id
            )
        ).all()
    )
    return [
        PlaylistOut(
            id=p.id,
            station_id=p.station_id,
            station_name=station_names.get(p.station_id, ""),
            youtube_playlist_id=p.youtube_playlist_id,
            label=p.label,
            track_count=counts.get(p.id, 0),
        )
        for p in playlists
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run (workdir `backend`): `pytest tests/test_admin.py -v`
Expected: PASS, including the two new tests.

- [ ] **Checkpoint:** `pytest tests/test_admin.py -v` is green.

---

## Task 2: Backend — delete added playlist endpoint

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin.py`:

```python
def test_delete_playlist_removes_tracks(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    _login(client)
    sid = client.post(
        "/api/admin/stations", json={"name": "S", "slug": "s"}
    ).json()["id"]
    monkeypatch.setattr(
        "app.routers.admin._build_fetch",
        lambda: _fake_fetch([TrackData("v1", "One", "A", "u", 0)]),
    )
    pid = client.post(
        "/api/admin/playlists",
        json={"station_id": sid, "youtube_playlist_url": "PL1", "label": ""},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `backend`): `pytest tests/test_admin.py::test_delete_playlist_removes_tracks -v`
Expected: FAIL with `405 Method Not Allowed` / `404` (route missing).

- [ ] **Step 3: Add the endpoint**

In `backend/app/routers/admin.py`, add after `list_added_playlists`:

```python
@router.delete(
    "/playlists/{playlist_id}", dependencies=[Depends(require_admin)]
)
def delete_playlist(
    playlist_id: int, session: Session = Depends(get_session)
) -> dict:
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="playlist not found")
    session.exec(delete(TrackCache).where(TrackCache.playlist_id == playlist_id))
    session.delete(playlist)
    session.commit()
    return {"status": "deleted"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (workdir `backend`): `pytest tests/test_admin.py -v`
Expected: PASS (all backend admin tests).

- [ ] **Checkpoint:** `pytest tests/test_admin.py -v` is green.

---

## Task 3: Frontend — types and API client

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write the failing tests**

Append inside the `describe("api client", ...)` block in `frontend/src/api/client.test.ts`:

```ts
  it("GETs added playlists", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    await api.listPlaylists();
    expect(spy.mock.calls[0][0]).toBe("/api/admin/playlists");
  });

  it("POSTs a playlist refresh", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 3, synced: 2 }), { status: 200 }),
    );
    await api.refreshPlaylist(3);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/admin/playlists/3/refresh");
    expect(init?.method).toBe("POST");
  });

  it("DELETEs a playlist", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "deleted" }), { status: 200 }),
    );
    await api.deletePlaylist(3);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/admin/playlists/3");
    expect(init?.method).toBe("DELETE");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `frontend`): `npm test -- client.test.ts`
Expected: FAIL — `api.listPlaylists is not a function`.

- [ ] **Step 3: Add the type**

In `frontend/src/types.ts`, append:

```ts
export interface AddedPlaylist {
  id: number;
  station_id: number;
  station_name: string;
  youtube_playlist_id: string;
  label: string;
  track_count: number;
}
```

- [ ] **Step 4: Add the client methods**

In `frontend/src/api/client.ts`, add `AddedPlaylist` to the type import:

```ts
import type {
  AddedPlaylist,
  ChannelPlaylist,
  ChannelSource,
  CurrentStation,
  Station,
  StationDetail,
  Track,
} from "../types";
```

Add these methods to the `api` object (after `createPlaylist`):

```ts
  listPlaylists: () => request<AddedPlaylist[]>("/admin/playlists"),
  refreshPlaylist: (id: number) =>
    request<{ id: number; synced: number }>(
      `/admin/playlists/${id}/refresh`,
      { method: "POST" },
    ),
  deletePlaylist: (id: number) =>
    request<{ status: string }>(`/admin/playlists/${id}`, { method: "DELETE" }),
```

- [ ] **Step 5: Run tests to verify they pass**

Run (workdir `frontend`): `npm test -- client.test.ts`
Expected: PASS.

- [ ] **Checkpoint:** `npm test -- client.test.ts` is green.

---

## Task 4: Frontend — Tabs and StationSelect components

**Files:**
- Create: `frontend/src/components/admin/Tabs.tsx`
- Create: `frontend/src/components/admin/StationSelect.tsx`
- Test: `frontend/src/components/admin/Tabs.dom.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/admin/Tabs.dom.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Tabs } from "./Tabs";

describe("Tabs", () => {
  it("marks the active tab and reports clicks", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        tabs={[
          { id: "a", label: "A" },
          { id: "b", label: "B" },
        ]}
        active="a"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole("tab", { name: "A" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "B" }));
    expect(onChange).toHaveBeenCalledWith("b");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (workdir `frontend`): `npm test -- Tabs.dom.test.tsx`
Expected: FAIL — cannot resolve `./Tabs`.

- [ ] **Step 3: Write `Tabs.tsx`**

Create `frontend/src/components/admin/Tabs.tsx`:

```tsx
export interface TabDef {
  id: string;
  label: string;
}

interface Props {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}

export function Tabs({ tabs, active, onChange }: Props) {
  return (
    <nav className="admin-tabs" role="tablist" aria-label="Admin sections">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={t.id === active}
          className={t.id === active ? "active" : ""}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: Write `StationSelect.tsx`**

Create `frontend/src/components/admin/StationSelect.tsx`:

```tsx
import type { Station } from "../../types";

interface Props {
  label: string;
  stations: Station[];
  value: string;
  onChange: (value: string) => void;
}

export function StationSelect({ label, stations, value, onChange }: Props) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Select a station…</option>
      {stations.map((s) => (
        <option key={s.slug} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (workdir `frontend`): `npm test -- Tabs.dom.test.tsx`
Expected: PASS.

- [ ] **Checkpoint:** `npm test -- Tabs.dom.test.tsx` is green.

---

## Task 5: Frontend — NowPlayingPanel

**Files:**
- Create: `frontend/src/components/admin/NowPlayingPanel.tsx`
- Test: `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/admin/NowPlayingPanel.dom.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { NowPlayingPanel } from "./NowPlayingPanel";

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return { ...actual, api: { scheduleNow: vi.fn(), syncAll: vi.fn() } };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(() => {
  vi.clearAllMocks();
});

describe("NowPlayingPanel", () => {
  it("shows the scheduled station and track", async () => {
    mocked.scheduleNow.mockResolvedValue({
      station: { id: 1, name: "Chill", slug: "chill", is_default: true, track_count: 5 },
      track: {
        youtube_video_id: "v",
        title: "Song",
        artist: "Artist",
        thumbnail_url: "",
        duration_seconds: 0,
        position: 0,
      },
      cursor: "c",
      source: "schedule",
    });
    render(<NowPlayingPanel onNotice={vi.fn()} onError={vi.fn()} />);
    expect(await screen.findByText("Song")).toBeInTheDocument();
    expect(screen.getByText(/Chill/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing is scheduled", async () => {
    mocked.scheduleNow.mockResolvedValue({
      station: null,
      track: null,
      cursor: null,
      source: "none",
    });
    render(<NowPlayingPanel onNotice={vi.fn()} onError={vi.fn()} />);
    expect(await screen.findByText("Nothing scheduled.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (workdir `frontend`): `npm test -- NowPlayingPanel.dom.test.tsx`
Expected: FAIL — cannot resolve `./NowPlayingPanel`.

- [ ] **Step 3: Write `NowPlayingPanel.tsx`**

Create `frontend/src/components/admin/NowPlayingPanel.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { CurrentStation } from "../../types";
import { secondsUntilNextMinute } from "../../utils/format";

interface Props {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

function messageFor(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

export function NowPlayingPanel({ onNotice, onError }: Props) {
  const [current, setCurrent] = useState<CurrentStation | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const data = await api.scheduleNow();
        if (!cancelled) setCurrent(data);
      } catch {
        // keep the last known state on transient errors
      }
    };

    const scheduleNext = () => {
      if (cancelled) return;
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
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, []);

  const syncAll = async () => {
    try {
      const result = await api.syncAll();
      const failed = result.results.filter((r) => r.error).length;
      onNotice(
        failed === 0
          ? `Synced ${result.results.length} playlist(s).`
          : `Synced ${result.results.length - failed} of ${result.results.length} playlist(s); ${failed} failed.`,
      );
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const syncButton = (
    <button type="button" onClick={syncAll}>
      Sync all playlists
    </button>
  );

  if (!current) {
    return (
      <section className="admin-panel" aria-label="Now playing">
        <h2>Now playing</h2>
        <p>Loading…</p>
        {syncButton}
      </section>
    );
  }

  if (!current.station || !current.track) {
    return (
      <section className="admin-panel" aria-label="Now playing">
        <h2>Now playing</h2>
        <p>Nothing scheduled.</p>
        {syncButton}
      </section>
    );
  }

  return (
    <section className="admin-panel" aria-label="Now playing">
      <h2>Now playing</h2>
      <div className="now-playing">
        {current.track.thumbnail_url && (
          <img className="art" src={current.track.thumbnail_url} alt="" />
        )}
        <div className="meta">
          <div className="title">{current.track.title}</div>
          <div className="artist">{current.track.artist}</div>
          <div className="source">
            Station: {current.station.name} · Source: {current.source}
          </div>
        </div>
      </div>
      {syncButton}
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (workdir `frontend`): `npm test -- NowPlayingPanel.dom.test.tsx`
Expected: PASS.

- [ ] **Checkpoint:** `npm test -- NowPlayingPanel.dom.test.tsx` is green.

---

## Task 6: Frontend — StationsPanel and SchedulePanel

**Files:**
- Create: `frontend/src/components/admin/StationsPanel.tsx`
- Create: `frontend/src/components/admin/SchedulePanel.tsx`

No new tests: both are exercised through the rewritten `AdminPage.dom.test.tsx` in Task 8. This checkpoint uses `npm run typecheck`.

- [ ] **Step 1: Write `StationsPanel.tsx`**

Create `frontend/src/components/admin/StationsPanel.tsx`:

```tsx
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Station } from "../../types";

interface Props {
  stations: Station[];
  onStationsChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

function messageFor(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

export function StationsPanel({
  stations,
  onStationsChanged,
  onNotice,
  onError,
}: Props) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  const addStation = async () => {
    try {
      await api.createStation(name, slug);
      setName("");
      setSlug("");
      onNotice("Station added.");
      await onStationsChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  return (
    <section className="admin-panel" aria-label="Stations">
      <h2>Stations</h2>
      <input
        aria-label="Station name"
        placeholder="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        aria-label="Station slug"
        placeholder="Slug"
        value={slug}
        onChange={(e) => setSlug(e.target.value)}
      />
      <button type="button" onClick={addStation} disabled={!name || !slug}>
        Add station
      </button>
      <ul className="station-admin-list">
        {stations.map((s) => (
          <li key={s.id}>
            <span>{s.name}</span>
            <span className="muted"> ({s.track_count} tracks)</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 2: Write `SchedulePanel.tsx`**

Create `frontend/src/components/admin/SchedulePanel.tsx`:

```tsx
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Station } from "../../types";
import { StationSelect } from "./StationSelect";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  stations: Station[];
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

function messageFor(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

export function SchedulePanel({ stations, onNotice, onError }: Props) {
  const [station, setStation] = useState("");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [start, setStart] = useState("06:00");
  const [end, setEnd] = useState("12:00");

  const toggleDay = (day: number) => {
    setDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  };

  const addSlot = async () => {
    try {
      await api.createSlot({
        station_id: Number(station),
        days_of_week: days,
        start_time: start,
        end_time: end,
      });
      onNotice("Schedule slot added.");
    } catch (err) {
      onError(messageFor(err));
    }
  };

  return (
    <section className="admin-panel" aria-label="Schedule">
      <h2>Schedule slot</h2>
      <StationSelect
        label="Slot station"
        stations={stations}
        value={station}
        onChange={setStation}
      />
      <div className="days">
        {DAY_LABELS.map((label, i) => (
          <button
            type="button"
            key={label}
            className={days.includes(i) ? "active" : ""}
            aria-pressed={days.includes(i)}
            onClick={() => toggleDay(i)}
          >
            {label}
          </button>
        ))}
      </div>
      <label>
        Start
        <input value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label>
        End
        <input value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <button type="button" onClick={addSlot} disabled={!station}>
        Add slot
      </button>
    </section>
  );
}
```

- [ ] **Step 3: Typecheck**

Run (workdir `frontend`): `npm run typecheck`
Expected: no errors from the two new files.

- [ ] **Checkpoint:** `npm run typecheck` is green.

---

## Task 7: Frontend — PlaylistsPanel

**Files:**
- Create: `frontend/src/components/admin/PlaylistsPanel.tsx`

Exercised through `AdminPage.dom.test.tsx` in Task 8.

- [ ] **Step 1: Write `PlaylistsPanel.tsx`**

Create `frontend/src/components/admin/PlaylistsPanel.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type {
  AddedPlaylist,
  ChannelPlaylist,
  ChannelSource,
  Station,
} from "../../types";
import { StationSelect } from "./StationSelect";

interface Props {
  stations: Station[];
  onStationsChanged: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

function messageFor(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

export function PlaylistsPanel({
  stations,
  onStationsChanged,
  onNotice,
  onError,
}: Props) {
  const [added, setAdded] = useState<AddedPlaylist[]>([]);
  const [addedError, setAddedError] = useState("");

  const [addStation, setAddStation] = useState("");
  const [url, setUrl] = useState("");

  const [channel, setChannel] = useState<ChannelSource | null>(null);
  const [channelInput, setChannelInput] = useState("");
  const [channelError, setChannelError] = useState("");
  const [channelPlaylists, setChannelPlaylists] = useState<ChannelPlaylist[]>(
    [],
  );
  const [playlistError, setPlaylistError] = useState("");
  const [stationById, setStationById] = useState<Record<string, string>>({});

  const loadAdded = useCallback(async () => {
    try {
      setAdded(await api.listPlaylists());
      setAddedError("");
    } catch (err) {
      setAddedError(messageFor(err));
    }
  }, []);

  const loadChannel = useCallback(async () => {
    try {
      const source = await api.getChannelSource();
      setChannel(source);
      if (source.channel_id) {
        setChannelPlaylists(await api.listChannelPlaylists());
        setPlaylistError("");
      } else {
        setChannelPlaylists([]);
      }
    } catch (err) {
      setPlaylistError(messageFor(err));
    }
  }, []);

  useEffect(() => {
    loadAdded();
    loadChannel();
  }, [loadAdded, loadChannel]);

  const reportResult = (result: { synced: number; sync_error: string | null }) => {
    onNotice(
      result.sync_error
        ? `Playlist saved, but sync failed: ${result.sync_error}`
        : `Playlist synced (${result.synced} tracks).`,
    );
  };

  const addByUrl = async () => {
    try {
      reportResult(await api.createPlaylist(Number(addStation), url, ""));
      setUrl("");
      await onStationsChanged();
      await loadAdded();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const refresh = async (id: number) => {
    try {
      const result = await api.refreshPlaylist(id);
      onNotice(`Refreshed playlist (${result.synced} tracks).`);
      await loadAdded();
      await onStationsChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const remove = async (id: number) => {
    if (!window.confirm("Remove this playlist and its tracks?")) return;
    try {
      await api.deletePlaylist(id);
      onNotice("Playlist removed.");
      await loadAdded();
      await onStationsChanged();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  const saveChannel = async () => {
    try {
      const source = await api.setChannelSource(channelInput.trim());
      setChannel(source);
      setChannelInput("");
      setChannelPlaylists(await api.listChannelPlaylists());
      setPlaylistError("");
    } catch (err) {
      setChannelError(messageFor(err));
    }
  };

  const addFromChannel = async (playlistId: string) => {
    const stationId = Number(stationById[playlistId] ?? "");
    if (!stationId) {
      onError("Select a station first.");
      return;
    }
    try {
      reportResult(
        await api.createPlaylist(
          stationId,
          `https://www.youtube.com/playlist?list=${playlistId}`,
          "",
        ),
      );
      await onStationsChanged();
      await loadAdded();
      await loadChannel();
    } catch (err) {
      onError(messageFor(err));
    }
  };

  return (
    <section className="admin-panel" aria-label="Playlists">
      <h2>Added playlists</h2>
      {addedError && (
        <p className="error" role="alert">
          {addedError}
        </p>
      )}
      {added.length === 0 && !addedError && <p>No playlists added yet.</p>}
      <ul className="added-playlists">
        {added.map((p) => (
          <li key={p.id}>
            <span className="pl-station">{p.station_name}</span>
            <span className="pl-id">{p.label || p.youtube_playlist_id}</span>
            <span className="muted">{p.track_count} tracks</span>
            <button type="button" onClick={() => refresh(p.id)}>
              Refresh
            </button>
            <button type="button" onClick={() => remove(p.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>

      <h2>Add playlist by URL</h2>
      <StationSelect
        label="Playlist station"
        stations={stations}
        value={addStation}
        onChange={setAddStation}
      />
      <input
        aria-label="YouTube playlist URL"
        placeholder="YouTube playlist URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button type="button" onClick={addByUrl} disabled={!addStation || !url}>
        Add playlist
      </button>

      <h2>Browse channel playlists</h2>
      {channel?.channel_id ? (
        <div>
          <p>Channel: {channel.title || channel.channel_id}</p>
          <button
            type="button"
            onClick={() => {
              setChannel(null);
              setChannelError("");
            }}
          >
            Change
          </button>
          <button type="button" onClick={loadChannel}>
            Refresh
          </button>
          {playlistError && (
            <p className="error" role="alert">
              {playlistError}
            </p>
          )}
          {channelPlaylists.length === 0 && !playlistError && (
            <p>No playlists found.</p>
          )}
          <ul>
            {channelPlaylists.map((p) => (
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
                      value={stationById[p.youtube_playlist_id] ?? ""}
                      onChange={(e) =>
                        setStationById((prev) => ({
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
                      onClick={() => addFromChannel(p.youtube_playlist_id)}
                      disabled={!stationById[p.youtube_playlist_id]}
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
  );
}
```

- [ ] **Step 2: Typecheck**

Run (workdir `frontend`): `npm run typecheck`
Expected: no errors from `PlaylistsPanel.tsx`.

- [ ] **Checkpoint:** `npm run typecheck` is green.

---

## Task 8: Frontend — tabbed AdminPage and DOM tests

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`
- Test: `frontend/src/pages/AdminPage.dom.test.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `AdminPage.dom.test.tsx`**

Replace the entire contents of `frontend/src/pages/AdminPage.dom.test.tsx` with:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { AdminPage } from "./AdminPage";

vi.mock("../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      login: vi.fn(),
      logout: vi.fn(),
      listStations: vi.fn(),
      createStation: vi.fn(),
      createPlaylist: vi.fn(),
      createSlot: vi.fn(),
      syncAll: vi.fn(),
      scheduleNow: vi.fn(),
      getChannelSource: vi.fn(),
      setChannelSource: vi.fn(),
      listChannelPlaylists: vi.fn(),
      listPlaylists: vi.fn(),
      refreshPlaylist: vi.fn(),
      deletePlaylist: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  mocked.getChannelSource.mockResolvedValue({ channel_id: null, title: null });
  mocked.listChannelPlaylists.mockResolvedValue([]);
  mocked.listPlaylists.mockResolvedValue([]);
  mocked.scheduleNow.mockResolvedValue({
    station: null,
    track: null,
    cursor: null,
    source: "none",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

async function login() {
  fireEvent.change(screen.getByPlaceholderText("Password"), {
    target: { value: "pw" },
  });
  fireEvent.click(screen.getByText("Log in"));
  await screen.findByRole("tab", { name: "Stations" });
}

describe("AdminPage", () => {
  it("shows the tabs after a successful login", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([]);
    render(<AdminPage />);
    await login();
    expect(screen.getByRole("tab", { name: "Now Playing" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Playlists" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Schedule" })).toBeInTheDocument();
  });

  it("shows the API error message on a bad login", async () => {
    mocked.login.mockRejectedValue(new ApiError(401, "invalid password"));
    render(<AdminPage />);
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByText("Log in"));
    expect(await screen.findByText("invalid password")).toBeInTheDocument();
  });

  it("creates a station and refreshes the list", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([]);
    mocked.createStation.mockResolvedValue({
      id: 1,
      name: "Chill",
      slug: "chill",
      is_default: false,
      track_count: 0,
    });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Stations" }));
    fireEvent.change(screen.getByPlaceholderText("Name"), {
      target: { value: "Chill" },
    });
    fireEvent.change(screen.getByPlaceholderText("Slug"), {
      target: { value: "chill" },
    });
    fireEvent.click(screen.getByText("Add station"));
    await waitFor(() =>
      expect(mocked.createStation).toHaveBeenCalledWith("Chill", "chill"),
    );
    expect(mocked.listStations).toHaveBeenCalledTimes(2);
  });

  it("logs out and returns to the login screen", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([]);
    mocked.logout.mockResolvedValue({ status: "ok" });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByText("Log out"));
    await waitFor(() => expect(mocked.logout).toHaveBeenCalled());
    expect(await screen.findByText("Log in")).toBeInTheDocument();
  });

  it("adds a playlist by URL and reports the synced count", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.createPlaylist.mockResolvedValue({
      id: 9,
      youtube_playlist_id: "PL1",
      synced: 3,
      sync_error: null,
    });
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    fireEvent.change(screen.getByLabelText("Playlist station"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByPlaceholderText("YouTube playlist URL"), {
      target: { value: "https://www.youtube.com/playlist?list=PL1" },
    });
    fireEvent.click(screen.getByText("Add playlist"));
    await waitFor(() =>
      expect(mocked.createPlaylist).toHaveBeenCalledWith(
        1,
        "https://www.youtube.com/playlist?list=PL1",
        "",
      ),
    );
    expect(
      await screen.findByText(/Playlist synced \(3 tracks\)/),
    ).toBeInTheDocument();
  });

  it("lists added playlists with station and track count", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listPlaylists.mockResolvedValue([
      {
        id: 9,
        station_id: 1,
        station_name: "Chill",
        youtube_playlist_id: "PL1",
        label: "",
        track_count: 4,
      },
    ]);
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    expect(await screen.findByText("PL1")).toBeInTheDocument();
    expect(screen.getByText("4 tracks")).toBeInTheDocument();
  });

  it("refreshes and removes an added playlist", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.listPlaylists.mockResolvedValue([
      {
        id: 9,
        station_id: 1,
        station_name: "Chill",
        youtube_playlist_id: "PL1",
        label: "",
        track_count: 4,
      },
    ]);
    mocked.refreshPlaylist.mockResolvedValue({ id: 9, synced: 4 });
    mocked.deletePlaylist.mockResolvedValue({ status: "deleted" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    await screen.findByText("PL1");
    fireEvent.click(screen.getByText("Refresh"));
    await waitFor(() =>
      expect(mocked.refreshPlaylist).toHaveBeenCalledWith(9),
    );
    fireEvent.click(screen.getByText("Remove"));
    await waitFor(() => expect(mocked.deletePlaylist).toHaveBeenCalledWith(9));
  });

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
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
    await screen.findByPlaceholderText("@handle or channel URL");
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
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Playlists" }));
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
    expect(
      await screen.findByText(/Playlist synced \(5 tracks\)/),
    ).toBeInTheDocument();
  });

  it("adds a schedule slot", async () => {
    mocked.login.mockResolvedValue({ status: "ok" });
    mocked.listStations.mockResolvedValue([
      { id: 1, name: "Chill", slug: "chill", is_default: false, track_count: 0 },
    ]);
    mocked.createSlot.mockResolvedValue({});
    render(<AdminPage />);
    await login();
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    fireEvent.change(screen.getByLabelText("Slot station"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByText("Add slot"));
    await waitFor(() => expect(mocked.createSlot).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `frontend`): `npm test -- AdminPage.dom.test.tsx`
Expected: FAIL — no `tab` role in the current single-card page; `createSlot`/`listPlaylists` not called.

- [ ] **Step 3: Rewrite `AdminPage.tsx`**

Replace the entire contents of `frontend/src/pages/AdminPage.tsx` with:

```tsx
import { useCallback, useState } from "react";
import { api, ApiError } from "../api/client";
import { NowPlayingPanel } from "../components/admin/NowPlayingPanel";
import { PlaylistsPanel } from "../components/admin/PlaylistsPanel";
import { SchedulePanel } from "../components/admin/SchedulePanel";
import { StationsPanel } from "../components/admin/StationsPanel";
import { Tabs, type TabDef } from "../components/admin/Tabs";
import type { Station } from "../types";

function messageFor(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

const TABS: TabDef[] = [
  { id: "now", label: "Now Playing" },
  { id: "playlists", label: "Playlists" },
  { id: "stations", label: "Stations" },
  { id: "schedule", label: "Schedule" },
];

export function AdminPage() {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [stations, setStations] = useState<Station[]>([]);
  const [tab, setTab] = useState("now");

  const refreshStations = useCallback(async () => {
    try {
      setStations(await api.listStations());
    } catch {
      setStations([]);
    }
  }, []);

  const login = async () => {
    try {
      await api.login(password);
      setAuthed(true);
      setError("");
      await refreshStations();
    } catch (err) {
      setError(messageFor(err));
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // session may already be gone; ignore
    }
    setAuthed(false);
    setStations([]);
    setPassword("");
    setError("");
    setNotice("");
  };

  const onNotice = (message: string) => {
    setError("");
    setNotice(message);
  };

  const onError = (message: string) => {
    setNotice("");
    setError(message);
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
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="admin">
      <header className="admin-header">
        <h1>Admin</h1>
        <button type="button" onClick={logout}>
          Log out
        </button>
      </header>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" aria-live="polite">
          {notice}
        </p>
      )}

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "now" && (
        <NowPlayingPanel onNotice={onNotice} onError={onError} />
      )}
      {tab === "playlists" && (
        <PlaylistsPanel
          stations={stations}
          onStationsChanged={refreshStations}
          onNotice={onNotice}
          onError={onError}
        />
      )}
      {tab === "stations" && (
        <StationsPanel
          stations={stations}
          onStationsChanged={refreshStations}
          onNotice={onNotice}
          onError={onError}
        />
      )}
      {tab === "schedule" && (
        <SchedulePanel
          stations={stations}
          onNotice={onNotice}
          onError={onError}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (workdir `frontend`): `npm test -- AdminPage.dom.test.tsx`
Expected: PASS.

- [ ] **Checkpoint:** `npm test -- AdminPage.dom.test.tsx` is green.

---

## Task 9: Frontend — styles

**Files:**
- Modify: `frontend/src/styles/vintage.css`

- [ ] **Step 1: Widen the admin card**

In `frontend/src/styles/vintage.css`, change:

```css
.admin {
  width: min(560px, 92vw);
```

to:

```css
.admin {
  width: min(720px, 94vw);
```

- [ ] **Step 2: Append tab and panel styles**

Append to `frontend/src/styles/vintage.css`:

```css
.admin-tabs {
  display: flex;
  gap: 6px;
  margin: 12px 0 4px;
  flex-wrap: wrap;
}

.admin-tabs button {
  margin: 0;
  background: transparent;
  color: var(--ink);
}

.admin-tabs button.active {
  background: var(--wood);
  color: var(--cream);
}

.admin-panel {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px dashed rgba(42, 26, 16, 0.3);
}

.added-playlists {
  list-style: none;
  margin: 8px 0;
  padding: 0;
}

.added-playlists li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(42, 26, 16, 0.12);
  flex-wrap: wrap;
}

.added-playlists .pl-station {
  font-weight: bold;
}

.added-playlists .pl-id {
  opacity: 0.8;
}

.station-admin-list {
  list-style: none;
  margin: 8px 0;
  padding: 0;
}

.muted {
  color: #6b5a4a;
  font-size: 0.85rem;
}
```

- [ ] **Step 3: Typecheck and build**

Run (workdir `frontend`): `npm run typecheck`
Then: `npm run build`
Expected: no errors; build succeeds.

- [ ] **Checkpoint:** `npm run typecheck` and `npm run build` are green.

---

## Task 10: Full verification

- [ ] **Step 1: Backend tests**

Run (workdir `backend`): `pytest -v`
Expected: all tests pass.

- [ ] **Step 2: Frontend tests**

Run (workdir `frontend`): `npm test`
Expected: all tests pass.

- [ ] **Step 3: Typecheck**

Run (workdir `frontend`): `npm run typecheck`
Expected: no errors.

- [ ] **Final Checkpoint:** Both suites green. The admin page shows four tabs; Playlists lists added playlists with Refresh/Remove; Now Playing shows the scheduled track.

---

## Self-Review Notes

- **Spec coverage:** Tab layout (Tasks 4, 8); now playing (Task 5); added playlists list + refresh/remove (Tasks 1, 2, 3, 7, 8); add-by-URL and channel browse preserved (Task 7); stations (Task 6); schedule (Task 6); CSS (Task 9); tests (Tasks 1–5, 8, 10). All spec sections map to tasks.
- **PlaylistOut fields** match `AddedPlaylist` exactly (`id`, `station_id`, `station_name`, `youtube_playlist_id`, `label`, `track_count`).
- **Client method names** (`listPlaylists`, `refreshPlaylist`, `deletePlaylist`) are used identically in `PlaylistsPanel` and `AdminPage.dom.test.tsx`.
- **Route shape** `/api/admin/playlists` (GET/DELETE) matches the client paths.
