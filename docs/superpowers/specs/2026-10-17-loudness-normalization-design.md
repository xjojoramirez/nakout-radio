# Loudness normalization across tracks — design

Date: 2026-10-17
Branch: `feat/loudness-normalization-23`
Issue: #23

## Goal

A given master-volume position must sound roughly equally loud for every track.
Today some tracks are noticeably too loud and others too quiet: at the same
fader position, the loudest masters in the library run ~12 dB hotter than the
quietest ones.

Audio plays inside the YouTube iframe (cross-origin), so the browser cannot
analyze the stream and the app cannot measure loudness live. The only lever is
`player.setVolume(0-100)`, and the only data source is per-track loudness
metadata.

## Evidence (probe, 2026-10-17)

Deezer's keyless API exposes a per-track `gain` field (a loudness level: the
closer to 0, the louder the track). A random 30-track sample of the real
library measured:

- 29/30 confident artist+title matches; 29/30 with a usable `gain`.
- Range `-19.3` (quietest ballads) to `-6.8` (loudest nu-metal), average
  `-11.4`. The spread matches the complaint exactly: ballads sit ~15…19,
  loud rock/metal ~7…10.

## Data model

`TrackCache` gains:

- `gain_db: float | None` — raw Deezer loudness value; `None` = no data.
- `gain_checked_at: datetime | None` — set once a lookup completed (hit or
  definitive miss), so misses are not retried forever.

Lookups are best-effort: tracks without data simply get no correction and play
exactly as today.

`sync_playlist` currently deletes and re-inserts a playlist's rows. It must
preserve `gain_db`/`gain_checked_at` for video ids that reappear with the same
title+artist, and reset them when title or artist changed (the match may
differ; a re-check is worth it).

Alembic migration adds the two nullable columns (head `b2c3d4e5f6a7` →
new revision).

## Correction model

Per track: `offset_db = clamp(LOUDNESS_TARGET_DB - gain_db, -15, +LOUDNESS_MAX_BOOST_DB)`

- default target `-15.0`, max boost `+6.0` (both env-tunable, no rebuild
  needed to tune; attenuation is capped at −15 dB as a metadata sanity guard).
- A loud track (gain ≈ −7) gets ≈ −8 dB; a quiet ballad (gain ≈ −19) gets
  ≈ +4 dB; the station averages ≈ −3.6 dB quieter. Chosen "balance" option
  (approved 2026-10-17) — quieter tracks are pushed up toward the loud ones
  instead of anchoring everything at the quietest track.
- Effective player volume: `clamp(round(volume × 10^(offset/20)), 0, 100)`.
- Because YouTube caps at 100, boosts cannot exceed the track's natural
  maximum; near the top of the fader the quietest tracks can end up slightly
  below target. This is inherent and accepted; below roughly three-quarter
  fader the correction is exact.

`TrackCache.volume_offset_db` is a read-only property computing the offset, and
`TrackOut` exposes `volume_offset_db: float = 0.0`, so every existing
`TrackOut.model_validate(row)` call site gains the field with no changes.

## Lookup pipeline

New module `backend/app/loudness.py`:

- Pure helpers: YouTube-title cleaning (`"Artist - Song (Official Video)"` →
  title/artist), candidate matching (key containment with min length ratio
  0.6; exact-key preferred; artist-less titles require an exact title match —
  this rejects the probe's `Glitch/Shiver` → `Aaron Glitch/Shivers` false
  positive).
- `lookup_gain(title, artist, client)` — Deezer search (limit 5) + track
  detail, returns `float | None`; raises on API/transport errors.
- `enrich_pending(session_factory, client, ...)` — resolves up to N unchecked
  video ids; on success/miss sets `gain_db`/`gain_checked_at` on **all** rows
  with that video id; skips (leaves unchecked) on errors; aborts the batch
  after 5 consecutive errors.
- `ensure_backfill()` — starts a single-flight daemon thread (guarded; no-op
  when `LOUDNESS_LOOKUP_ENABLED=false`) that loops `enrich_pending` with a
  0.3 s pause between lookups.

Triggers: FastAPI lifespan on startup (initial backfill, ~4 min for 392
tracks) and after admin playlist syncs (new tracks). Tests disable the whole
thing via env.

## Frontend

- `Track.volume_offset_db: number`.
- New pure helper `applyVolumeOffset(volume, offsetDb)` (round + clamp 0–100;
  treats missing/non-finite offsets as 0 so old fixtures and any stale frames
  are harmless).
- `useYouTubePlayer` applies it at every point volume reaches a player:
  initial `onReady`, gap-start/`startPreloaded`, preload promotion
  (`scheduleSwap`), and the volume/mute effect — the effect also re-runs when
  the broadcast track or its offset changes, so a correction that arrives
  mid-track is applied.
- No UI change; no listener toggle (future work if it ever feels wrong).
- Only the listener page plays audio (`RadioPage`); the admin deck is
  display-only, so nothing to do there.

## Testing

- `backend/tests/test_loudness.py` — title cleaning, candidate matching
  (including the false-positive regression case), offset math and caps,
  `lookup_gain` with `httpx.MockTransport`, `enrich_pending` (dedupe by video
  id, miss marks checked, error leaves pending, consecutive-error abort),
  `ensure_backfill` disabled/guard cases.
- `backend/tests/test_sync.py` — loudness survives re-sync; resets on
  title/artist change.
- `backend/tests/test_now.py` — `/api/now` carries the computed
  `volume_offset_db`.
- `backend/tests/test_models.py` — property math on the model.
- `frontend/src/utils/loudness.unit.test.ts` — offset math, clamps, garbage
  input.
- `frontend/src/hooks/useYouTubePlayer.dom.test.ts` — adjusted volume on
  start, on slider change, on preload promotion; clamp; missing data.
- Fixture helpers gain `volume_offset_db: 0` where `Track` literals are built.
- `conftest.py` sets `LOUDNESS_LOOKUP_ENABLED=false` for the test process.

## Deployment

- Both containers: `docker compose up -d --build backend frontend`.
- First backend boot starts the background backfill (watch logs); tracks play
  uncorrected until their lookup lands.
- Tuning without rebuild: edit `LOUDNESS_TARGET_DB` / `LOUDNESS_MAX_BOOST_DB`
  in `backend/.env`, restart `backend` only.
- Hard-refresh the browser after the frontend rebuild.

## Out of scope

- Listener-facing toggle or strength slider.
- Admin manual per-track override (raw `gain_db` is kept in the DB, so one
  can be added later).
- Re-checking already-checked tracks when Deezer data improves.
