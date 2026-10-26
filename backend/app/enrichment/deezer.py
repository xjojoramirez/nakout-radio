"""Deezer metadata provider (keyless public API).

Deezer is the primary source: one search plus the track and its album gives
the album title, release date, label, genres, credits, BPM, ISRC and cover.
"""

import httpx

from app.enrichment.base import (
    ProviderData,
    ProviderError,
    is_empty,
    year_from_date,
)
from app.matching import clean_query, match_confidence, pick_candidate

SEARCH_URL = "https://api.deezer.com/search"
TRACK_URL = "https://api.deezer.com/track/{track_id}"
ALBUM_URL = "https://api.deezer.com/album/{album_id}"
PROVIDER = "deezer"


def _get_json(
    client: httpx.Client, url: str, **params: object
) -> dict:
    resp = client.get(url, params=params or None)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError("malformed Deezer response") from exc
    if not isinstance(data, dict):
        raise ProviderError("unexpected Deezer response")
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else error
        raise ProviderError(f"Deezer error: {message}")
    return data


def _credits(contributors: list[dict]) -> list[dict]:
    credits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for contributor in contributors or []:
        if not isinstance(contributor, dict):
            continue
        name = (contributor.get("name") or "").strip()
        role = (contributor.get("role") or "").strip()
        if not name or not role or (role, name) in seen:
            continue
        seen.add((role, name))
        credits.append({"role": role, "name": name})
    return credits


def lookup_deezer(
    title: str, artist: str, client: httpx.Client
) -> ProviderData | None:
    """Best-effort Deezer metadata for a YouTube title/artist pair."""
    clean_title, clean_artist = clean_query(title, artist)
    if not clean_title:
        return None

    search = _get_json(
        client,
        SEARCH_URL,
        q=f"{clean_artist} {clean_title}".strip(),
        limit=5,
    )
    candidate = pick_candidate(
        search.get("data") or [], clean_title, clean_artist
    )
    if candidate is None or candidate.get("id") is None:
        return None

    track = _get_json(
        client, TRACK_URL.format(track_id=candidate["id"])
    )
    album_id = (track.get("album") or {}).get("id")
    album: dict = {}
    if album_id:
        try:
            album = _get_json(
                client, ALBUM_URL.format(album_id=album_id)
            )
        except (httpx.HTTPError, ProviderError):
            # The album enriches label/genres; the track facts still stand.
            album = {}

    track_album = track.get("album") or {}
    release_date = (
        album.get("release_date")
        or track_album.get("release_date")
        or track.get("release_date")
        or ""
    ).strip()

    fields = {
        "album": track_album.get("title"),
        "album_artist": (album.get("artist") or {}).get("name")
        or (track.get("artist") or {}).get("name"),
        "release_date": release_date,
        "release_year": year_from_date(release_date),
        "label": album.get("label"),
        "genres": sorted(
            {
                genre.get("name")
                for genre in (album.get("genres") or {}).get("data") or []
                if isinstance(genre, dict) and genre.get("name")
            }
        ),
        "isrc": track.get("isrc"),
        "bpm": (
            round(track.get("bpm"))
            if isinstance(track.get("bpm"), (int, float))
            and track.get("bpm") > 0
            else None
        ),
        "track_number": track.get("track_position") or None,
        "disc_number": track.get("disk_number") or None,
        "cover_url": (
            album.get("cover_xl")
            or track_album.get("cover_xl")
            or track_album.get("cover_big")
            or track_album.get("cover_medium")
        ),
        "credits": _credits(track.get("contributors") or []),
    }
    fields = {
        name: value for name, value in fields.items() if not is_empty(value)
    }

    track_id = track.get("id") or candidate.get("id")
    return ProviderData(
        provider=PROVIDER,
        url=f"https://www.deezer.com/track/{track_id}",
        confidence=match_confidence(
            clean_title,
            clean_artist,
            candidate.get("title") or "",
            (candidate.get("artist") or {}).get("name") or "",
        ),
        fields=fields,
    )
