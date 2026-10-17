"""Per-track loudness normalization via Deezer loudness metadata.

Audio plays inside YouTube's cross-origin iframe, so loudness cannot be
measured live. Deezer's public API exposes a per-track ``gain`` (a loudness
level: closer to 0 means louder); it is fetched once per video and turned
into a small volume offset applied by the player.

This module must not import ``app.models`` at module level: ``models`` imports
``offset_for_gain`` from here for the ``TrackCache.volume_offset_db``
property. Model imports happen inside functions instead.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.config import get_settings

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.deezer.com/search"
TRACK_URL = "https://api.deezer.com/track/{track_id}"
USER_AGENT = "nakout-radio/1.0 (+https://github.com/xjojoramirez/nakout-radio)"

# Safety guard against confident-but-wrong metadata: never pull a track down
# by more than this, however loud Deezer claims it is.
MAX_ATTENUATION_DB = 15.0

# Politeness pause between two lookups (each lookup is two HTTP requests).
LOOKUP_PAUSE_S = 0.3

# A batch aborts after this many lookups in a row failed (network/API down).
MAX_CONSECUTIVE_ERRORS = 5

# Candidates only match when artist/title keys contain each other with at
# least this length ratio; keeps fuzzy search results from matching a
# different song (e.g. "Glitch - Shiver" must not match "Aaron Glitch -
# Shivers").
MIN_MATCH_RATIO = 0.6

# Plausible Deezer gain values are negative dB-ish loudness levels.
VALID_GAIN_FLOOR = -60.0
VALID_GAIN_CEILING = 0.0


class DeezerLookupError(RuntimeError):
    """The Deezer API returned an error payload or unusable data."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def offset_for_gain(gain_db: float | None) -> float:
    """Volume offset in dB to apply for a track at ``gain_db``.

    ``offset = clamp(target - gain)``: loud tracks (gain near 0) get a
    negative offset (attenuation), quiet ones a positive one (boost), capped
    by settings so no track plays insanely loud or quiet because of doubtful
    metadata. ``None`` means no data, no correction.
    """
    if gain_db is None:
        return 0.0
    settings = get_settings()
    offset = settings.loudness_target_db - gain_db
    return max(-MAX_ATTENUATION_DB, min(settings.loudness_max_boost_db, offset))


_BRACKETED_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_TRAILING_NOISE_RE = re.compile(
    r"\s+(official|lyrics?|audio|video|mv|hd|hq|4k|remaster(?:ed)?)\b.*$",
    re.IGNORECASE,
)
_KEY_RE = re.compile(r"[^a-z0-9]+")


def clean_query(title: str, artist: str) -> tuple[str, str]:
    """Split a YouTube-style title and drop bracketed/noise suffixes.

    ``"Artist - Song (Official Video) [HD]"`` becomes ``("Song", "Artist")``.
    The ``" - "`` split happens *after* bracket removal so titles like
    ``"Hurricane (2015 - Remaster)"`` survive intact. A known artist is only
    overridden when the title carries one.
    """
    text = _BRACKETED_RE.sub(" ", title or "")
    cleaned_artist = (artist or "").strip()
    cleaned_title = text.strip()
    if " - " in text:
        left, right = text.split(" - ", 1)
        if right.strip():
            if left.strip():
                cleaned_artist = left.strip()
            cleaned_title = right.strip()
        else:
            cleaned_title = left.strip() or cleaned_title
    cleaned_title = _TRAILING_NOISE_RE.sub("", cleaned_title).strip(" -|")
    return cleaned_title, cleaned_artist


def _key(text: str) -> str:
    return _KEY_RE.sub("", (text or "").lower())


def _key_ratio(a: str, b: str) -> float:
    """1.0 for equal keys, containment scaled by length, 0 otherwise."""
    ka, kb = _key(a), _key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka in kb or kb in ka:
        return min(len(ka), len(kb)) / max(len(ka), len(kb))
    return 0.0


def pick_candidate(items: list[dict], title: str, artist: str) -> dict | None:
    """Best Deezer search result for ``title``/``artist``, or None.

    Requires containment with ``MIN_MATCH_RATIO`` on the artist (when known)
    and on the title; without an artist the title must match exactly. Exact
    keys win over containment, then longer matches.
    """
    title_query = title.strip()
    artist_query = artist.strip()
    if not title_query:
        return None
    best: dict | None = None
    best_score: tuple[float, float, float] | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate_artist = (item.get("artist") or {}).get("name") or ""
        candidate_title = item.get("title") or ""
        title_ratio = _key_ratio(title_query, candidate_title)
        if title_ratio < MIN_MATCH_RATIO:
            continue
        artist_ratio = 0.0
        if artist_query:
            artist_ratio = _key_ratio(artist_query, candidate_artist)
            if artist_ratio < MIN_MATCH_RATIO:
                continue
        elif title_ratio < 1.0:
            continue
        score = (
            1.0 if artist_ratio == 1.0 else 0.0,
            1.0 if title_ratio == 1.0 else 0.0,
            artist_ratio + title_ratio,
        )
        if best_score is None or score > best_score:
            best_score = score
            best = item
    return best


