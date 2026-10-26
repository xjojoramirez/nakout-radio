"""MusicBrainz metadata provider (keyless, 1 request/second).

Used to fill the gaps Deezer leaves behind: canonical release dates, labels,
country and ISRCs. A recording's search result can point at arbitrary
compilations; the recording lookup gives all releases and release groups, so
the earliest (usually original) release is chosen instead.

MusicBrainz asks clients to identify themselves and to stay under one request
per second.
"""

import time
from collections.abc import Callable

import httpx

from app.enrichment.base import (
    ProviderData,
    ProviderError,
    USER_AGENT,
    is_empty,
    year_from_date,
)
from app.matching import clean_query, match_confidence, pick_candidate

SEARCH_URL = "https://musicbrainz.org/ws/2/recording"
RECORDING_URL = "https://musicbrainz.org/ws/2/recording/{recording_id}"
RELEASE_URL = "https://musicbrainz.org/ws/2/release/{release_id}"
PROVIDER = "musicbrainz"
PAUSE_S = 1.05


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _get_json(
    client: httpx.Client, url: str, **params: object
) -> dict:
    resp = client.get(
        url,
        params=params or None,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError("malformed MusicBrainz response") from exc
    if not isinstance(data, dict):
        raise ProviderError("unexpected MusicBrainz response")
    return data


def _credit_name(recording: dict) -> str:
    credits = recording.get("artist-credit") or []
    if credits and isinstance(credits[0], dict):
        return credits[0].get("name") or ""
    return ""


def _label_name(release: dict) -> str | None:
    info = release.get("label-info") or []
    if not info or not isinstance(info[0], dict):
        return None
    name = ((info[0].get("label") or {}).get("name") or "").strip()
    return name or None


def _release_date(release: dict) -> str:
    group = release.get("release-group") or {}
    return (group.get("first-release-date") or release.get("date") or "").strip()


def _choose_release(releases: list[dict]) -> dict:
    """Earliest official release (the original album, not a later compilation)."""
    dated = [release for release in releases if _release_date(release)]
    candidates = dated or releases
    if not candidates:
        return {}
    return min(
        candidates,
        key=lambda release: (
            _release_date(release),
            0 if release.get("status") == "Official" else 1,
        ),
    )


def lookup_musicbrainz(
    title: str,
    artist: str,
    client: httpx.Client,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> ProviderData | None:
    clean_title, clean_artist = clean_query(title, artist)
    if not clean_title:
        return None

    query = f'recording:"{_escape(clean_title)}"'
    if clean_artist:
        query += f' AND artist:"{_escape(clean_artist)}"'
    search = _get_json(
        client, SEARCH_URL, query=query, fmt="json", limit=5
    )

    recordings = [
        recording
        for recording in search.get("recordings") or []
        if isinstance(recording, dict)
    ]
    candidates = [
        {
            "title": recording.get("title") or "",
            "artist": {"name": _credit_name(recording)},
            "recording": recording,
        }
        for recording in recordings
    ]
    candidate = pick_candidate(candidates, clean_title, clean_artist)
    if candidate is None:
        return None

    recording = candidate["recording"]
    recording_id = recording.get("id")
    detailed = recording
    detail_ok = False
    if recording_id:
        # The search result's releases are incomplete and often compilations.
        sleep(PAUSE_S)
        try:
            detailed = _get_json(
                client,
                RECORDING_URL.format(recording_id=recording_id),
                inc="releases release-groups isrcs",
                fmt="json",
            )
            detail_ok = True
        except (httpx.HTTPError, ProviderError):
            detailed = recording

    releases = [
        release
        for release in detailed.get("releases") or []
        if isinstance(release, dict)
    ]
    release = _choose_release(releases)
    group = release.get("release-group") or {}

    release_date = (
        group.get("first-release-date")
        or release.get("date")
        or detailed.get("first-release-date")
        or ""
    ).strip()
    album = group.get("title") or release.get("title")
    label = _label_name(release)
    country = (release.get("country") or "").strip()

    release_id = release.get("id")
    if release_id and not label:
        sleep(PAUSE_S)
        try:
            release_detail = _get_json(
                client,
                RELEASE_URL.format(release_id=release_id),
                inc="labels",
                fmt="json",
            )
        except (httpx.HTTPError, ProviderError):
            release_detail = {}
        label = label or _label_name(release_detail)
        country = country or (release_detail.get("country") or "").strip()
        release_date = release_date or (release_detail.get("date") or "").strip()

    isrcs = [
        isrc
        for isrc in (detailed.get("isrcs") or recording.get("isrcs") or [])
        if isinstance(isrc, str) and isrc.strip()
    ]
    fields = {
        "album": album,
        "release_date": release_date or None,
        "release_year": year_from_date(release_date),
        "label": label,
        "country": country or None,
        "isrc": isrcs[0] if isrcs else None,
    }
    fields = {
        name: value for name, value in fields.items() if not is_empty(value)
    }

    return ProviderData(
        provider=PROVIDER,
        url=f"https://musicbrainz.org/recording/{recording_id}",
        confidence=(
            match_confidence(
                clean_title,
                clean_artist,
                candidate["title"],
                candidate["artist"]["name"],
            )
            if detail_ok
            else "fuzzy"
        ),
        fields=fields,
    )
