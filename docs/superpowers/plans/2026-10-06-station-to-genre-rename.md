# Station → Genre Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the app's "Station" domain concept to "Genre" across database, backend, frontend, config, tests, and docs, preserving all existing data.

**Architecture:** Mechanical, case-aware global rename (`station`→`genre`, `Station`→`Genre`, `STATION`→`GENRE`) scoped to source directories, followed by explicit file renames, plus one hand-written Alembic migration that renames the SQLite table/columns/indexes and rewrites persisted `Setting` keys. The historical migrations and `docs/` are left untouched.

**Tech Stack:** FastAPI + SQLModel + Alembic + SQLite (backend), React + Vite + Vitest (frontend), Docker Compose.

---

## Notes for the implementer

- This working copy is **not a git repository**, so the "Commit" steps from the standard plan template are replaced with verification checkpoints. Do not run `git` commands.
- A case-aware string replace is safe here: an audit of the codebase found no words other than the `station` concept contain that substring (`backend/`, `frontend/src/`).
- Do **not** run the rename over `backend/alembic/versions/` (historical migrations must keep creating the old `station` schema) or `docs/` (historical specs/plans).
- The migration test intentionally contains legacy strings (`station`, `station_id`, `station_order:`); it is written *after* the global rename and must never be run through the rename script.

---

## Task 1: Baseline verification

**Files:** none (read-only).

- [ ] **Step 1: Run the backend test suite**

Run (from `backend/`):
```
python -m pytest -q
```
Expected: all tests pass. Record the count.

- [ ] **Step 2: Run the frontend checks**

Run (from `frontend/`):
```
npm run typecheck
npm test
```
Expected: typecheck clean; all vitest suites pass. Record the count.

- [ ] **Step 3: Checkpoint**

Baseline is green. Do not proceed until both suites pass.

---

## Task 2: Backend source rename

**Files:**
- Modify (in place): everything under `backend/app/` and `backend/tests/` (`*.py`)
- Modify: `backend/.env`, `backend/.env.example`
- Rename: `backend/app/routers/stations.py` → `backend/app/routers/genres.py`
- Rename: `backend/tests/test_stations.py` → `backend/tests/test_genres.py`

- [ ] **Step 1: Run the case-aware rename script over the backend sources and env files**

Run from the repo root:
```powershell
$enc = New-Object System.Text.UTF8Encoding($false)
$roots = @("backend\app", "backend\tests", "backend\.env", "backend\.env.example")
$files = foreach ($p in $roots) {
  if (Test-Path -LiteralPath $p -PathType Container) {
    Get-ChildItem -LiteralPath $p -Recurse -File | Where-Object { $_.Extension -in '.py' }
  } else {
    Get-Item -LiteralPath $p
  }
}
foreach ($f in $files) {
  $t = [System.IO.File]::ReadAllText($f.FullName)
  $n = $t.Replace('station','genre').Replace('Station','Genre').Replace('STATION','GENRE')
  if ($n -ne $t) { [System.IO.File]::WriteAllText($f.FullName, $n, $enc); "updated $($f.FullName)" }
}
```

- [ ] **Step 2: Rename the backend module and test files**

Run from the repo root:
```powershell
Move-Item -LiteralPath "backend\app\routers\stations.py" -Destination "backend\app\routers\genres.py"
Move-Item -LiteralPath "backend\tests\test_stations.py" -Destination "backend\tests\test_genres.py"
```

- [ ] **Step 3: Verify no unintended leftovers**

Run from the repo root:
```powershell
Get-ChildItem "backend\app","backend\tests" -Recurse -File -Include *.py | Select-String -Pattern "station|Station|STATION"
```
Expected: no output.

- [ ] **Step 4: Verify the key renamed declarations exist**

Run from the repo root:
```powershell
Select-String -Path "backend\app\models.py" -Pattern "class Genre"
Select-String -Path "backend\app\config.py" -Pattern "genre_tz"
Select-String -Path "backend\app\routers\genres.py" -Pattern "/api/genres"
Select-String -Path "backend\.env" -Pattern "GENRE_TZ"
```
Expected: one match each.

- [ ] **Step 5: Run the backend test suite**