def _get_json(client: httpx.Client, url: str, **params: object) -> dict:
    resp = client.get(url, params=params or None)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as exc:
        raise DeezerLookupError("malformed Deezer response") from exc
    if not isinstance(data, dict):
        raise DeezerLookupError("unexpected Deezer response")
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else error
        raise DeezerLookupError(f"Deezer error: {message}")
    return data


def lookup_gain(title: str, artist: str, client: httpx.Client) -> float | None:
    """Resolve a track's Deezer gain, or None when no confident match.

    Raises ``DeezerLookupError`` / ``httpx.HTTPError`` on failures the caller
    should retry later.
    """
    clean_title, clean_artist = clean_query(title, artist)
    if not clean_title:
        return None
    search = _get_json(
        client, SEARCH_URL, q=f"{clean_artist} {clean_title}".strip(), limit=5
    )
    candidate = pick_candidate(search.get("data") or [], clean_title, clean_artist)
    if candidate is None or candidate.get("id") is None:
        return None
    detail = _get_json(client, TRACK_URL.format(track_id=candidate["id"]))
    gain = detail.get("gain")
    if isinstance(gain, bool) or not isinstance(gain, (int, float)):
        return None
    gain = float(gain)
    if not VALID_GAIN_FLOOR < gain < VALID_GAIN_CEILING:
        return None
    return gain


def enrich_pending(
    session_factory: Callable[[], Session],
    client: httpx.Client,
    *,
    limit: int = 100,
    pause_seconds: float = LOOKUP_PAUSE_S,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Resolve loudness for up to ``limit`` unchecked video ids.

    Returns how many ids were resolved (hit or definitive miss). Every row
    sharing a video id is updated; lookups that errored stay unchecked for a
    later run, and the batch aborts after ``MAX_CONSECUTIVE_ERRORS`` failures
    in a row.
    """
    from app.models import TrackCache  # local import: models imports this module

    with session_factory() as session:
        rows = session.exec(
            select(TrackCache)
            .where(TrackCache.gain_checked_at.is_(None))
            .order_by(TrackCache.id)
        ).all()

    pending: dict[str, tuple[str, str]] = {}
    for row in rows:
        pending.setdefault(row.youtube_video_id, (row.title, row.artist))
        if len(pending) >= limit:
            break

    processed = 0
    consecutive_errors = 0
    for video_id, (title, artist) in pending.items():
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            break
        try:
            gain = lookup_gain(title, artist, client)
        except (DeezerLookupError, httpx.HTTPError) as exc:
            consecutive_errors += 1
            logger.warning("loudness lookup failed for %s: %s", video_id, exc)
            continue
        consecutive_errors = 0
        with session_factory() as session:
            for row in session.exec(
                select(TrackCache).where(TrackCache.youtube_video_id == video_id)
            ).all():
                row.gain_db = gain
                row.gain_checked_at = _utcnow()
                session.add(row)
            session.commit()
        processed += 1
        if pause_seconds:
            sleep(pause_seconds)
    return processed


_start_lock = threading.Lock()
_backfill_running = threading.Event()


def ensure_backfill() -> bool:
    """Start the single-flight background loudness backfill.

    Returns True when a worker was started; False when disabled or already
    running. Best-effort: failures abort the run and are retried by the next
    trigger (startup or playlist sync).
    """
    if not get_settings().loudness_lookup_enabled:
        return False
    with _start_lock:
        if _backfill_running.is_set():
            return False
        _backfill_running.set()
    threading.Thread(
        target=_backfill_worker, name="loudness-backfill", daemon=True
    ).start()
    return True


def _backfill_worker() -> None:
    from functools import partial

    from app.db import engine

    try:
        factory = partial(Session, engine)
        with httpx.Client(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            while enrich_pending(factory, client) > 0:
                pass
    except Exception:  # noqa: BLE001 - background best-effort
        logger.exception("loudness backfill aborted")
    finally:
        _backfill_running.clear()
