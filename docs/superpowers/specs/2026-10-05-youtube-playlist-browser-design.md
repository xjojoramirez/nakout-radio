# Nakout Radio — Browse Channel Playlists: Design Specification

Date: 2026-10-05
Status: Approved for planning

## 1. Overview

The admin panel currently accepts a pasted YouTube playlist URL and immediately
syncs it. The owner cannot see which playlists exist on their channel, so adding
one requires leaving the app to copy a link.

This feature adds a browsable list of the saved channel's **public** playlists
to the admin page. The owner saves a channel once, sees its public playlists,
and adds one to a station directly from the list. Manual URL entry is kept for
playlists that are not public or are saved from other channels.

## 2. Goals

- Let the owner save one YouTube channel (ID, `@handle`, or channel URL) in the
  admin UI.
- List that channel's public playlists with title, track count, and thumbnail.
- Add any listed playlist to a chosen station in one action, reusing the
  existing sync pipeline.
- Mark playlists already added to the app.
- Keep the existing manual URL entry for private/unlisted/saved playlists.

## 3. Non-Goals

- No Google/OAuth sign-in. Only public, channel-owned playlists are listed.
- No listing of playlists the user *saved* from other channels (OAuth-only).
- No multiple saved channels.
- No deleting or editing playlists from this list.
- No change to schedule editing or the station/slot management gaps discussed
  separately.

## 4. Confirmed Decisions

| Area | Decision |
| --- | --- |
| Auth | None; uses the existing `YT_API_KEY` |
| Channel source | One channel saved in the database, editable in the UI |
| Privacy | Public, channel-owned playlists only; manual paste retained for the rest |
| Add action | Choose station inline, add immediately |
| Storage | Generic `Setting` key/value table |
| YouTube calls | Isolated in `app/youtube.py`, as with existing code |

## 5. Architecture

No new services. Changes are confined to the existing FastAPI backend, the
SQLite schema, and the React admin page.

```
backend/
├─ app/
│  ├─ models.py            # + Setting table
│  ├─ youtube.py           # + resolve_channel_id, fetch_channel_playlists
│  ├─ schemas.py           # + channel/playlist response models
│  └─ routers/admin.py     # + three YouTube endpoints
└─ alembic/versions/       # + migration creating `setting`

frontend/src/
├─ types.ts                # + ChannelSource, ChannelPlaylist
├─ api/client.ts           # + getChannelSource, setChannelSource, listChannelPlaylists
└─ pages/AdminPage.tsx     # + "Browse YouTube playlists" section
```

## 6. Data Model

New table `Setting`:

- `key`: primary key, string.
- `value`: string.

Keys used by this feature:

- `youtube_channel_id` — the resolved `UC…` channel ID.
- `youtube_channel_title` — the channel display title, for display only.

Rationale: a generic key/value table avoids a dedicated table per single-value
setting and keeps future settings cheap. No other table changes.

## 7. Backend

### `app/youtube.py`

- `@dataclass PlaylistData`: `youtube_playlist_id`, `title`, `item_count`,
  `thumbnail_url`.
- `resolve_channel_id(value, api_key, client) -> tuple[str, str]`:
  - Accepts a raw channel ID (`UC…`), `@handle`, `youtube.com/@handle`,
    `youtube.com/channel/<id>`, or `youtube.com/user/<name>`.
  - Calls `channels.list?part=snippet` with `id`, `forHandle`, or
    `forUsername` as appropriate.
  - Returns `(channel_id, title)`.
  - Raises `ValueError` when the input cannot be parsed or resolves to nothing.
- `fetch_channel_playlists(channel_id, api_key, client) -> list[PlaylistData]`:
  - Paginates `playlists.list?part=snippet,contentDetails&channelId=…`
    (`maxResults=50`, following `nextPageToken`).
  - Reads `id`, `snippet.title`, `snippet.thumbnails`, and
    `contentDetails.itemCount`.

### `app/schemas.py`

- `ChannelIn`: `channel: str`.
- `ChannelOut`: `channel_id: str | None`, `title: str | None`.
- `ChannelPlaylistOut`: `youtube_playlist_id: str`, `title: str`,
  `item_count: int`, `thumbnail_url: str`, `already_added: bool`.