Run (from `backend/`):
```
python -m pytest -q
```
Expected: same count as baseline, all passing. If a failure names a leftover `station` identifier, fix it and re-run.

- [ ] **Step 6: Checkpoint**

Backend tests green with the new `Genre` naming.

---

## Task 3: Frontend source rename

**Files:**
- Modify (in place): everything under `frontend/src/` (`*.ts`, `*.tsx`)
- Rename: `frontend/src/components/StationDial.tsx` → `frontend/src/components/GenreDial.tsx`
- Rename: `frontend/src/components/admin/StationsPanel.tsx` → `frontend/src/components/admin/GenresPanel.tsx`
- Rename: `frontend/src/components/admin/StationSelect.tsx` → `frontend/src/components/admin/GenreSelect.tsx`

- [ ] **Step 1: Run the case-aware rename script over the frontend sources**

Run from the repo root:
```powershell
$enc = New-Object System.Text.UTF8Encoding($false)
$files = Get-ChildItem -LiteralPath "frontend\src" -Recurse -File | Where-Object { $_.Extension -in '.ts', '.tsx' }
foreach ($f in $files) {
  $t = [System.IO.File]::ReadAllText($f.FullName)
  $n = $t.Replace('station','genre').Replace('Station','Genre').Replace('STATION','GENRE')
  if ($n -ne $t) { [System.IO.File]::WriteAllText($f.FullName, $n, $enc); "updated $($f.FullName)" }
}
```

- [ ] **Step 2: Rename the frontend component files**

Run from the repo root:
```powershell
Move-Item -LiteralPath "frontend\src\components\StationDial.tsx" -Destination "frontend\src\components\GenreDial.tsx"
Move-Item -LiteralPath "frontend\src\components\admin\StationsPanel.tsx" -Destination "frontend\src\components\admin\GenresPanel.tsx"
Move-Item -LiteralPath "frontend\src\components\admin\StationSelect.tsx" -Destination "frontend\src\components\admin\GenreSelect.tsx"
```

- [ ] **Step 3: Verify no unintended leftovers**

Run from the repo root:
```powershell
Get-ChildItem "frontend\src" -Recurse -File -Include *.ts,*.tsx | Select-String -Pattern "station|Station|STATION"
```
Expected: no output. (The CSS file is covered in Step 4.)

- [ ] **Step 4: Verify renamed CSS classes and API path**

Run from the repo root:
```powershell
Select-String -Path "frontend\src\styles\vintage.css" -Pattern "\.genre-row",".genre-list"
Select-String -Path "frontend\src\api\client.ts" -Pattern "/api/genres"
```
Expected: matches present; no `.station-` matches remain in `vintage.css`.

- [ ] **Step 5: Run frontend typecheck and tests**

Run (from `frontend/`):
```
npm run typecheck
npm test
```
Expected: typecheck clean; same passing test count as baseline. Fix any import path that still points at the old filenames.

- [ ] **Step 6: Checkpoint**

Frontend builds and tests green with the new naming.

---

## Task 4: Database migration and migration test

**Files:**
- Create: `backend/tests/test_migration_station_to_genre.py`
- Create: `backend/alembic/versions/c1a2b3c4d5e6_rename_station_to_genre.py`

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/test_migration_station_to_genre.py`:
```python
import json
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


def _seed_legacy(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO station (id, name, slug, is_default, sort_order) "
        "VALUES (1, 'Morning', 'morning', 1, 0)"
    )
    cur.execute(
        "INSERT INTO playlist (id, station_id, youtube_playlist_id, label) "
        "VALUES (1, 1, 'PL1', '')"
    )
    cur.execute(
        "INSERT INTO scheduleslot "
        "(id, station_id, days_of_week, start_time, end_time) "
        "VALUES (1, 1, '[0,1,2,3,4,5,6]', '00:00', '23:59')"
    )
    cur.execute("INSERT INTO setting (key, value) VALUES ('station_order:1', '[\"a\"]')")
    cur.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?)",
        (
            "broadcast_state",
            json.dumps(
                {
                    "station_id": 1,
                    "track_ids": [],
                    "durations": [],
                    "index": 0,
                    "started_at_utc": "2026-01-01T00:00:00",
                    "manual": False,
                }
            ),
        ),
    )
    con.commit()
    con.close()


