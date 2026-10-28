# Nakout Radio

A personal internet-radio website streaming the owner's YouTube playlists as a
single always-on broadcast, with a time-of-day scheduled genre, a live
listener count, and an admin panel.

Nakout 2.0 adds an authenticated **music library API** and makes every track a
permanent library record: removing a track from a playlist detaches it instead
of deleting it. The V1 radio, schedule, and public site keep working exactly as
before.

## Architecture

- `backend/` — FastAPI + SQLite. Reads playlist tracks via the YouTube Data
  API v3 and caches them. Serves genres, schedule, admin, the music library
  API, and a listener websocket.
- `frontend/` — React + Vite. Drives the YouTube IFrame Player and renders the
  vintage-radio UI.
- `caddy` — TLS termination and routing: `/` to frontend, `/api` and `/api/ws`
  to backend.

## Local development

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    |  macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
# Windows: copy .env.example .env    |  macOS/Linux: cp .env.example .env
# then edit .env and fill in YT_API_KEY, ADMIN_PASSWORD, SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` (including the websocket) to `http://localhost:8000`.

## Required configuration

Backend (`backend/.env`):

| Variable | Purpose |
| --- | --- |
| `YT_API_KEY` | YouTube Data API v3 key |
| `ADMIN_PASSWORD` | Admin login password |
| `SECRET_KEY` | Session signing key (long random string) |
| `GENRE_TZ` | Schedule timezone, e.g. `Asia/Manila` |
| `DATABASE_URL` | SQLite path |
| `FRONTEND_ORIGIN` | Allowed CORS origin |
| `CACHE_TTL_MINUTES` | Reserved for future automatic cache refresh; not yet used |
| `ENRICHMENT_ENABLED` | Automatic track details, stories and charts (default `true`) |
| `COOKIE_SECURE` | `true` in production (HTTPS); `false` for local http dev |
| `LIBRARY_API_KEY` | Bearer key for `/api/library/*`. Empty disables the API |
| `LIBRARY_IMPORT_ENABLED` | Allow `POST /api/library/import` (keep `false` on live) |

> Track details are enriched in the background: albums, release years, labels,
> credits and covers come from Deezer, with MusicBrainz filling gaps. Wikipedia
> supplies the liner-note story and chart history. All three are keyless public
> APIs.

Root (`.env`):

| Variable | Purpose |
| --- | --- |
| `DOMAIN` | Public domain for Caddy/TLS |

> Track caching is refreshed when a playlist is added (or re-added) and when you
> click **Sync all playlists** in the admin panel. There is no automatic timer
> yet, so `CACHE_TTL_MINUTES` is currently unused.

## Nakout 2.0: Music Library API

The library API exposes the station's tracks and editorial details over HTTP.
It is read-only except for the local-only import route. A track belongs to the
library permanently; playlist membership is optional. Removing a track from a
playlist detaches it, and it stays available as a "No playlist" library track.

### Authentication

Every route requires a bearer key:

```bash
LIBRARY_API_KEY=<random-secret>
```

Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

When `LIBRARY_API_KEY` is empty, the routes return **503** instead of allowing
access. Set the same key on live and local, or use different keys and pass the
local one with `--import-key`.

`POST /api/library/import` is additionally disabled unless
`LIBRARY_IMPORT_ENABLED=true`. Keep it `false` on the live station.

### Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/library/meta` | Version, timestamp, track/detail counts |
| `GET` | `/api/library/tracks?limit=50&offset=0&group=all` | Paginated unique tracks |
| `GET` | `/api/library/tracks/{video_id}` | One track with all memberships and details |
| `GET` | `/api/library/export` | Full snapshot, including empty playlists |
| `POST` | `/api/library/import?dry_run=true` | Apply a snapshot (local only) |

`group=unassigned` returns only the virtual **No playlist** group. A track in
several playlists appears once with a `playlists` array.

```bash
curl -H "Authorization: Bearer $LIBRARY_API_KEY" \
  https://radio.example.com/api/library/export > live-library.json
```

### Pulling live into local

The local backend must be reachable (default `http://localhost:8011`). Use the
live key for the source and the local key for the import:

```powershell
$liveKey = "<key set on the live backend>"
$localKey = ((Get-Content backend/.env |
  Where-Object { $_ -match '^LIBRARY_API_KEY=' }) -replace '^LIBRARY_API_KEY=','').Trim()

python scripts/pull_library.py `
  --from https://radio.example.com `
  --to http://localhost:8011 `
  --key $liveKey `
  --import-key $localKey
```

The script downloads `/api/library/export`, writes the snapshot to the local
`/api/library/import` route, and prints created/updated/detached counts. Add
`--dry-run` to validate and count without committing, or `--save snapshot.json`
to keep the downloaded snapshot.

If the live key is missing, the live API returns **503**. If the local import is
disabled, the local API returns **404**.

The import merges rather than replaces:

- Live values win, except for fields in the local track's `locked_fields`.
- New tracks and details are added; existing ones are updated.
- Tracks removed from a live playlist are detached locally, never deleted.
- Local-only playlists and tracks are left alone.
- Re-running the same snapshot is idempotent.

