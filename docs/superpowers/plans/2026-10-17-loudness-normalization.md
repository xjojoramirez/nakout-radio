# Loudness normalization — implementation plan

**Goal:** every track plays at roughly the same perceived loudness at a given
fader position, using Deezer `gain` metadata applied as a per-track offset to
`player.setVolume`.

**Spec:** `docs/superpowers/specs/2026-10-17-loudness-normalization-design.md`

**Branch:** `feat/loudness-normalization-23` (base `main`; land via PR, body
must end with the `Container restart` section).

**Test commands:** backend `cd backend && python -m pytest -q`; frontend
`cd frontend && npm run test && npm run typecheck`.

## File structure

Backend:

- `app/models.py` — two columns + `volume_offset_db` property.
- `app/loudness.py` — new: title cleaning, matching, Deezer lookup, enrichment
  runner, backfill trigger.
- `app/sync.py` — preserve loudness across re-syncs.
- `app/config.py` — `loudness_target_db`, `loudness_max_boost_db`,
  `loudness_lookup_enabled`.
- `app/schemas.py` — `TrackOut.volume_offset_db`.
- `app/main.py` — lifespan starts the backfill.
- `app/routers/admin.py` — trigger backfill after syncs.
- `alembic/versions/<new>_track_loudness.py` — columns.
- `backend/.env.example` — document new vars.
- Tests: `tests/test_loudness.py` (new), `tests/test_sync.py`,
  `tests/test_models.py`, `tests/test_now.py`, `tests/conftest.py`.

Frontend:

- `src/utils/loudness.ts` — new pure helper + `loudness.unit.test.ts`.
- `src/types.ts` — `Track.volume_offset_db`.
- `src/hooks/useYouTubePlayer.ts` — apply offset at the four volume sites.
- `src/hooks/useYouTubePlayer.dom.test.ts` — new cases + fixture field.
- Fixtures: `RadioPage.dom.test.tsx`, `NowPlayingPanel.dom.test.tsx`,
  `GenresPanel.dom.test.tsx`, `useBroadcast.dom.test.ts` as typecheck demands.

---

### Task 1: spec + plan docs

- [ ] Commit `docs/superpowers/specs/2026-10-17-loudness-normalization-design.md`
      and this plan.

### Task 2: model columns, migration, sync preservation

- [ ] **Tests first** (`tests/test_models.py`, `tests/test_sync.py`):
  - offset property: `gain_db=None` → 0.0; `-15.0` → 0.0; `-7.0` → −8.0;
    `-19.3` → +4.3; `-30.0` → capped +6.0 boost... (−15−(−30) = +15 → cap 6).
  - re-sync same title/artist preserves `gain_db` + `gain_checked_at`;
    changed title resets both; new tracks start `None`.
- [ ] `models.py`: add columns and

  ```python
  @property
  def volume_offset_db(self) -> float:
      return offset_for_gain(self.gain_db)
  ```

  with `from app.loudness import offset_for_gain` (loudness must not import
  models at module top — see Task 3).
- [ ] `sync.py`: capture `{video_id: (title, artist, gain_db, checked_at)}`
      before the delete; restore on matching title+artist.
- [ ] Migration `f3a4b5c6d7e8_track_loudness.py`: `down_revision =
      "b2c3d4e5f6a7"`; `batch_alter_table("trackcache")` add
      `gain_db` Float nullable + `gain_checked_at` DateTime nullable; drop in
      downgrade.
- [ ] Commit: `feat: per-track loudness fields with re-sync preservation (#23)`.

### Task 3: `app/loudness.py`

- [ ] **Tests first** (`tests/test_loudness.py`), covering:
  - `clean_query`: `"Artist - Song (Official Video) [HD]"` →
    `("Song", "Artist")`; `"Hurricane (2015 - Remaster)"` + `""` →
    `("Hurricane", "")`; `"Artist - Song | Lyrics"` → cut at `|`.
  - `pick_candidate`: rejects `Glitch/Shiver` vs `Aaron Glitch/Shivers`
    (artist ratio < 0.6); picks exact-key match among remaster variants;
    artist-less query requires exact title key; returns `None` on empty.
  - `offset_for_gain` caps (boost cap from settings; attenuation cap −15).
  - `lookup_gain` with `httpx.MockTransport`: hit → float; gain `0`/missing →
    `None`; `{"error": ...}` payload → raises `DeezerLookupError`; search hit +
    detail fetched once.
  - `enrich_pending` with a fake `session_factory` and a stubbed
    `lookup_gain`: dedupes by video id while updating **all** rows; a miss
    sets `gain_checked_at` with `gain_db=None`; an error leaves the row
    pending; 5 consecutive errors abort the batch and return the processed
    count.
  - `ensure_backfill`: returns False when `loudness_lookup_enabled` is false
    (conftest default) and when already running (set the guard manually).
