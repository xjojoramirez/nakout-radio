# Nakout Radio — Design Specification

Date: 2026-10-05
Status: Approved for planning

## 1. Overview

Nakout Radio is a personal internet radio website built around the owner's
YouTube Music playlists. Visitors open the site and hear continuous music that
streams from one or more YouTube playlists. The site presents an always-on
"main station" whose genre changes according to a fixed time-of-day schedule,
plus several manually selectable "mood stations".

The product should feel like a vintage physical radio: a dial, a warm cabinet
aesthetic, and animated VU meters.

## 2. Goals

- Stream the owner's YouTube playlists continuously to any visitor in a browser.
- Provide an always-on main station with a server-driven time-of-day genre schedule.
- Provide multiple mood stations the visitor can switch between.
- Show accurate "Now Playing" information (title, artist, artwork).
- Show a live listener count.
- Give the owner an admin panel to manage stations, playlists, and the schedule
  without touching code.

## 3. Non-Goals (v1)

- No self-hosted or downloaded audio. All playback goes through YouTube.

  > Rationale: self-hosting YouTube audio violates YouTube's Terms of Service.

- No user accounts for visitors.
- No track request form or user-submitted songs.
- No multi-instance / horizontally scaled backend.
- No mobile native app.
- No paid music-service integration.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Playback | YouTube IFrame Player API, driven by our own code |
| Track data | YouTube Data API v3 (hybrid: official data + official player) |
| Backend | Python FastAPI |
| Frontend | React + Vite + TypeScript (web, not React Native) |
| Database | SQLite (file on a Docker volume), via SQLModel + Alembic |
| Admin auth | Single password from env, exchanged for a signed session cookie |
| Schedule clock | Fixed station timezone (`STATION_TZ`), same genre for everyone |
| Listener count | In-memory WebSocket connection count |
| Aesthetic | Vintage / retro radio |
| Packaging | Docker Compose with separate `caddy`, `frontend`, `backend` services |
| Hosting | Owner's own VPS |

### Why the hybrid approach

YouTube Music provides no official API for embedding an editable YT Music
playlist with custom queue control. The chosen approach separates concerns:

- The **Data API v3** is used only to read playlist track lists (video IDs and
  metadata), which the backend fetches and caches. This enables custom queues,
  shuffle, accurate Now Playing, and the time-of-day schedule.
- The **IFrame Player API** is used only for playback, so all media stays
  YouTube-hosted and legal.

Alternatives rejected: pure playlist embeds (no track awareness, cannot build a
schedule or queue), scraping YouTube Music (fragile, against ToS), self-hosted
audio (illegal), React Native (wrong target for a website).

## 5. Architecture

Two independently deployable applications plus a database file and a reverse
proxy, packaged as Docker Compose services.

```
nakout-radio/
├─ backend/                     # FastAPI
│  ├─ app/
│  │  ├─ main.py                # app factory, middleware, router mounts
│  │  ├─ config.py              # env settings
│  │  ├─ db.py                  # SQLModel engine + session
│  │  ├─ models.py              # Station, Playlist, TrackCache, ScheduleSlot
│  │  ├─ schemas.py             # request/response models
│  │  ├─ youtube.py             # Data API client + cache logic
│  │  ├─ scheduler.py           # time-of-day resolution
│  │  ├─ auth.py                # password -> signed session cookie
│  │  └─ routers/
│  │     ├─ stations.py         # GET /stations, POST /api/queue/advance
│  │     ├─ schedule.py         # GET /schedule/now
│  │     ├─ admin.py            # login + CRUD
│  │     └─ ws.py               # /ws/listeners
│  ├─ alembic/                  # migrations
│  ├─ tests/
│  ├─ requirements.txt
│  ├─ Dockerfile
│  └─ .env.example
├─ frontend/                    # React + Vite + TypeScript
│  ├─ src/
│  │  ├─ api/client.ts
│  │  ├─ hooks/
│  │  │  ├─ useYouTubePlayer.ts
│  │  │  ├─ useListenerCount.ts
│  │  │  └─ useSchedule.ts
│  │  ├─ components/
│  │  │  ├─ RadioPlayer.tsx
│  │  │  ├─ NowPlaying.tsx
│  │  │  ├─ StationDial.tsx
│  │  │  └─ VUMeter.tsx
│  │  └─ pages/
│  │     ├─ RadioPage.tsx
│  │     └─ AdminPage.tsx
│  ├─ nginx.conf
│  ├─ Dockerfile
│  └─ .env.example
├─ Caddyfile
├─ docker-compose.yml
└─ README.md
```

### Compose services

| Service | Image | Responsibility | Notes |
| --- | --- | --- | --- |
| `caddy` | `caddy:2-alpine` | TLS termination + routing | `/` → frontend, `/api` and `/ws` → backend |
| `frontend` | built (node → `nginx:alpine`) | Serve static React build | Internal only, exposed via caddy |
| `backend` | built (python slim) | FastAPI + uvicorn | SQLite on named volume `radio_data` |

Only `caddy` publishes ports (80/443). `frontend` and `backend` bind to the
internal Docker network. Because everything is presented on one origin by
Caddy, CORS is not required for normal operation.

## 6. Data Model

- **Station** — `id`, `name`, `slug`, `is_default`, `sort_order`.
- **Playlist** — `id`, `station_id`, `youtube_playlist_id`, `label`.
- **TrackCache** — `id`, `playlist_id`, `youtube_video_id`, `title`, `artist`,
  `thumbnail_url`, `duration_seconds`, `position`, `fetched_at`.