### Pushing local stories to live

The normal direction is live -> local. If you have curated stories locally
and want them on live without touching live playlists or metadata, use
`scripts/push_stories.py`. It matches tracks by video ID, copies only
`summary`, `story` and `dj_note`, and sends a playlist-free snapshot, so live
memberships are never reconciled. Live album/year/label, charts and every
other detail field are preserved.

By default it pushes only story fields already in the local `locked_fields`.
Use `--all` to include unlocked provider prose, and `--no-lock` to leave
transferred fields unlocked (live enrichment may overwrite them).

The live import route must be enabled for the duration of the push:

```bash
# on live
sed -i 's/^LIBRARY_IMPORT_ENABLED=.*/LIBRARY_IMPORT_ENABLED=true/' backend/.env
docker compose up -d backend
```

Then, from local:

```powershell
$liveKey = "<key set on the live backend>"
$localKey = ((Get-Content backend/.env |
  Where-Object { $_ -match '^LIBRARY_API_KEY=' }) -replace '^LIBRARY_API_KEY=','').Trim()

python scripts/push_stories.py `
  --from http://localhost:8011 `
  --to https://radio.example.com `
  --key $localKey `
  --import-key $liveKey `
  --dry-run
```

Review the counts, remove `--dry-run` to apply, then disable the route again:

```bash
# on live
sed -i 's/^LIBRARY_IMPORT_ENABLED=.*/LIBRARY_IMPORT_ENABLED=false/' backend/.env
docker compose up -d backend
```

`--save payload.json` writes the generated snapshot for inspection. The push
is idempotent; re-running it only changes the story fields it carries.

### Pushing reviewed facts to live

`scripts/push_facts.py` is the narrow facts counterpart. It sends only fields
that are **locked locally**, and only for the video IDs you list explicitly;
it never pushes the whole library. It starts each track from the live detail
and overlays the reviewed local facts, so live prose, charts, timestamps and
memberships are preserved. Lock a corrected fact locally first; otherwise the
next pull or enrichment may revert it.

Use the same temporary live import route as above, then dry-run to review the
field-by-field diff:

```powershell
python scripts/push_facts.py `
  --from http://localhost:8011 `
  --to https://radio.example.com `
  --key $localKey `
  --import-key $liveKey `
  --ids-file reviewed-ids.txt `
  --dry-run
```

Remove `--dry-run` to apply, then disable the live import route. `--video-id`
can be repeated instead of `--ids-file`, and `--save` keeps the generated
payload. The tool reports any live-locked field it refuses to overwrite.

### Schema notes

- `trackcache.playlist_id` is nullable. `NULL` means a standalone library track.
- `TrackDetail` is keyed by video ID, so stories, charts, locks and sources
  survive detaching and re-attaching.
- Deleting a genre or playlist in Studio now detaches its tracks; they remain in
  the library with no playlist.

## Production deploy

1. Point your domain's DNS at the VPS.
2. Ensure inbound TCP ports **80** and **443** are open (Caddy needs them for
   Let's Encrypt HTTP-01 / TLS-ALPN challenges).
3. Create `backend/.env` from `backend/.env.example` with real values:
   `YT_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY`;
   `FRONTEND_ORIGIN=https://<your-domain>`; `COOKIE_SECURE=true`.
   Create a root `.env` with `DOMAIN=<your-domain>`.
4. Run `docker compose up -d --build`.
5. Caddy obtains and renews TLS certificates automatically.
6. Visit `https://<your-domain>/studio`, log in, add genres and YouTube
   playlist URLs, then add schedule slots. Adding a playlist fetches and caches
   its tracks immediately; use **Sync all playlists** to refresh later.

If a YouTube fetch fails while adding a playlist, the playlist is still saved
but reports a sync error — fix the URL or API key, then use
**Sync all playlists**.

Data is stored in the `radio_data` Docker volume.

### Updating

```bash
git pull
docker compose up -d --build
```

Database migrations run automatically on backend start (`backend/entrypoint.sh`).

### Logs and status

```bash
docker compose ps
docker compose logs -f backend
docker compose restart backend
```

### Backups

The SQLite database lives in the `radio_data` volume. Example backup to the
current directory:

```bash
docker run --rm \
  -v nakout-radio_radio_data:/data \
  -v "$PWD":/backup \
  alpine tar czf /backup/radio-backup.tgz -C /data .
```

## Notes

- The genre is a single server-driven broadcast: every listener hears the same
  track at the same second. The backend stores a playback anchor and clients sync
  to it, joining mid-song at the live offset.
- Browsers only allow autoplay while muted, so the radio starts playing muted.
  Use the **UNMUTE** button or the volume slider to listen; your volume level is
  remembered between visits.
- Visitors do not pick genres or skip tracks. The time-of-day schedule selects
  the live genre, and the current song finishes before a scheduled switch.
- The listener count is in-memory and the broadcast lock is per-process, so both
  assume a single backend instance.