- [ ] Implement:

  ```python
  MAX_ATTENUATION_DB = 15.0
  _LOOKUP_PAUSE_S = 0.3
  _MAX_CONSECUTIVE_ERRORS = 5
  MIN_MATCH_RATIO = 0.6

  def offset_for_gain(gain_db: float | None) -> float: ...   # settings caps
  def clean_query(title: str, artist: str) -> tuple[str, str]: ...
  def pick_candidate(items, title, artist) -> dict | None: ...
  def lookup_gain(title, artist, client: httpx.Client) -> float | None: ...
  def enrich_pending(session_factory, client, *, limit=100,
                     pause_seconds=_LOOKUP_PAUSE_S, sleep=time.sleep) -> int: ...
  def ensure_backfill() -> bool: ...  # guarded daemon thread
  ```

  Notes: bracket segments removed **before** the `" - "` split (so
  `"...(2015 - Remaster)"` is handled); `from app.models import TrackCache`
  inside functions (models imports this module for the property);
  `httpx.Client(timeout=10, headers={"User-Agent": "nakout-radio/1.0 ..."})`;
  valid `gain` = finite, `< 0`, `> -60`; Deezer API error payloads raise
  `DeezerLookupError`; empty results are a definitive miss (`checked_at` set).
- [ ] Commit: `feat: Deezer loudness lookup + background enrichment (#23)`.

### Task 4: config, schema, triggers

- [ ] **Tests first** (`tests/test_loudness.py` / `tests/test_now.py`):
  - `/api/now` for a track with `gain_db=-7` reports
    `volume_offset_db == -8.0` (seed the DB row directly).
  - config defaults / validators (`loudness_target_db` in −60…0,
    `loudness_max_boost_db` in 0…24).
- [ ] `config.py`: the three settings + validators.
- [ ] `schemas.py`: `volume_offset_db: float = 0.0` on `TrackOut`.
- [ ] `main.py`: `lifespan` calling `ensure_backfill()`.
- [ ] `admin.py`: call `ensure_backfill()` after `sync_playlist` in
      `add_playlist`, `refresh_playlist`, `sync_all`.
- [ ] `conftest.py`: `os.environ.setdefault("LOUDNESS_LOOKUP_ENABLED", "false")`.
- [ ] `.env.example`: document the three vars.
- [ ] Commit: `feat: expose volume offsets and trigger backfill (#23)`.

### Task 5: frontend util

- [ ] **Tests first** (`src/utils/loudness.unit.test.ts`): 0/undefined/NaN →
      volume; ±6.02 dB halves/doubles; clamp at 100; rounding.
- [ ] Implement `applyVolumeOffset(volume, offsetDb)`.
- [ ] Commit: `test+feat: volume offset helper (#23)` (can share commits with
      Task 6).

### Task 6: hook integration

- [ ] Fixtures: add `volume_offset_db: 0` to Track literals (helpers in
      `useYouTubePlayer.dom.test.ts`, `RadioPage.dom.test.tsx`,
      `NowPlayingPanel.dom.test.tsx`, `GenresPanel.dom.test.tsx`;
      `useBroadcast.dom.test.ts` if typed).
- [ ] **Tests first** (`useYouTubePlayer.dom.test.ts`):
  - start applies `round(70 × 10^(offset/20))` for a track offset;
  - slider change re-applies with the offset;
  - preload promotion during a gap uses the **next** track's offset;
  - boost clamp at 100; absent/0 offset unchanged (existing tests cover this
    once fixtures are 0).
- [ ] Implement in `useYouTubePlayer.ts`:
  - `trackOffset(broadcast, videoId)` resolver (track → nextTrack → 0);
  - `volumeForVideo(videoId)` reading `volumeRef`/`broadcastRef`;
  - replace the four `setVolume(volumeRef.current)` / `setVolume(volume)`
    sites (onReady, `startPreloaded`, `scheduleSwap`, volume effect);
  - volume effect deps gain `broadcast?.track?.youtube_video_id` and
    `broadcast?.track?.volume_offset_db` so track changes/arrivals re-apply.
- [ ] `npm run test`, `npm run typecheck`.
- [ ] Commit: `feat: apply per-track loudness offset to the player (#23)`.

### Task 7: changelog, full verification, PR

- [ ] `docs/changelog.md` entry (top): summary, files, container restart
      (both), verification results, first-boot backfill note.
- [ ] Full runs: backend pytest, frontend test + typecheck + build.
- [ ] `gh auth switch --user xjojoramirez`; push branch; open PR closing #23;
      body ends with:
      `## Container restart` → `Yes — backend and frontend: docker compose up -d --build backend frontend`.

## Self-review

- Spec coverage: data model → T2; lookup/matching/backfill → T3; API surface
  and triggers → T4; frontend math/application → T5/T6; deployment notes →
  T7. Rejected alternative (yt-dlp analysis) not revisited — metadata approach
  approved.
- Risks: Deezer matching false positives (mitigated by ratio gate + tests);
  background thread hitting a locked SQLite (writes are one row per ~0.35 s;
  existing engine uses `check_same_thread=False`); thread disabled in tests.
- No placeholders; interfaces named consistently across tasks
  (`volume_offset_db`, `offset_for_gain`, `applyVolumeOffset`,
  `enrich_pending`, `ensure_backfill`).
