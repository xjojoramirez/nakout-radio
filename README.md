# Nakout Radio

A personal internet-radio website streaming the owner's YouTube playlists as a
single always-on broadcast, with a time-of-day scheduled genre, a live
listener count, and an admin panel.

## Architecture

- `backend/` — FastAPI + SQLite. Reads playlist tracks via the YouTube Data
  API v3 and caches them. Serves genres, schedule, admin, and a listener
  websocket.
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
| `COOKIE_SECURE` | `true` in production (HTTPS); `false` for local http dev |

Root (`.env`):

| Variable | Purpose |
| --- | --- |
| `DOMAIN` | Public domain for Caddy/TLS |

> Track caching is refreshed when a playlist is added (or re-added) and when you
> click **Sync all playlists** in the admin panel. There is no automatic timer
> yet, so `CACHE_TTL_MINUTES` is currently unused.

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
