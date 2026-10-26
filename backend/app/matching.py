"""Artist/title matching shared by the metadata and loudness lookups.

YouTube titles carry noise ("Official Video", "(Remaster)") while catalogue
providers use the canonical song title. Matching is deliberately conservative:
a confident-looking but wrong match is worse than no match at all.
"""

import re
from typing import Literal

# Candidates only match when artist/title keys contain each other with at
# least this length ratio; keeps fuzzy search results from matching a
# different song (e.g. "Glitch - Shiver" must not match "Aaron Glitch -
# Shivers").
MIN_MATCH_RATIO = 0.6

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


def normalize_key(text: str) -> str:
    """Lowercase letters/digits only, for lenient title and artist matching."""
    text = (text or "").replace("&", " and ")
    return _KEY_RE.sub("", text.lower())


def _key(text: str) -> str:
    return normalize_key(text)


def _clean_candidate_title(title: str) -> str:
    """Candidate titles carry suffixes like ``(Air Raid Vehicle)``; strip them
    before comparing so containment stays meaningful."""
    text = _BRACKETED_RE.sub(" ", title or "")
    return _TRAILING_NOISE_RE.sub("", text).strip(" -|")


def key_ratio(a: str, b: str) -> float:
    """1.0 for equal keys, containment scaled by length, 0 otherwise."""
    ka, kb = _key(a), _key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka in kb or kb in ka:
        return min(len(ka), len(kb)) / max(len(ka), len(kb))
    return 0.0


def _key_ratio(a: str, b: str) -> float:
    return key_ratio(a, b)


def pick_candidate(items: list[dict], title: str, artist: str) -> dict | None:
    """Best search result for ``title``/``artist``, or None.

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
        candidate_title = _clean_candidate_title(item.get("title") or "")
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


def match_confidence(
    title: str, artist: str, candidate_title: str, candidate_artist: str
) -> Literal["exact", "fuzzy"]:
    """Whether a chosen candidate is an exact key match or only containment."""
    title_ratio = _key_ratio(title, _clean_candidate_title(candidate_title))
    artist_ratio = _key_ratio(artist, candidate_artist) if artist.strip() else 1.0
    if title_ratio == 1.0 and artist_ratio == 1.0:
        return "exact"
    return "fuzzy"
