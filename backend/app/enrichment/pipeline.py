"""Background enrichment pipeline for track details.

Mirrors the loudness backfill: a single-flight daemon thread fills empty,
unlocked fields from Deezer and MusicBrainz, records where each field came
from, and remembers definitive misses so they are not retried forever.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import httpx
from sqlmodel import Session, delete, select

from app.config import get_settings
from app.enrichment.base import (
    ProviderData,
    ProviderError,
    USER_AGENT,
    apply_provider_data,
    is_empty,
)
from app.enrichment.deezer import lookup_deezer
from app.enrichment.musicbrainz import lookup_musicbrainz
from app.enrichment.wikipedia import (
    PAUSE_S as WIKI_PAUSE_S,
    PROVIDER as WIKIPEDIA,
    WikipediaData,
    lookup_wikipedia,
)
from app.models import TrackCache, TrackChartEntry, TrackDetail, _utcnow

logger = logging.getLogger(__name__)

# Sentinels so callers can inject a fake provider, disable one with None, or
# leave the real default in place.
UNSET: Any = object()

DEFAULT_PAUSE_S = 0.5
MB_PAUSE_S = 1.05


@dataclass
class EnrichOutcome:
    video_id: str
    committed: bool = False
    matched: bool = False
    applied: int = 0
    providers: list[str] = field(default_factory=list)
    confidence: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class StoryOutcome:
    video_id: str
    committed: bool = False
    matched: bool = False
    applied: int = 0
    has_story: bool = False
    charts: int = 0
    confidence: str | None = None
    errors: list[str] = field(default_factory=list)


def _needs_more(row: TrackDetail) -> bool:
    return any(
        is_empty(getattr(row, field_name, None))
        for field_name in ("album", "release_year", "label", "isrc")
    )


def _record_confidence(outcome: EnrichOutcome, data: ProviderData) -> None:
    if outcome.confidence is None:
        outcome.confidence = data.confidence
    elif data.confidence == "fuzzy":
        outcome.confidence = "fuzzy"


def enrich_track(
    session: Session,
    video_id: str,
    *,
    force: bool = False,
    client: httpx.Client | None = None,
    deezer: Callable[..., ProviderData | None] | None | Any = UNSET,
    musicbrainz: Callable[..., ProviderData | None] | None | Any = UNSET,
) -> EnrichOutcome:
    """Enrich one track, filling only empty/unlocked fields.

    ``force`` refreshes values that were auto-filled before (they carry a
    source entry); fields without a source are treated as manual and kept.
    """
    outcome = EnrichOutcome(video_id=video_id)
    track = session.exec(
        select(TrackCache).where(TrackCache.youtube_video_id == video_id)
    ).first()
    if track is None:
        outcome.errors.append("track not found")
        return outcome

    deezer_fn = lookup_deezer if deezer is UNSET else deezer
    musicbrainz_fn = lookup_musicbrainz if musicbrainz is UNSET else musicbrainz

    row = session.get(TrackDetail, video_id)
    if row is None:
        row = TrackDetail(youtube_video_id=video_id)

    own_client = client is None
    if own_client:
        client = httpx.Client(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        )
    fetched_at = _utcnow().isoformat()

    try:
        if deezer_fn is not None:
            try:
                data = deezer_fn(track.title, track.artist, client)
            except (ProviderError, httpx.HTTPError) as exc:
                outcome.errors.append(f"deezer: {exc}")
                data = None
            if data is not None:
                outcome.providers.append("deezer")
                outcome.matched = True
                _record_confidence(outcome, data)
                outcome.applied += apply_provider_data(
                    row, data, fetched_at=fetched_at, force=force
                )

        if musicbrainz_fn is not None and _needs_more(row):
            try:
                data = musicbrainz_fn(track.title, track.artist, client)
            except (ProviderError, httpx.HTTPError) as exc:
                outcome.errors.append(f"musicbrainz: {exc}")
                data = None
            if data is not None:
                outcome.providers.append("musicbrainz")
                outcome.matched = True
                _record_confidence(outcome, data)
                outcome.applied += apply_provider_data(
                    row, data, fetched_at=fetched_at, force=force
                )
    finally:
        if own_client and isinstance(client, httpx.Client):
            client.close()

    if outcome.providers:
        row.enriched_at = _utcnow()
        row.enrich_error = (
            "; ".join(outcome.errors)[:500] if outcome.errors else None
        )
        row.needs_review = outcome.confidence == "fuzzy"
        session.add(row)
        session.commit()
        session.refresh(row)
        outcome.committed = True
        return outcome

    if outcome.errors:
        # Providers are down / rate-limited: leave the track pending so the
        # next startup or manual run retries it.
        logger.warning(
            "enrichment failed for %s: %s", video_id, outcome.errors
        )
        return outcome

    # Both providers answered but found nothing: remember the miss so a bulk
    # run does not retry it forever. A manual "Fetch details" can try again.
    row.enriched_at = _utcnow()
    row.enrich_error = None
    row.needs_review = False
    session.add(row)
    session.commit()
    outcome.committed = True
    return outcome


def enrich_story(
    session: Session,
    video_id: str,
    *,
    force: bool = False,
    client: httpx.Client | None = None,
    wikipedia: Callable[..., WikipediaData | None] | None | Any = UNSET,
) -> StoryOutcome:
    """Fetch Wikipedia prose and chart placements for one track.

    ``force`` refreshes prose/charts that were auto-filled before; fields
    without a source entry are treated as manual and kept.
    """
    outcome = StoryOutcome(video_id=video_id)
    track = session.exec(
        select(TrackCache).where(TrackCache.youtube_video_id == video_id)
    ).first()
    if track is None:
        outcome.errors.append("track not found")
        return outcome

    wikipedia_fn = lookup_wikipedia if wikipedia is UNSET else wikipedia
    if wikipedia_fn is None:
        return outcome

    row = session.get(TrackDetail, video_id)
    if row is None:
        row = TrackDetail(youtube_video_id=video_id)

    own_client = client is None
    if own_client:
        client = httpx.Client(
            timeout=20.0, headers={"User-Agent": USER_AGENT}
        )
    fetched_at = _utcnow().isoformat()

    try:
        data = wikipedia_fn(track.title, track.artist, client)
    except (ProviderError, httpx.HTTPError) as exc:
        outcome.errors.append(f"wikipedia: {exc}")
        data = None
        failed = True
    else:
        failed = False
    finally:
        if own_client and isinstance(client, httpx.Client):
            client.close()

    if failed:
        # Leave ``story_at`` empty so the bulk run retries after the outage.
        row.story_error = "; ".join(outcome.errors)[:500]
        session.add(row)
        session.commit()
        logger.warning(
            "story lookup failed for %s: %s", video_id, outcome.errors
        )
        return outcome

    if data is None:
        # A definitive miss: remember it so the bulk run does not retry.
        row.story_at = _utcnow()
        row.story_error = None
        session.add(row)
        session.commit()
        outcome.committed = True
        return outcome

    locked = set(row.locked_fields or [])
    outcome.applied = apply_provider_data(
        row,
        ProviderData(
            provider=WIKIPEDIA,
            url=data.url,
            confidence=data.confidence,
            fields={"summary": data.summary, "story": data.story},
        ),
        fetched_at=fetched_at,
        force=force,
    )

    if data.url and "links" not in locked:
        links = list(row.links or [])
        if not any(
            isinstance(link, dict)
            and "wikipedia.org" in (link.get("url") or "")
            for link in links
        ):
            row.links = [*links, {"label": "Wikipedia", "url": data.url}]

    existing = list(
        session.exec(
            select(TrackChartEntry).where(
                TrackChartEntry.youtube_video_id == video_id
            )
        ).all()
    )
    auto_charts = "charts" in (row.sources or {})
    if (
        data.charts
        and "charts" not in locked
        and (not existing or (force and auto_charts))
    ):
        if existing:
            session.exec(
                delete(TrackChartEntry).where(
                    TrackChartEntry.youtube_video_id == video_id
                )
            )
        for chart in data.charts:
            session.add(
                TrackChartEntry(
                    youtube_video_id=video_id,
                    chart_name=chart.chart_name,
                    country=chart.country,
                    peak=chart.peak,
                    weeks_on_chart=chart.weeks_on_chart,
                    year=chart.year,
                    source_url=chart.source_url or data.url,
                )
            )
        sources = dict(row.sources or {})
        sources["charts"] = {
            "provider": WIKIPEDIA,
            "url": data.url,
            "fetched_at": fetched_at,
        }
        row.sources = sources
        outcome.charts = len(data.charts)

    row.story_at = _utcnow()
    row.story_error = None
    row.needs_review = bool(row.needs_review) or data.confidence == "fuzzy"
    session.add(row)
    session.commit()
    session.refresh(row)
    outcome.committed = True
    outcome.matched = True
    outcome.has_story = bool(row.summary or row.story)
    outcome.confidence = data.confidence
    return outcome


def _pending_story_ids(session: Session, limit: int) -> list[str]:
    unique: dict[str, TrackCache] = {}
    for row in session.exec(select(TrackCache).order_by(TrackCache.id)).all():
        unique.setdefault(row.youtube_video_id, row)
    details = {
        row.youtube_video_id: row
        for row in session.exec(select(TrackDetail)).all()
    }
    pending: list[str] = []
    for video_id in unique:
        detail = details.get(video_id)
        if detail is None or (
            detail.story_at is None and not detail.story_error
        ):
            pending.append(video_id)
            if len(pending) >= limit:
                break
    return pending


def enrich_stories_pending(
    session_factory: Callable[[], Session],
    client: httpx.Client,
    *,
    limit: int = 100,
    pause_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    wikipedia: Callable[..., WikipediaData | None] | None | Any = UNSET,
) -> int:
    """Fetch stories for up to ``limit`` tracks that have none yet."""
    settings = get_settings()
    pause = (
        settings.enrichment_pause_seconds
        if pause_seconds is None
        else pause_seconds
    )
    with session_factory() as session:
        pending = _pending_story_ids(session, limit)

    processed = 0
    consecutive_errors = 0
    for video_id in pending:
        try:
            with session_factory() as session:
                outcome = enrich_story(
                    session, video_id, client=client, wikipedia=wikipedia
                )
        except Exception:  # noqa: BLE001 - keep the batch alive
            logger.exception("story lookup crashed for %s", video_id)
            outcome = StoryOutcome(video_id=video_id, errors=["crashed"])

        if outcome.committed:
            processed += 1
            consecutive_errors = 0
        else:
            consecutive_errors += 1
            if consecutive_errors >= settings.enrichment_max_consecutive_errors:
                logger.warning(
                    "story enrichment aborted after %d consecutive errors",
                    consecutive_errors,
                )
                break

        delay = max(pause, WIKI_PAUSE_S)
        if delay:
            sleep(delay)
    return processed


def _pending_video_ids(session: Session, limit: int) -> list[str]:
    unique: dict[str, TrackCache] = {}
    for row in session.exec(select(TrackCache).order_by(TrackCache.id)).all():
        unique.setdefault(row.youtube_video_id, row)
    details = {
        row.youtube_video_id: row
        for row in session.exec(select(TrackDetail)).all()
    }
    pending: list[str] = []
    for video_id in unique:
        detail = details.get(video_id)
        if detail is None or (
            detail.enriched_at is None and not detail.enrich_error
        ):
            pending.append(video_id)
            if len(pending) >= limit:
                break
    return pending


def enrich_pending(
    session_factory: Callable[[], Session],
    client: httpx.Client,
    *,
    limit: int = 100,
    pause_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    deezer: Callable[..., ProviderData | None] | None | Any = UNSET,
    musicbrainz: Callable[..., ProviderData | None] | None | Any = UNSET,
) -> int:
    """Enrich up to ``limit`` pending video ids; returns committed tracks."""
    settings = get_settings()
    pause = (
        settings.enrichment_pause_seconds
        if pause_seconds is None
        else pause_seconds
    )
    with session_factory() as session:
        pending = _pending_video_ids(session, limit)

    processed = 0
    consecutive_errors = 0
    for video_id in pending:
        try:
            with session_factory() as session:
                outcome = enrich_track(
                    session,
                    video_id,
                    client=client,
                    deezer=deezer,
                    musicbrainz=musicbrainz,
                )
        except Exception:  # noqa: BLE001 - keep the batch alive
            logger.exception("enrichment crashed for %s", video_id)
            outcome = EnrichOutcome(video_id=video_id, errors=["crashed"])

        if outcome.committed:
            processed += 1
            consecutive_errors = 0
        else:
            consecutive_errors += 1
            if consecutive_errors >= settings.enrichment_max_consecutive_errors:
                logger.warning(
                    "enrichment aborted after %d consecutive errors",
                    consecutive_errors,
                )
                break

        used_mb = "musicbrainz" in outcome.providers
        delay = max(pause, MB_PAUSE_S) if used_mb else pause
        if delay:
            sleep(delay)
    return processed


def clear_errors(session_factory: Callable[[], Session]) -> int:
    """Make previously failed tracks pending again (manual retry)."""
    with session_factory() as session:
        cleared = 0
        for row in session.exec(select(TrackDetail)).all():
            changed = False
            if row.enrich_error and row.enriched_at is None:
                row.enrich_error = None
                changed = True
            if row.story_error and row.story_at is None:
                row.story_error = None
                changed = True
            if changed:
                session.add(row)
                cleared += 1
        session.commit()
    return cleared


def progress(session: Session) -> dict[str, Any]:
    video_ids = {
        row for row in session.exec(select(TrackCache.youtube_video_id)).all()
    }
    details = {
        row.youtube_video_id: row
        for row in session.exec(select(TrackDetail)).all()
        if row.youtube_video_id in video_ids
    }
    enriched = sum(
        1 for row in details.values() if row.enriched_at is not None
    )
    failed = sum(
        1
        for row in details.values()
        if row.enriched_at is None and row.enrich_error
    )
    total = len(video_ids)
    return {
        "running": is_running(),
        "total": total,
        "enriched": enriched,
        "failed": failed,
        "remaining": max(0, total - enriched - failed),
        "stories": sum(
            1 for row in details.values() if row.story_at is not None
        ),
        "stories_failed": sum(
            1
            for row in details.values()
            if row.story_at is None and row.story_error
        ),
    }


_start_lock = threading.Lock()
_running = threading.Event()


def is_running() -> bool:
    return _running.is_set()


def ensure_backfill(*, retry_failed: bool = False) -> bool:
    """Start the single-flight enrichment worker."""
    if not get_settings().enrichment_enabled:
        return False
    with _start_lock:
        if _running.is_set():
            return False
        _running.set()
    threading.Thread(
        target=_worker,
        args=(retry_failed,),
        name="track-enrichment",
        daemon=True,
    ).start()
    return True


def _worker(retry_failed: bool) -> None:
    from app.db import engine

    try:
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            )
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        factory = partial(Session, engine)
        if retry_failed:
            cleared = clear_errors(factory)
            logger.info(
                "track enrichment: cleared %d previous failures", cleared
            )

        processed = 0
        logger.info("track enrichment started")
        with httpx.Client(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            while True:
                batch = enrich_pending(factory, client)
                if batch <= 0:
                    break
                processed += batch
                logger.info(
                    "track enrichment: %d tracks processed", processed
                )
            logger.info(
                "track enrichment finished: %d tracks processed", processed
            )

            stories = 0
            logger.info("track stories started")
            while True:
                batch = enrich_stories_pending(factory, client)
                if batch <= 0:
                    break
                stories += batch
                logger.info("track stories: %d processed", stories)
            logger.info("track stories finished: %d processed", stories)
    except Exception:  # noqa: BLE001 - background best-effort
        logger.exception("track enrichment aborted")
    finally:
        _running.clear()
