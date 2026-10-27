# Nakout 2.0: Music Library API — Design

**Date:** 2026-10-27
**Status:** Approved for implementation
**Scope:** Nakout 2.0. V1 stays the radio-only product: no public route is
removed or renamed, and playback, scheduling, queueing, and the public site
keep their current behavior. The library API is additive.

## Core idea

> Playlists and schedules are views over the library, not owners of it.

A track is a permanent library record. Playlist membership is optional and may
come and go. Removing a track from a playlist **detaches** it; it is never
deleted. A detached track remains visible in Studio and in the library API, but
it is not part of any genre's rotation.

## Goals

- Expose the live station's music library over an authenticated, read-only API.
- Pull the live library into a local deployment with one command.
- Keep track metadata, stories, chart entries, locks, and provenance when a
  track leaves a playlist.
- Allow tracks to exist with no playlist at all.
- Make the "No playlist" set discoverable through a virtual group.

## Non-goals (v2.0)

- Schedule or playlist CRUD over the library API.
- Incremental `since` sync. The snapshot is a full export.
- Pushing local changes back to live.
- Postgres. SQLite remains sufficient.
- Persistent custom collections (`TrackGroup`). The only virtual group is
  `unassigned`.
- Automatic removal of playlists deleted on live.

## Data model

### TrackCache becomes the library table

`TrackCache.playlist_id` becomes nullable.

| `playlist_id` | Meaning |
|---|---|
| integer | A playlist membership row. The track is in that playlist's genre rotation. |
| `NULL` | A standalone library track. It is not in any rotation. |

Invariants, enforced in application code:

- At most one row per `(playlist_id, youtube_video_id)` membership.
- At most one standalone row (`playlist_id IS NULL`) per video.
- A video with a membership should not also have a standalone row; adding a
  membership re-attaches the standalone row.
- When the last membership is removed, the row is detached rather than deleted.

`TrackDetail` is unchanged. It is keyed by video ID, so stories, charts, locks,
and sources survive any membership change.

### Detach algorithm

`detach_membership(row)`:

1. If another row exists for the same video, delete this membership row.
   The track survives through the other row.
2. Otherwise set `playlist_id = NULL`, `position = 0`, and keep the row.

This converges to one standalone row when every membership is removed, even if
several memberships are removed in one operation.

### Behavior changes

| Operation | v2.0 behavior |
|---|---|
| Playlist sync | Fetch, then reconcile: update existing rows in place, insert new ones, detach removed ones. IDs are preserved where possible. |
| Delete playlist | Detach every membership in the playlist, then delete the playlist. |
| Delete genre | Detach tracks from every playlist in the genre, then delete the playlists, slots, play history, order setting, and genre. |
| Radio playback | Unchanged. Standalone rows have no genre and are never selected. |
| Enrichment / loudness | Unchanged. They already walk all cache rows, so standalone tracks keep improving. |

The two admin confirmation messages that promise track deletion are updated.

## Library API

Prefix `/api/library`. All routes require:

```
Authorization: Bearer <LIBRARY_API_KEY>
```

`LIBRARY_API_KEY` is a new optional setting. When empty the routes return 503
instead of allowing access. Comparison uses `hmac.compare_digest`.

The import route additionally requires `LIBRARY_IMPORT_ENABLED=true`; otherwise
it returns 404. The default is false, so a leaked live key cannot write.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/library/meta` | Schema version, app version, timestamp, counts. |
| GET | `/api/library/tracks?limit=&offset=&group=all\|unassigned` | Paginated unique tracks. |
| GET | `/api/library/tracks/{video_id}` | One track with memberships and detail. |
| GET | `/api/library/export` | Full snapshot. |
| POST | `/api/library/import?dry_run=` | Apply a snapshot (local only). |

`group=unassigned` is the virtual "No playlist" group: tracks with no
membership rows. It is derived at query time; nothing extra is stored.

### Track shape

```json
{
  "youtube_video_id": "abc123",
  "title": "Song",
  "artist": "Artist",
  "thumbnail_url": "https://...",
  "duration_seconds": 214,
  "gain_db": -1.4,
  "playlists": [
    {
      "youtube_playlist_id": "PL_rock",
      "label": "Rock",
      "genre": {
        "slug": "rock",
        "name": "Rock",
        "color": "#e0654a",
        "is_default": false,
        "sort_order": 1
      },
      "position": 12,
      "gain_db": -1.4
    }
  ],
  "detail": {
    "album": "…",
    "release_year": 1997,
    "label": "…",
    "genres": ["Alternative"],
    "moods": ["mellow"],
    "summary": "…",
    "story": "…",
    "dj_note": "…",
    "dj_note_public": true,
    "lyric_snippet": "…",
    "credits": [],
    "links": [],
    "similar_video_ids": [],
    "charts": [],
    "sources": {},
    "locked_fields": ["story"],
    "needs_review": false,
    "enriched_at": "…",
    "story_at": "…",
    "created_at": "…",
    "updated_at": "…"
  }
}
```

- A track appears once even when it is in several playlists.
- `playlists` may be empty.
- `detail` may be null.
- `gain_db` at the track level is the detached row's gain. Per-membership gain
  is authoritative for memberships.

### Snapshot

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-27T12:00:00Z",
  "playlists": [
    {
      "youtube_playlist_id": "PL_rock",
      "label": "Rock",
      "genre": { "...": "..." },
      "track_count": 12
    }
  ],
  "tracks": [ "...Track shape..." ]
}
```

