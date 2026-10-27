"""CLI used by the track agents to read and compose track details.

    python -m app.detail_tools find "Jump"
    python -m app.detail_tools show <video_id>
    python -m app.detail_tools apply <video_id> --source-url URL \
        [--summary TEXT] [--story TEXT] [--album TEXT] [--release-year YEAR] \
        [--label TEXT] [--isrc CODE] [--credit "Role=Name"] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from sqlmodel import Session

from app.composer import ComposeChange, ComposeResult, compose_detail
from app.db import engine
from app.track_details import admin_detail, library_page


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_credits(pairs: list[str]) -> list[dict] | None:
    if not pairs:
        return None
    credits: list[dict] = []
    for pair in pairs:
        role, separator, name = pair.partition("=")
        if not separator:
            raise ValueError(f"credit must be Role=Name: {pair}")
        credits.append({"role": role, "name": name})
    return credits


def _short(value: Any, limit: int = 80) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}..."


def _describe(change: ComposeChange) -> str:
    if change.field in {"summary", "story"}:
        return f"{change.field} ({len(change.value)} chars)"
    return change.field


def _print_result(result: ComposeResult) -> None:
    if result.changes:
        verb = "would apply" if result.dry_run else "applied"
        fields = ", ".join(_describe(change) for change in result.changes)
        print(f"{verb}: {fields}")
    else:
        print("no changes")
    for skip in result.skipped:
        suffix = ""
        if skip.reason == "already set":
            suffix = f": {_short(skip.current)}"
        print(f"skipped: {skip.field} ({skip.reason}{suffix})")
    if result.dry_run:
        print(f"dry run for {result.video_id}: nothing written")
    elif result.detail is not None:
        print(
            f"saved {len(result.changes)} fields for "
            f"{result.detail.artist} - {result.detail.title}"
        )


def _find(args: argparse.Namespace) -> int:
    limit = max(1, min(args.limit, 50))
    with Session(engine) as session:
        page = library_page(session, query=args.query, limit=limit)
        items = [item.model_dump(mode="json") for item in page.items]
    _print_json(items)
    if not items:
        print("no matches", file=sys.stderr)
        return 1
    return 0


def _show(args: argparse.Namespace) -> int:
    with Session(engine) as session:
        detail = admin_detail(session, args.video_id)
    if detail is None:
        print("error: track not found", file=sys.stderr)
        return 1
    _print_json(detail.model_dump(mode="json"))
    return 0


def _apply(args: argparse.Namespace) -> int:
    try:
        credits = _parse_credits(args.credit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with Session(engine) as session:
        try:
            result = compose_detail(
                session,
                args.video_id,
                summary=args.summary,
                story=args.story,
                album=args.album,
                release_year=args.release_year,
                label=args.label,
                isrc=args.isrc,
                credits=credits,
                source_url=args.source_url,
                provider=args.provider,
                dry_run=args.dry_run,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if result is None:
        print("error: track not found", file=sys.stderr)
        return 1
    _print_result(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="detail_tools")
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("find", help="find tracks by title or artist")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=10)
    find.set_defaults(func=_find)

    show = sub.add_parser("show", help="show a track detail record as JSON")
    show.add_argument("video_id")
    show.set_defaults(func=_show)

    apply = sub.add_parser("apply", help="compose detail fields from evidence")
    apply.add_argument("video_id")
    apply.add_argument("--source-url", required=True)
    apply.add_argument("--provider")
    apply.add_argument("--summary")
    apply.add_argument("--story")
    apply.add_argument("--album")
    apply.add_argument("--release-year", type=int)
    apply.add_argument("--label")
    apply.add_argument("--isrc")
    apply.add_argument(
        "--credit",
        action="append",
        default=[],
        metavar="ROLE=NAME",
    )
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(func=_apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