def test_station_to_genre_migration_preserves_data(tmp_path):
    db_path = tmp_path / "mig.db"
    db_url = f"sqlite:///{db_path}"
    _alembic(db_url, "upgrade", "b2f4c1a9d3e7")
    _seed_legacy(db_path)
    _alembic(db_url, "upgrade", "head")

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    tables = {
        r[0]
        for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "genre" in tables
    assert "station" not in tables

    assert cur.execute("SELECT name FROM genre WHERE id = 1").fetchone()[0] == "Morning"
    assert cur.execute("SELECT genre_id FROM playlist WHERE id = 1").fetchone()[0] == 1
    assert cur.execute("SELECT genre_id FROM scheduleslot WHERE id = 1").fetchone()[0] == 1

    keys = {r[0] for r in cur.execute("SELECT key FROM setting")}
    assert "genre_order:1" in keys
    assert "station_order:1" not in keys

    value = cur.execute(
        "SELECT value FROM setting WHERE key = 'broadcast_state'"
    ).fetchone()[0]
    data = json.loads(value)
    assert data["genre_id"] == 1
    assert "station_id" not in data

    indexes = {
        r[0]
        for r in cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "ix_genre_slug" in indexes
    assert "ix_station_slug" not in indexes
    assert "ix_playlist_genre_id" in indexes
    assert "ix_scheduleslot_genre_id" in indexes
    con.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`):
```
python -m pytest tests/test_migration_station_to_genre.py -v
```
Expected: FAIL — `genre`/`genre_id` not present after `upgrade head` (the rename migration does not exist yet).

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/c1a2b3c4d5e6_rename_station_to_genre.py`:
```python
"""rename station to genre

Revision ID: c1a2b3c4d5e6
Revises: b2f4c1a9d3e7
Create Date: 2026-10-06 00:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, None] = "b2f4c1a9d3e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE station RENAME TO genre")
    op.execute("ALTER TABLE playlist RENAME COLUMN station_id TO genre_id")
    op.execute("ALTER TABLE scheduleslot RENAME COLUMN station_id TO genre_id")

    op.execute("DROP INDEX IF EXISTS ix_station_slug")
    op.execute("CREATE UNIQUE INDEX ix_genre_slug ON genre (slug)")
    op.execute("DROP INDEX IF EXISTS ix_playlist_station_id")
    op.execute("CREATE INDEX ix_playlist_genre_id ON playlist (genre_id)")
    op.execute("DROP INDEX IF EXISTS ix_scheduleslot_station_id")
    op.execute("CREATE INDEX ix_scheduleslot_genre_id ON scheduleslot (genre_id)")

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE setting SET key = replace(key, 'station_order:', 'genre_order:') "
            "WHERE key LIKE 'station_order:%'"
        )
    )
    row = conn.execute(
        sa.text("SELECT value FROM setting WHERE key = 'broadcast_state'")
    ).first()
    if row is not None and row[0]:
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict) and "station_id" in data:
            data["genre_id"] = data.pop("station_id")
            conn.execute(
                sa.text(
                    "UPDATE setting SET value = :v WHERE key = 'broadcast_state'"
                ),
                {"v": json.dumps(data)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT value FROM setting WHERE key = 'broadcast_state'")
    ).first()
    if row is not None and row[0]:
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict) and "genre_id" in data:
            data["station_id"] = data.pop("genre_id")
            conn.execute(
                sa.text(
                    "UPDATE setting SET value = :v WHERE key = 'broadcast_state'"
                ),
                {"v": json.dumps(data)},
            )
    conn.execute(
        sa.text(
            "UPDATE setting SET key = replace(key, 'genre_order:', 'station_order:') "
            "WHERE key LIKE 'genre_order:%'"
        )
    )

    op.execute("ALTER TABLE playlist RENAME COLUMN genre_id TO station_id")
    op.execute("ALTER TABLE scheduleslot RENAME COLUMN genre_id TO station_id")
    op.execute("DROP INDEX IF EXISTS ix_playlist_genre_id")
    op.execute("CREATE INDEX ix_playlist_station_id ON playlist (station_id)")
    op.execute("DROP INDEX IF EXISTS ix_scheduleslot_genre_id")
    op.execute("CREATE INDEX ix_scheduleslot_station_id ON scheduleslot (station_id)")
    op.execute("DROP INDEX IF EXISTS ix_genre_slug")
    op.execute("ALTER TABLE genre RENAME TO station")
    op.execute("CREATE UNIQUE INDEX ix_station_slug ON station (slug)")
```

- [ ] **Step 4: Run the migration test to verify it passes**

Run (from `backend/`):
```
python -m pytest tests/test_migration_station_to_genre.py -v
```
Expected: PASS.

- [ ] **Step 5: Scrub the throwaway test database if one was created**

Run from the repo root:
```powershell
Test-Path "backend\mig.db"
```
Expected: `False` (the test uses `tmp_path`). If a `mig.db` or stray `radio.db` was created during manual testing, delete it.

- [ ] **Step 6: Run the full backend suite**

Run (from `backend/`):
```
python -m pytest -q
```
Expected: baseline count plus 1, all passing.

- [ ] **Step 7: Checkpoint**

Migration applies old→new preserving data, and is reversible.

---

## Task 5: Documentation rename

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the case-aware rename script over the README**

Run from the repo root:
```powershell
$enc = New-Object System.Text.UTF8Encoding($false)
$f = Get-Item -LiteralPath "README.md"
$t = [System.IO.File]::ReadAllText($f.FullName)
$n = $t.Replace('station','genre').Replace('Station','Genre').Replace('STATION','GENRE')
if ($n -ne $t) { [System.IO.File]::WriteAllText($f.FullName, $n, $enc); "updated README.md" }
```

- [ ] **Step 2: Verify the env-var table and prose**

Run from the repo root:
```powershell
Select-String -Path "README.md" -Pattern "GENRE_TZ"
Get-ChildItem "README.md" | Select-String -Pattern "station|Station"
```
Expected: `GENRE_TZ` present; no `station`/`Station` matches.

- [ ] **Step 3: Checkpoint**

README reflects the new naming. Leave `docs/` unchanged.

---

## Task 6: Rebuild and verify in Docker

**Files:** none (build/run only).

- [ ] **Step 1: Rebuild the backend and frontend images**

Run from the repo root:
```
docker compose build backend frontend
```
Expected: both images build successfully.

- [ ] **Step 2: Recreate the containers (backend entrypoint runs the migration)**

Run from the repo root:
```
docker compose up -d backend frontend
```
Expected: `backend` and `frontend` recreated and started; dependencies (`caddy`) remain up.

- [ ] **Step 3: Confirm the migration ran against the live volume**

Run from the repo root:
```
docker compose logs backend
```
Expected: Alembic logs show upgrade to revision `c1a2b3c4d5e6`; no errors.

- [ ] **Step 4: Confirm the API serves the new shape**

Run from the repo root (PowerShell):
```
Invoke-RestMethod http://localhost:8011/api/now | ConvertTo-Json -Depth 5
```
Expected: JSON contains a top-level `genre` object (not `station`) and `"source"`.

- [ ] **Step 5: Manual UI verification**

Hard-refresh the admin panel (`https://localhost:8010/admin`, Ctrl+Shift+R) and confirm:
- The station selector is labeled "Genre" and lists the existing genre(s).
- Playlists and schedule still show their genre names.
- The public page (`https://localhost:8010/`) still loads, shows the now-playing genre, and plays.

- [ ] **Step 6: Checkpoint**

Renamed app runs end-to-end against the migrated data.

---

## Self-review

- **Spec coverage:** DB rename (Task 4), backend module/classes/route/JSON fields/config (Task 2), frontend types/components/CSS/API (Task 3), env + docs (Tasks 2 and 5), tests (Tasks 2–4), Docker verification (Task 6). All spec sections covered.
- **Placeholder scan:** none.
- **Type consistency:** `Genre`, `GenreOut`, `GenreDetail`, `genre_id`, `genre_name`, `genre_tz`, `/api/genres`, `genre_order:` are used consistently across tasks. The migration test deliberately keeps legacy `station*` literals.