The playlist manifest includes empty playlists. It is what lets import detach
stale memberships from a playlist that currently has no tracks.

Orphan `TrackDetail` rows (a detail whose video is in no cache row) are not
exported. Going forward detachment prevents new orphans; pre-existing orphans
are ignored.

## Import rules

- Validate `schema_version == 1`. Unknown versions return 422.
- Validate that every membership references a playlist in the manifest.
- Upsert genres by slug. Live name/color/order wins. If live says default and
  local already has a default, leave the local default alone.
- Upsert playlists by `youtube_playlist_id`. Update label and re-point the genre
  if live differs.
- For every playlist in the manifest, reconcile its membership:
  - Add missing memberships.
  - Re-attach a standalone row when the track returns.
  - Remove memberships that are not in the snapshot; the track is detached if
    it has no other membership.
- Every snapshot track is updated with canonical title/artist/thumbnail/
  duration. Tracks with `playlists: []` are ensured a standalone row unless
  they still have a membership in a local-only playlist.
- Details merge field by field:
  - Local `locked_fields` win: that field is not overwritten.
  - `dj_note` lock also protects `dj_note_public`.
  - Locks are unioned: local locks ∪ live locks.
  - `sources` follows the fields actually copied; a skipped field keeps its
    local provenance.
  - Charts are replaced unless `"charts"` is locally locked.
  - `needs_review` is OR-ed (a pull can raise it, never clear it).
  - `enrich_error` / `story_error` are never imported.
  - A null `detail` never clears a local detail.
- No track or detail is ever deleted.
- The whole import runs in one transaction. `dry_run=true` rolls it back.
- Re-importing the same snapshot is idempotent.

Local-only playlists are never modified except by membership reconciliation for
playlists present in the snapshot. A playlist deleted on live therefore remains
locally until the operator removes it; deleting it in Studio safely detaches its
tracks.

## CLI

New `scripts/pull_library.py`, standard library only:

```powershell
python scripts/pull_library.py `
  --from https://radio.example.com `
  --to http://localhost:8011 `
  --key $env:LIBRARY_API_KEY `
  [--import-key ...] [--dry-run] [--save snapshot.json]
```

It fetches `/api/library/export`, posts it to `/api/library/import`, and prints
the created/updated/detached counts. `--dry-run` asks the local server to
validate and count without committing.

## Studio

- `TrackLibraryItem.has_playlist` and an `unassigned` filter on
  `GET /api/studio/tracks`.
- A `No playlist` badge and filter checkbox in the library panel.
- Updated delete-confirmation copy:
  - Genre: "Delete X and its playlists and schedule slots? Tracks stay in the
    library."
  - Playlist: "Remove X? Its tracks stay in the library."

## Configuration

New backend settings:

```
LIBRARY_API_KEY=
LIBRARY_IMPORT_ENABLED=false
```

- Live: set a random key; leave import disabled.
- Local: same key (or a different one) and `LIBRARY_IMPORT_ENABLED=true`.

## Testing

- Unit tests for detach/re-attach and sync ID preservation.
- Admin tests for playlist/genre deletion preserving tracks.
- API tests for auth, meta, list, unassigned filter, export shape, multi-playlist
  grouping, and standalone tracks.
- Import tests for create/update, lock preservation, chart replacement, dry-run,
  idempotency, and malformed payloads.
- Migration test on a copy of the local database.
- Frontend DOM tests for the badge/filter and copy.
- CLI dry run against the local API.

## Deployment

- Backend and frontend images must be rebuilt:
  `docker compose up -d --build backend frontend`.
- Alembic runs on backend start and makes `trackcache.playlist_id` nullable.
- No Caddy change. No frontend hard-refresh requirement beyond the rebuild.

## Risks

- **Nullable FK migration** on SQLite requires a table rebuild; Alembic batch
  mode is used. Verify on a copy of the volume DB before deploying live.
- **Concurrent sync and import** both reconcile memberships. SQLite serializes
  writers; keep the import transaction short and run it in a quiet moment.
- **Live deletion of a playlist** is not mirrored automatically in v2.0. The
  local playlist can be deleted manually; tracks are detached, not lost.
- **Track metadata conflicts** across playlists are resolved by using the most
  recently fetched row and applying it to all memberships.
