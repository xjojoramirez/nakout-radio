# Nakout 2.0 Music Library API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authenticated library export/import API and make tracks permanent library records that detach from playlists instead of being deleted.

**Architecture:** `TrackCache` becomes the library table with an optional `playlist_id`. A shared reconciliation helper is used by YouTube sync and the new import endpoint. `app/library.py` builds snapshots and merges them; `app/routers/library.py` exposes `/api/library/*` behind a bearer key. The radio continues to read only tracks attached to a playlist in the active genre.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, Alembic (SQLite batch mode), Pydantic v2, pytest, React/Vitest.

---

## File map

**Create**

- `backend/alembic/versions/b7c1d2e3f4a5_nullable_playlist_id.py`
- `backend/app/library.py`
- `backend/app/library_schemas.py`
- `backend/app/routers/library.py`
- `backend/tests/test_library.py`
- `backend/tests/test_library_import.py`
- `scripts/pull_library.py`
- `frontend/src/components/admin/TrackLibraryPanel` changes/tests

**Modify**

- `backend/app/models.py` — nullable `playlist_id`, docstrings
- `backend/app/sync.py` — reconcile instead of delete/recreate
- `backend/app/routers/admin.py` — detach on playlist/genre delete
- `backend/app/config.py` — library API settings
- `backend/app/main.py` — register router, version
- `backend/app/schemas.py` — `has_playlist`
- `backend/app/track_details.py` — `unassigned` filter and `has_playlist`
- `backend/app/routers/tracks.py` — studio `unassigned` query param
- `backend/app/__init__.py` — `__version__ = "2.0.0"`
- `backend/.env.example` — new keys
- `backend/tests/test_sync.py`, `test_admin.py`, `test_track_details.py`
- `frontend/src/types.ts`, `frontend/src/api/client.ts`
- `frontend/src/components/admin/TrackLibraryPanel.tsx` and its test
- `frontend/src/components/admin/GenresPanel.tsx` and its test
- `frontend/src/components/admin/PlaylistsPanel.tsx` and its test
- `README.md`, `docs/changelog.md`

---

## Task 1: Make `playlist_id` nullable

**Files:** `backend/app/models.py`, new Alembic revision, `backend/tests/test_migration_nullable_playlist.py`

- [ ] Write a migration test that creates a DB at the previous head, inserts a track, upgrades to head, asserts `PRAGMA table_info(trackcache)` reports `playlist_id` nullable and the row survives.
- [ ] Run it and watch it fail because the migration does not exist.
- [ ] Change the model:

```python
class TrackCache(SQLModel, table=True):
    """A library track, optionally attached to a playlist.

    ``playlist_id`` is NULL for standalone tracks that were detached when a
    playlist stopped listing them. They stay in the library and API but never
    enter a genre rotation.
    """

    id: int | None = Field(default=None, primary_key=True)
    playlist_id: int | None = Field(
        default=None, foreign_key="playlist.id", index=True
    )
    # ... existing fields unchanged
```

- [ ] Add the migration:

```python
revision = "b7c1d2e3f4a5"
down_revision = "d8e9f0a1b2c3"

def upgrade() -> None:
    with op.batch_alter_table("trackcache") as batch_op:
        batch_op.alter_column(
            "playlist_id", existing_type=sa.Integer(), nullable=True
        )

def downgrade() -> None:
    op.execute("DELETE FROM trackcache WHERE playlist_id IS NULL")
    with op.batch_alter_table("trackcache") as batch_op:
        batch_op.alter_column(
            "playlist_id", existing_type=sa.Integer(), nullable=False
        )
```

- [ ] Run the migration test and the existing migration tests.

**Verify:** `pytest tests/test_migration_nullable_playlist.py tests/test_migration_station_to_genre.py -v`

---

## Task 2: Detach helpers and reconciliation

**Files:** `backend/app/library.py` (new), `backend/app/sync.py`, `backend/tests/test_sync.py`

