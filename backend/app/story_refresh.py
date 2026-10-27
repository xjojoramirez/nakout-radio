"""Refresh provider-written Wikipedia prose after an extractor change.

    python -m app.story_refresh --dry-run
    python -m app.story_refresh
    python -m app.story_refresh --only-long
    python -m app.story_refresh --limit 20

Only rows whose summary or story came from Wikipedia are selected, and only
while that field is unlocked. Composer-written prose and manual text keep their
locks and sources. Charts are not touched.
"""

from __future__ import annotations

import argparse
import time

import httpx
from sqlmodel import Session, select

from app.db import engine
from app.enrichment.base import USER_AGENT
from app.enrichment.pipeline import enrich_story
from app.enrichment.wikipedia import (
    STORY_LIMIT,
    SUMMARY_LIMIT,
    lookup_wikipedia,
)
from app.models import TrackDetail

PROVIDER = "wikipedia"
PAUSE_S = 0.8
_LIMITS = {"summary": SUMMARY_LIMIT, "story": STORY_LIMIT}


def _prose_only(title: str, artist: str, client: httpx.Client):
    """Refresh prose without replacing the existing chart rows."""
    return lookup_wikipedia(title, artist, client, with_charts=False)


def provider_prose_ids(
    session: Session, *, only_long: bool = False
) -> list[str]:
    """Video ids with at least one unlocked, Wikipedia-sourced prose field."""
    ids: list[str] = []
    rows = session.exec(
        select(TrackDetail).order_by(TrackDetail.youtube_video_id)
    ).all()
    for row in rows:
        sources = row.sources or {}
        locked = set(row.locked_fields or [])
        for field_name in ("summary", "story"):
            source = sources.get(field_name)
            if (
                field_name not in locked
                and isinstance(source, dict)
                and source.get("provider") == PROVIDER
                and (
                    not only_long
                    or len(getattr(row, field_name) or "")
                    > _LIMITS[field_name]
                )
            ):
                ids.append(row.youtube_video_id)
                break
    return ids


def refresh(
    ids: list[str],
    *,
    pause: float = PAUSE_S,
    dry_run: bool = False,
) -> int:
    if dry_run:
        for video_id in ids:
            print(video_id)
        print(f"would refresh {len(ids)} tracks")
        return 0

    processed = 0
    with httpx.Client(
        timeout=20.0, headers={"User-Agent": USER_AGENT}
    ) as client:
        for video_id in ids:
            try:
                with Session(engine) as session:
                    outcome = enrich_story(
                        session,
                        video_id,
                        force=True,
                        client=client,
                        wikipedia=_prose_only,
                    )
            except Exception as exc:  # noqa: BLE001 - keep the batch alive
                print(f"{video_id}: error: {exc}")
                continue
            if outcome.committed:
                processed += 1
            detail = outcome.errors[0] if outcome.errors else "ok"
            print(f"{video_id}: {outcome.applied} applied, {detail}")
            if pause:
                time.sleep(pause)
    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="story_refresh")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="maximum tracks to refresh (0 = all)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only-long",
        action="store_true",
        help="only rows whose unlocked prose is still over the limit",
    )
    args = parser.parse_args(argv)

    with Session(engine) as session:
        ids = provider_prose_ids(session, only_long=args.only_long)
    if args.limit > 0:
        ids = ids[: args.limit]

    processed = refresh(ids, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"refreshed {processed} of {len(ids)} tracks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
