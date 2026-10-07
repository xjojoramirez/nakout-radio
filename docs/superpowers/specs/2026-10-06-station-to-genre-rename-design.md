# Station → Genre Rename — Design

## Goal

Rename the application's core "Station" concept to "Genre" across every layer:
database, backend code/API, frontend code/UI, configuration, tests, and docs.
Existing data (playlists, schedules, cached tracks, playback state) must be
preserved.

## Approach

In-place SQLite rename via a single Alembic migration (approach A). SQLite
supports `ALTER TABLE ... RENAME TO` and `RENAME COLUMN`, so no table
recreation or data copy is needed. The same migration rewrites the persisted
`Setting` keys that embed the old name.

No backwards-compatibility aliases are kept: the frontend and backend are the
only consumers and ship together.

## Rename mapping

### Database

| From | To |
| --- | --- |
| table `station` | `genre` |
| index `ix_station_slug` | `ix_genre_slug` |
| `playlist.station_id` | `playlist.genre_id` |
| index `ix_playlist_station_id` | `ix_playlist_genre_id` |
| `scheduleslot.station_id` | `scheduleslot.genre_id` |
| index `ix_scheduleslot_station_id` | `ix_scheduleslot_genre_id` |
| `Setting` key `station_order:<id>` | `genre_order:<id>` |

Unchanged tables/columns: `playlist`, `trackcache`, `scheduleslot`, `setting`,
`is_default`, `slug`, `sort_order`.

### Backend

| From | To |
| --- | --- |
| `app/routers/stations.py` | `app/routers/genres.py` |
| router prefix `/api/stations` | `/api/genres` |
| class `Station` (model) | `Genre` |
| class `StationOut` | `GenreOut` |
| class `StationDetail` | `GenreDetail` |
| class `CurrentStationOut` | `CurrentGenreOut` |
| class `StationRefIn` | `GenreRefIn` |
| JSON field `station` | `genre` |
| JSON field `station_id` | `genre_id` |
| JSON field `station_name` | `genre_name` |
| `STATION_TZ` / `station_tz` | `GENRE_TZ` / `genre_tz` |
| helpers `load_order`/`save_order` prefix `station_order:` | `genre_order:` |
| function/variable names containing `station` | `genre` equivalents |

Unchanged: `Track`, `Playlist`, `ScheduleSlot`, `Setting`; `source` values
(`schedule`, `default`, `manual`, `none`); route behavior.

The 404 detail `station not found` becomes `genre not found`.

### Frontend

| From | To |
| --- | --- |
| `components/StationDial.tsx` | `components/GenreDial.tsx` |
| `components/admin/StationsPanel.tsx` | `components/admin/GenresPanel.tsx` |
| `components/admin/StationSelect.tsx` | `components/admin/GenreSelect.tsx` |
| type `Station` | `Genre` |
| type `StationDetail` | `GenreDetail` |
| type `CurrentStation` | `CurrentGenre` |
| `AddedPlaylist.station_id` / `station_name` | `genre_id` / `genre_name` |
| API client methods `stationTracks`, `setStationOrder`, etc. | `genreTracks`, `setGenreOrder`, etc. |
| API path `/api/stations` | `/api/genres` |
| CSS classes `.station-*` | `.genre-*` |
| user-visible labels "Station"/"Stations" | "Genre"/"Genres" |

Unchanged: UI layout and behavior; `Track`; `source` values.

### Config and docs

- `backend/.env`, `backend/.env.example`: `STATION_TZ` → `GENRE_TZ`.
- `README.md`: update the station terminology and env var table; the prose
  describing the single always-on broadcast may keep the word "broadcast" but
  change "station" references to "genre".
- `docs/` design/plan files are historical; not rewritten.

## Testing

- Backend: update and run the full pytest suite
  (`backend/tests/`, including `test_stations.py` → `test_genres.py`).
  Add/adjust a migration test that upgrades a DB seeded with the old schema and
  asserts `genre`/`genre_id` exist and `station_order:` keys were rewritten.
- Frontend: update and run the full vitest suite (`npm test`), plus
  `npm run typecheck`.
- Manual: rebuild and recreate the Docker `frontend` and `backend` containers;
  verify the admin panel and public radio page load, a genre can be selected,
  tracks/queue render, and schedule editing works against the migrated data.

## Out of scope

- Changing the playback/scheduling logic or UI behavior.
- Renaming the `Playlist` concept.
- Rewriting historical docs under `docs/superpowers/`.
- Backwards-compatible API aliases.

## Risks

- Migration must run against the live Docker `radio_data` volume; verify SQLite
  version supports `RENAME COLUMN` (SQLite ≥ 3.25; Python 3.12 image is fine).
- Alembic autogenerate/offline mode: write the migration explicitly rather than
  relying on autogenerate for the table rename.
- The `Setting` key rewrite is a data update, not a schema change; it must be
  part of the migration so saved queue orders survive.