- [ ] Add failing sync tests:
  - removing `v2` from a playlist leaves a row with `playlist_id is None` and `position == 0`;
  - re-adding `v2` reuses the detached row (same `id`);
  - a track present in a second playlist is removed from the first without
    creating a standalone duplicate;
  - existing row IDs are preserved across a sync.

- [ ] Implement the shared helpers in `app/library.py`:

```python
@dataclass
class IncomingTrack:
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    position: int = 0
    gain_db: float | None = None


def detach_membership(session: Session, row: TrackCache) -> bool:
    """Keep the track, drop this membership. True when the row was detached."""
    other = session.exec(
        select(TrackCache).where(
            TrackCache.youtube_video_id == row.youtube_video_id,
            TrackCache.id != row.id,
        )
    ).first()
    if other is not None:
        session.delete(row)
        return False
    row.playlist_id = None
    row.position = 0
    session.add(row)
    return True
```

`reconcile_playlist(session, playlist, incoming, *, preserve_gain)`
returns counts and updates rows in place. It must:

1. Index existing memberships by video ID.
2. Index standalone rows for incoming video IDs.
3. For each incoming track: reuse membership, else re-attach standalone, else
   create. Preserve `gain_db` when `preserve_gain` and title/artist match;
   otherwise copy the incoming gain when it is not null.
4. Delete unused standalone duplicates.
5. Call `detach_membership` on memberships no longer present.

- [ ] Rewrite `sync_playlist` to call `reconcile_playlist` and return
  `len(tracks)`.

**Verify:** `pytest tests/test_sync.py -v`

---

## Task 3: Destructive admin paths detach

**Files:** `backend/app/routers/admin.py`, `backend/tests/test_admin.py`

- [ ] Update the failing tests:
  - `test_delete_genre_removes_children` now expects the track row to remain
    with `playlist_id is None`; playlists/slots/history/genre are gone.
  - `test_delete_playlist_removes_tracks` now expects the track row to remain
    detached.
  - `test_delete_playlist_leaves_other_playlists_tracks` still expects only
    the surviving playlist membership.
- [ ] Replace bulk `delete(TrackCache)` in `delete_playlist` and `delete_genre`
  with `detach_membership` loops.
- [ ] Run the admin tests.

**Verify:** `pytest tests/test_admin.py -v -k "delete_genre or delete_playlist"`

---

## Task 4: Library schemas and snapshot builder

**Files:** `backend/app/library_schemas.py`, `backend/app/library.py`, `backend/tests/test_library.py`

- [ ] Define `LibraryGenreOut`, `LibraryPlaylistOut`,
  `LibraryPlaylistManifestOut`, `LibraryDetailOut`, `LibraryTrackOut`,
  `LibrarySnapshotOut`, `LibraryListOut`, `LibraryMetaOut`,
  `LibraryImportIn`, `LibraryImportOut` as specified in the design.
- [ ] Add a validator rejecting duplicate `(youtube_playlist_id,
  youtube_video_id)` memberships and unknown manifest references.
- [ ] Implement `build_snapshot(session)`, `list_tracks(session, group, limit,
  offset)`, `get_track(session, video_id)`, and `meta(session)`.
- [ ] Tests:
  - one track in two playlists appears once with two memberships;
  - standalone tracks appear with `playlists == []` and in
    `group=unassigned`;
  - the manifest includes a playlist with zero tracks;
  - `get_track` returns 404 for an unknown video;
  - track counts and `unassigned_tracks` are correct.

**Verify:** `pytest tests/test_library.py -v`

---

## Task 5: Auth, config, router

**Files:** `backend/app/config.py`, `backend/app/main.py`,
`backend/app/routers/library.py`, `backend/.env.example`,
`backend/tests/test_library.py`

- [ ] Add `library_api_key: str = ""` and
  `library_import_enabled: bool = False` to settings.
- [ ] Implement `require_library_key` with `hmac.compare_digest`; 503 when the
  key is unset, 401 when missing/wrong.