### `app/routers/admin.py` (all `dependencies=[Depends(require_admin)]`)

- `GET /api/admin/youtube/channel` → `ChannelOut`. Returns null fields when no
  channel is saved.
- `PUT /api/admin/youtube/channel` body `ChannelIn` → `ChannelOut`. Resolves the
  channel, upserts both `Setting` rows, returns the resolved ID and title.
- `GET /api/admin/youtube/playlists` → `list[ChannelPlaylistOut]`. Uses the
  saved channel; returns `[]` if none saved. `already_added` is computed by
  loading the set of `Playlist.youtube_playlist_id` values and checking
  membership.

Adding a playlist reuses the existing `POST /api/admin/playlists` endpoint,
which parses the ID, syncs tracks, and caches them.

## 8. Frontend

- `types.ts`: `ChannelSource { channel_id: string | null; title: string | null }`
  and `ChannelPlaylist { youtube_playlist_id; title; item_count;
  thumbnail_url; already_added }`.
- `api/client.ts`: `getChannelSource()`, `setChannelSource(channel)`,
  `listChannelPlaylists()`.
- `AdminPage.tsx`, a new "Browse YouTube playlists" section below "Playlist":
  - When no channel is saved: a text input (placeholder for `@handle` or channel
    URL) and a **Save channel** button.
  - When a channel is saved: the channel title, a **Change** button (returns to
    the input), and a **Refresh** button.
  - The list shows each playlist's thumbnail, title, and track count, plus a
    station dropdown and an **Add** button. Rows with `already_added` show an
    "Added" badge and a disabled button.
  - On **Add**: call `createPlaylist(stationId, "https://www.youtube.com/playlist?list=<id>", "")`,
    surface the existing notice/error text, then refresh the list so the row
    shows as added.

## 9. Data Flow

1. **Save channel.** Owner submits a channel reference → backend resolves it via
   `channels.list` → both settings rows are upserted → resolved title is
   returned and shown.
2. **Browse.** Admin opens the section → `GET …/playlists` reads the saved
   channel → fetches and paginates public playlists → annotates `already_added`
   from local `Playlist` rows.
3. **Add.** Owner picks a station and clicks **Add** → the existing create
   endpoint parses the ID, lint-syncs the track list, and caches it.

## 10. Error Handling

- **Unparseable/unresolvable channel:** `400` with a specific message; the UI
  shows it inline above the input.
- **YouTube HTTP failure** (`httpx.HTTPError`): `502` with the upstream message;
  the UI shows an error and keeps the **Refresh** button available.
- **No saved channel:** `GET …/channel` returns nulls and `GET …/playlists`
  returns `[]`; the UI shows the setup form.
- **Playlist with zero items:** still listed; adding it simply caches nothing
  and reports "Playlist synced (0 tracks)."
- **Existing behaviors unchanged:** manual URL entry, sync errors, and auth
  (401) continue to work as before.

## 11. Testing Strategy

- **Backend (`pytest`, FastAPI `TestClient`):**
  - `resolve_channel_id`: raw ID, `@handle`, `/channel/`, `/user/` inputs with a
    mocked HTTP client; `ValueError` on garbage.
  - `fetch_channel_playlists`: pagination across two pages; correct field
    mapping.
  - Admin endpoints: auth required, channel persistence across requests,
    `already_added` computed correctly after adding a playlist, 404/502 paths.
  - YouTube HTTP is mocked at the `youtube.py` boundary, matching existing tests.
- **Frontend (`Vitest` + Testing Library):**
  - `api/client` calls hit the expected methods/paths.
  - `AdminPage` DOM test: renders the playlist list, clicking **Add** calls
    `createPlaylist`, and already-added rows render a disabled button/badge.

## 12. Migration

One Alembic migration creates the `setting` table. It runs automatically via
`backend/entrypoint.sh` on container start.

## 13. Configuration

No new environment variables. The feature uses the existing `YT_API_KEY`. The
saved channel lives in the database, not in configuration.
