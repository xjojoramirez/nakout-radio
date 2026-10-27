"""Compose curated track details from agent-researched evidence.

Only the agent write path uses this module. Facts are fill-only: an existing
album, year, label, ISRC or credit list is never overwritten. Prose may replace
a value that came from a provider, but not a manually entered value. Every
field the composer writes is locked and keeps the evidence URL that justified
it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session

from app.enrichment.base import is_empty
from app.models import TrackDetail, _utcnow
from app.schemas import TrackDetailOut
from app.track_details import admin_detail, track_row

_PROSE_FIELDS = ("summary", "story")
_FACT_FIELDS = ("album", "release_year", "label", "isrc", "credits")
_FIELD_ORDER = ("summary", "story", *_FACT_FIELDS)

_SUMMARY_MIN = 40
_SUMMARY_MAX = 220
_STORY_MIN = 80
_STORY_MAX = 400
_PROVIDER_RE = re.compile(r"^[a-z0-9_-]{2,20}$")
_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{2}[0-9]{5}$")


@dataclass
class ComposeChange:
    field: str
    value: Any
    previous: Any = None


@dataclass
class ComposeSkip:
    field: str
    reason: str
    current: Any = None


@dataclass
class ComposeResult:
    video_id: str
    dry_run: bool = False
    changes: list[ComposeChange] = field(default_factory=list)
    skipped: list[ComposeSkip] = field(default_factory=list)
    detail: TrackDetailOut | None = None


def infer_provider(url: str) -> str:
    """Use the source's own name when the URL identifies a known provider."""
    host = urlparse(url).netloc.lower().split(":")[0]
    for domain, provider in (
        ("wikipedia.org", "wikipedia"),
        ("musicbrainz.org", "musicbrainz"),
        ("deezer.com", "deezer"),
    ):
        if host == domain or host.endswith(f".{domain}"):
            return provider
    return "editor"


def _clean_url(value: str) -> str:
    url = (value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("a source URL is required (http or https)")
    if len(url) > 500:
        raise ValueError("source URL must be 500 characters or fewer")
    return url


def _clean_provider(value: str | None, url: str) -> str:
    provider = (value or infer_provider(url)).strip().lower()
    if not _PROVIDER_RE.fullmatch(provider):
        raise ValueError(
            "provider must be 2-20 lowercase letters, digits, _ or -"
        )
    return provider


def _clean_prose(value: str, field_name: str) -> str:
    text = " ".join((value or "").split())
    if field_name == "summary":
        low, high = _SUMMARY_MIN, _SUMMARY_MAX
    else:
        low, high = _STORY_MIN, _STORY_MAX
    if not low <= len(text) <= high:
        raise ValueError(
            f"{field_name} must be between {low} and {high} characters"
        )
    return text


def _clean_text(value: str, field_name: str, max_length: int) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    if len(text) > max_length:
        raise ValueError(
            f"{field_name} must be {max_length} characters or fewer"
        )
    return text


def _clean_year(value: int) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("release year must be a four-digit year") from exc
    if not 1900 <= year <= 2100:
        raise ValueError("release year must be between 1900 and 2100")
    return year


def _clean_isrc(value: str) -> str:
    isrc = re.sub(r"[\s-]", "", (value or "")).upper()
    if not _ISRC_RE.fullmatch(isrc):
        raise ValueError(
            "ISRC must be 12 characters: two-letter country, registrant, "
            "year and designation"
        )
    return isrc


def _clean_credits(value: list[dict]) -> list[dict]:
    credits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("credit must be a role and a name")
        role = str(entry.get("role") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not role or not name:
            raise ValueError("credit role and name must not be empty")
        if len(role) > 120 or len(name) > 120:
            raise ValueError("credit role and name must be 120 characters or fewer")
        key = (role.casefold(), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        credits.append({"role": role, "name": name})
    if not credits:
        raise ValueError("at least one credit is required when credits are set")
    return credits


def _collect_values(
    *,
    summary: str | None,
    story: str | None,
    album: str | None,
    release_year: int | None,
    label: str | None,
    isrc: str | None,
    credits: list[dict] | None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if summary is not None:
        values["summary"] = _clean_prose(summary, "summary")
    if story is not None:
        values["story"] = _clean_prose(story, "story")
    if album is not None:
        values["album"] = _clean_text(album, "album", 300)
    if release_year is not None:
        values["release_year"] = _clean_year(release_year)
    if label is not None:
        values["label"] = _clean_text(label, "label", 200)
    if isrc is not None:
        values["isrc"] = _clean_isrc(isrc)
    if credits is not None:
        values["credits"] = _clean_credits(credits)
    if not values:
        raise ValueError("at least one field is required")
    return values


def _plan(
    row: TrackDetail,
    values: dict[str, Any],
    locked: set[str],
    sources: dict,
) -> tuple[list[ComposeChange], list[ComposeSkip]]:
    changes: list[ComposeChange] = []
    skipped: list[ComposeSkip] = []
    for field_name in _FIELD_ORDER:
        if field_name not in values:
            continue
        current = getattr(row, field_name, None)
        if field_name in locked:
            skipped.append(ComposeSkip(field_name, "locked", current))
            continue
        if field_name in _PROSE_FIELDS:
            if is_empty(current) or field_name in sources:
                changes.append(
                    ComposeChange(field_name, values[field_name], current)
                )
            else:
                skipped.append(
                    ComposeSkip(field_name, "manual prose", current)
                )
            continue
        if is_empty(current):
            changes.append(ComposeChange(field_name, values[field_name], current))
        else:
            skipped.append(ComposeSkip(field_name, "already set", current))
    return changes, skipped


def compose_detail(
    session: Session,
    video_id: str,
    *,
    summary: str | None = None,
    story: str | None = None,
    album: str | None = None,
    release_year: int | None = None,
    label: str | None = None,
    isrc: str | None = None,
    credits: list[dict] | None = None,
    source_url: str,
    provider: str | None = None,
    dry_run: bool = False,
) -> ComposeResult | None:
    """Apply an agent-composed detail payload, or preview it with ``dry_run``.

    Returns ``None`` when the video id is not in the track cache. Raises
    ``ValueError`` for an invalid payload so the CLI can print a usable error.
    """
    if track_row(session, video_id) is None:
        return None

    url = _clean_url(source_url)
    provider_name = _clean_provider(provider, url)
    values = _collect_values(
        summary=summary,
        story=story,
        album=album,
        release_year=release_year,
        label=label,
        isrc=isrc,
        credits=credits,
    )

    row = session.get(TrackDetail, video_id)
    if row is None:
        row = TrackDetail(youtube_video_id=video_id)

    locked = set(row.locked_fields or [])
    sources = dict(row.sources or {})
    changes, skipped = _plan(row, values, locked, sources)
    result = ComposeResult(
        video_id=video_id,
        dry_run=dry_run,
        changes=changes,
        skipped=skipped,
    )
    if dry_run or not changes:
        return result

    now = _utcnow()
    fetched_at = now.isoformat()
    locks = list(row.locked_fields or [])
    for change in changes:
        setattr(row, change.field, change.value)
        if change.field not in locks:
            locks.append(change.field)
        sources[change.field] = {
            "provider": provider_name,
            "url": url,
            "fetched_at": fetched_at,
        }
    row.locked_fields = locks
    row.sources = sources
    if any(change.field == "story" for change in changes):
        row.story_at = now
        row.story_error = None
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    result.detail = admin_detail(session, video_id)
    return result