- [ ] Add the import gate returning 404 when disabled.
- [ ] Register the router and set the FastAPI version to `2.0.0`.
- [ ] Tests: 503/401/200, disabled import, correct key.

**Verify:** `pytest tests/test_library.py -v -k "auth or config"`

---

## Task 6: Snapshot import

**Files:** `backend/app/library.py`, `backend/tests/test_library_import.py`

- [ ] Tests for:
  - importing into an empty DB creates genres, playlists, tracks, details;
  - a track in two playlists creates two membership rows and one detail;
  - re-import is idempotent;
  - local locks block field overwrite while unlocked fields update;
  - `dj_note` lock also blocks `dj_note_public`;
  - charts are replaced unless `"charts"` is locked;
  - a track removed from a playlist becomes standalone;
  - a track returning to a playlist re-attaches;
  - `playlists: []` creates a standalone track;
  - unknown `schema_version` returns 422;
  - `dry_run` changes nothing.

- [ ] Implement `apply_snapshot(session, snapshot, dry_run)`:
  1. Upsert genres.
  2. Upsert playlists.
  3. Reconcile each manifest playlist.
  4. Update canonical track metadata; ensure standalone rows.
  5. Merge details and charts.
  6. Commit, or roll back for dry-run.
- [ ] Add the `POST /api/library/import` endpoint with a `dry_run` query flag.

**Verify:** `pytest tests/test_library_import.py -v`

---

## Task 7: Studio "No playlist" group

**Files:** `backend/app/schemas.py`, `backend/app/track_details.py`,
`backend/app/routers/tracks.py`, `frontend/src/types.ts`,
`frontend/src/api/client.ts`, `frontend/src/components/admin/TrackLibraryPanel.tsx`,
`frontend/src/components/admin/TrackLibraryPanel.dom.test.tsx`

- [ ] Add `has_playlist: bool = True` to `TrackLibraryItem`.
- [ ] In `library_page`, build the set of assigned video IDs from rows with a
  non-null `playlist_id`; set `has_playlist`; add an `unassigned` filter.
- [ ] Add `unassigned?: boolean` to the Studio endpoint and client.
- [ ] Add a "No playlist" checkbox and row badge.
- [ ] Update tests.

**Verify:** `pytest tests/test_track_details.py -v` and
`npm test -- TrackLibraryPanel` in `frontend/`.

---

## Task 8: Confirmation copy

**Files:** `GenresPanel.tsx`, `PlaylistsPanel.tsx` and their DOM tests.

- [ ] Genre message: `Delete “X” and its playlists and schedule slots? Tracks
  stay in the library.`
- [ ] Playlist message: `Remove "X"? Its tracks stay in the library.`
- [ ] Update assertions.

**Verify:** `npm test -- GenresPanel PlaylistsPanel` in `frontend/`.

---

## Task 9: CLI

**Files:** `scripts/pull_library.py`, `README.md`

- [ ] Implement the stdlib client described in the design.
- [ ] Handle non-2xx responses with the body, normalize trailing slashes,
  print a summary, support `--dry-run` and `--save`.
- [ ] Document live and local usage, key generation, and the exact commands.

**Verify:** `python scripts/pull_library.py --help` and a dry run against the
local backend.

---

## Task 10: Docs, changelog, full verification

**Files:** `docs/changelog.md`, `README.md`

- [ ] Add a changelog entry at the top with date, summary, files, restart
  command (`docker compose up -d --build backend frontend`), and verification.
- [ ] Add the README library API section.
- [ ] Run:
  - `backend/.venv/Scripts/python -m pytest` (or the project's pytest command)
  - `npm test` and `npm run build` in `frontend/`
  - migration on a copy of the local volume DB
  - CLI dry run

---

## Self-review checklist

- [ ] Every design section maps to a task.
- [ ] No placeholders remain.
- [ ] Type names match across schemas, library code, router, tests, and CLI.
- [ ] `playlist_id` nullability is handled everywhere it is read.
- [ ] V1 public routes are untouched.