- **ScheduleSlot** — `id`, `station_id`, `days_of_week`, `start_time`,
  `end_time`.

Representation details:

- `days_of_week` is a JSON array of integers, `0` = Monday through `6` = Sunday.
- `start_time` and `end_time` are stored as local wall-clock times in
  `STATION_TZ`.
- If `end_time` is less than or equal to `start_time`, the slot crosses
  midnight and applies into the following day.
- Track list order is derived from `position`, matching YouTube playlist order.
  `fetched_at` drives cache freshness.

## 7. Data Flow

1. **Admin setup.** Owner adds a playlist URL or ID in the admin panel. The
   backend parses the YouTube playlist ID, calls `playlistItems.list`, and
   stores ordered tracks in `TrackCache`.
2. **Visitor load.** Frontend requests `GET /stations` and
   `GET /schedule/now`. The resolved station returns a single current track plus
   an opaque signed cursor.
3. **Playback.** The frontend plays the current track via the YouTube IFrame
   Player and requests next/previous/random from `POST /api/queue/advance`,
   which returns the next single track and a new cursor. The client never
   receives the full track list.
4. **Live count.** The frontend opens `/ws/listeners`; the backend adds the
   connection to an in-memory set and broadcasts the new count. Disconnects
   remove the connection.
5. **Refresh.** A periodic backend task re-fetches playlists whose cache is
   stale, so newly added songs appear without code changes.

## 8. Playback and Autoplay Policy

Browsers block autoplay with sound on page load. The radio therefore begins
muted-with-visual-state and presents a prominent vintage **"TUNE IN"** control.
The first user interaction starts audio and unmutes. After that first gesture,
playback is continuous and transitions between tracks without further clicks.

## 9. Schedule

The main station's genre follows a time-of-day schedule evaluated server-side
in a fixed `STATION_TZ`, so every listener hears the same genre at the same
moment, like a real broadcast. `GET /schedule/now` returns the active station.
When multiple slots could match, the most specific / latest-starting slot wins.
When no slot matches the current time, the station marked `is_default` is
returned as the fallback. The frontend re-checks at slot boundaries and
smoothly switches stations. Mood stations act as manual overrides through the
station dial.

## 10. Admin and Authentication

- A single admin password is stored in an environment variable.
- `POST /admin/login` verifies the password and issues a signed, `HttpOnly`
  session cookie (JWT signed with `SECRET_KEY`).
- Admin CRUD endpoints cover stations, playlists, and schedule slots. All admin
  routes require a valid session.
- No passwords are stored in the database.

## 11. Live Listener Count

Implemented with a WebSocket endpoint holding an in-memory set of active
connections. This is correct for a single backend container, which is the v1
deployment. If the backend is ever scaled to multiple instances or workers,
this must move to a shared store (e.g. Redis pub/sub). This is documented as a
future upgrade, not part of v1.

## 12. Error Handling

- **YouTube quota or API failure:** serve stale cache if present; otherwise
  return a "station off air" state to the UI.
- **Unavailable/removed video:** the IFrame player's `onError` handler skips to
  the next track.
- **WebSocket disconnect:** connection is removed from the listener set in a
  `finally` block.
- **Expired/absent admin session:** admin API returns 401 and the UI redirects
  to login.
- **Missing config (API key, admin password, secret):** backend fails fast at
  startup with a clear message.

## 13. Testing Strategy

- **Backend:** `pytest` with FastAPI `TestClient`. The YouTube client is mocked
  at the `youtube.py` boundary. Tests cover schedule boundary math (start/end
  edges, day-of-week matching, timezone conversion), authentication
  (login success/failure, session validation), playlist-ID parsing, and cache
  TTL behavior.
- **Frontend:** `Vitest` + React Testing Library for hooks and formatting
  logic (schedule countdown, track formatting). Real playback is verified
  manually in a browser, because the YouTube player cannot run headless.

## 14. Configuration

Environment variables (`.env` on the VPS, never committed):

| Variable | Purpose |
| --- | --- |
| `YT_API_KEY` | YouTube Data API v3 key |
| `ADMIN_PASSWORD` | Admin login password |
| `SECRET_KEY` | Signing key for session cookies |
| `STATION_TZ` | Fixed schedule timezone (e.g. `Asia/Manila`) |
| `DATABASE_URL` | SQLite path on the volume |
| `FRONTEND_ORIGIN` | Allowed origin if CORS is ever needed |
| `CACHE_TTL_MINUTES` | Track cache freshness window |

## 15. Deployment

- `docker compose up -d` on the VPS brings up `caddy`, `frontend`, `backend`.
- Caddy obtains and renews Let's Encrypt certificates automatically for the
  configured domain.
- SQLite data lives on the named volume `radio_data`, which is included in
  backups.
- Alembic migrations run as a release step before the backend starts.
- Secrets are provided via `.env` on the server.

## 16. Build-Time Inputs Required

These are needed during implementation but are not architectural blockers:

- Domain name for Caddy / TLS.
- Public YouTube playlist URLs or IDs.
- `STATION_TZ` value.
- The genre-per-time-window schedule definition.

## 17. Future Enhancements (post-v1)

- Queue and history views.
- Track request form.
- Redis-backed listener count and multi-instance backend.
- Migration from SQLite to Postgres.
- Additional stations and richer schedule rules (per-day overrides, holidays).
