import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

_API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
_PLAYLISTS_URL = "https://www.googleapis.com/youtube/v3/playlists"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _channel_lookup_param(value: str) -> dict[str, str]:
    value = (value or "").strip()
    if not value:
        raise ValueError("empty channel reference")
    if value.startswith("UC"):
        return {"id": value}
    if value.startswith("@"):
        return {"forHandle": value}
    lowered = value.lower()
    if not (
        "://" in value
        or lowered.startswith("youtube.com")
        or lowered.startswith("www.youtube.com")
        or lowered.startswith("music.youtube.com")
    ):
        return {"id": value}
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.hostname or ""
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        raise ValueError("not a YouTube channel URL")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("no channel in URL")
    if parts[0].startswith("@"):
        return {"forHandle": parts[0]}
    if len(parts) >= 2 and parts[0] == "channel":
        return {"id": parts[1]}
    if len(parts) >= 2 and parts[0] == "user":
        return {"forUsername": parts[1]}
    raise ValueError("unsupported channel URL")


def resolve_channel_id(
    value: str, api_key: str, client: httpx.Client
) -> tuple[str, str]:
    params = {"part": "snippet", "key": api_key, **_channel_lookup_param(value)}
    resp = client.get(_CHANNELS_URL, params=params)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        raise ValueError("channel not found")
    item = items[0]
    channel_id = item.get("id")
    if not channel_id:
        raise ValueError("channel not found")
    snippet = item.get("snippet") or {}
    return channel_id, snippet.get("title") or ""


@dataclass
class TrackData:
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str
    position: int
    duration_seconds: int = 0


@dataclass
class PlaylistData:
    youtube_playlist_id: str
    title: str
    item_count: int
    thumbnail_url: str


def _parse_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


_TOPIC_SUFFIX_RE = re.compile(r"\s*-\s*Topic\s*$", re.IGNORECASE)


def _clean_artist(name: str) -> str:
    return _TOPIC_SUFFIX_RE.sub("", name or "").strip()


def _pick_thumbnail(thumbs: dict | None) -> str:
    thumbs = thumbs or {}
    for key in ("high", "medium", "default"):
        candidate = (thumbs.get(key) or {}).get("url")
        if candidate:
            return candidate
    return ""


_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def _parse_iso_duration(value: str) -> int:
    match = _DURATION_RE.match(value or "")
    if not match:
        return 0
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def fetch_video_durations(
    video_ids: list[str], api_key: str, client: httpx.Client
) -> dict[str, int]:
    durations: dict[str, int] = {}
    unique = list(dict.fromkeys(video_ids))
    for start in range(0, len(unique), 50):
        batch = unique[start : start + 50]
        params = {
            "part": "contentDetails",
            "id": ",".join(batch),
            "key": api_key,
        }
        resp = client.get(_VIDEOS_URL, params=params)
        resp.raise_for_status()
        for item in resp.json().get("items") or []:
            video_id = item.get("id")
            if not video_id:
                continue
            content = item.get("contentDetails") or {}
            durations[video_id] = _parse_iso_duration(content.get("duration", ""))
    return durations


def fetch_channel_playlists(
    channel_id: str, api_key: str, client: httpx.Client
) -> list[PlaylistData]:
    playlists: list[PlaylistData] = []
    page_token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        params = {
            "part": "snippet,contentDetails",
            "channelId": channel_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = client.get(_PLAYLISTS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        for item in (data.get("items") or []):
            playlist_id = item.get("id")
            if not playlist_id:
                continue
            snippet = item.get("snippet") or {}
            content = item.get("contentDetails") or {}
            playlists.append(
                PlaylistData(
                    youtube_playlist_id=playlist_id,
                    title=snippet.get("title") or "Untitled",
                    item_count=_parse_int(content.get("itemCount")),
                    thumbnail_url=_pick_thumbnail(snippet.get("thumbnails")),
                )
            )
        page_token = data.get("nextPageToken")
        if not page_token or page_token in seen_tokens:
            break
        seen_tokens.add(page_token)
    return playlists


def parse_playlist_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("empty playlist reference")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.hostname or ""
    is_youtube = host == "youtube.com" or host.endswith(".youtube.com")
    is_short = host == "youtu.be" or host.endswith(".youtu.be")
    if is_youtube or is_short:
        query = parse_qs(parsed.query)
        list_values = query.get("list")
        if not list_values or not list_values[0]:
            raise ValueError("no list= parameter in URL")
        return list_values[0]
    return value


def fetch_playlist_items(
    playlist_id: str, api_key: str, client: httpx.Client
) -> list[TrackData]:
    tracks: list[TrackData] = []
    page_token: str | None = None
    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = client.get(_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        for item in (data.get("items") or []):
            snippet = item.get("snippet") or {}
            video_id = (snippet.get("resourceId") or {}).get("videoId")
            if not video_id:
                continue
            thumb = _pick_thumbnail(snippet.get("thumbnails"))
            tracks.append(
                TrackData(
                    youtube_video_id=video_id,
                    title=snippet.get("title") or "Unknown",
                    artist=_clean_artist(
                        snippet.get("videoOwnerChannelTitle", "")
                        or snippet.get("channelTitle", "")
                    ),
                    thumbnail_url=thumb,
                    position=snippet.get("position") or len(tracks),
                )
            )
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return tracks
