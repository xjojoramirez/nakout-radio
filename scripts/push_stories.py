#!/usr/bin/env python3
"""Push locally curated track stories to the live Nakout library.

The script talks only to the two HTTP APIs:

  GET  <local>/api/library/export
  GET  <live>/api/library/export
  POST <live>/api/library/import[?dry_run=true]

It copies only ``summary``, ``story`` and ``dj_note`` from local to live,
matched by YouTube video id, and sends a playlist-free snapshot so live
playlists and memberships are never reconciled. Live album/year/label/charts
and all other detail fields are preserved.

The live import route must be enabled for the duration of the push:

  LIBRARY_IMPORT_ENABLED=true

It uses only the standard library, so it runs on any machine with Python 3.10+.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
STORY_FIELDS = ("summary", "story", "dj_note")


def _base(value: str) -> str:
    return value.rstrip("/")


def _call(
    method: str,
    url: str,
    *,
    key: str,
    payload: dict | None = None,
    timeout: float,
) -> dict:
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        hint = ""
        if exc.code == 404 and "/api/library/import" in url:
            hint = (
                " (the target import route is disabled; set "
                "LIBRARY_IMPORT_ENABLED=true and recreate the backend)"
            )
        raise SystemExit(
            f"{method} {url} failed with HTTP {exc.code}: {detail}{hint}"
        ) from exc
    except URLError as exc:
        raise SystemExit(f"{method} {url} failed: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{method} {url} returned non-JSON data") from exc


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _selected_fields(
    local_detail: dict, *, include_unlocked: bool
) -> tuple[dict[str, str], set[str], int]:
    """Return selected story fields, local locks, and unlocked fields skipped."""
    locks = set(local_detail.get("locked_fields") or [])
    selected: dict[str, str] = {}
    unlocked = 0
    for field in STORY_FIELDS:
        value = _text(local_detail.get(field))
        if not value:
            continue
        if not include_unlocked and field not in locks:
            unlocked += 1
            continue
        selected[field] = value
    return selected, locks, unlocked


def _merge_detail(
    live_detail: dict | None,
    local_detail: dict,
    selected: dict[str, str],
    local_locks: set[str],
    *,
    lock: bool,
) -> dict:
    """Overlay only story fields onto the live detail payload."""
    merged = copy.deepcopy(live_detail) if live_detail else {}

    for field, value in selected.items():
        merged[field] = value
    if "dj_note" in selected:
        merged["dj_note_public"] = local_detail.get("dj_note_public", True)
    if "summary" in selected or "story" in selected:
        story_at = local_detail.get("story_at")
        if story_at:
            merged["story_at"] = story_at

    sources = dict(merged.get("sources") or {})
    local_sources = local_detail.get("sources") or {}
    for field in selected:
        if field in local_sources:
            sources[field] = local_sources[field]
        else:
            sources.pop(field, None)
    merged["sources"] = sources

    locks = list(dict.fromkeys(merged.get("locked_fields") or []))
    for field in selected:
        if (field in local_locks or lock) and field not in locks:
            locks.append(field)
    merged["locked_fields"] = locks
    return merged


def _build_track(
    live_track: dict,
    local_track: dict,
    selected: dict[str, str],
    local_locks: set[str],
    *,
    lock: bool,
) -> dict:
    track = copy.deepcopy(live_track)
    track["playlists"] = []
    track["detail"] = _merge_detail(
        live_track.get("detail"),
        local_track["detail"],
        selected,
        local_locks,
        lock=lock,
    )
    return track


def _format_result(result: dict) -> list[str]:
    lines = [
        f"  tracks:      {result.get('tracks_created', 0)} created, "
        f"{result.get('tracks_updated', 0)} updated, "
        f"{result.get('tracks_unchanged', 0)} unchanged",
        f"  memberships: {result.get('memberships_added', 0)} added, "
        f"{result.get('memberships_removed', 0)} removed, "
        f"{result.get('tracks_detached', 0)} detached",
        f"  details:     {result.get('details_created', 0)} created, "
        f"{result.get('details_updated', 0)} updated, "
        f"{result.get('details_unchanged', 0)} unchanged",
        f"  charts:      {result.get('charts_replaced', 0)} replaced",
    ]
    if result.get("locked_fields_skipped"):
        lines.append(
            f"  locks:       {result['locked_fields_skipped']} live field(s) kept"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Push curated local track stories to the live Nakout library."
        )
    )
    parser.add_argument(
        "--from",
        dest="source",
        default="http://localhost:8011",
        help="Local base URL (default: http://localhost:8011)",
    )
    parser.add_argument(
        "--to",
        dest="target",
        required=True,
        help="Live base URL, e.g. https://radio.example.com",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("LIBRARY_API_KEY", ""),
        help="Bearer key for the local export (default: $LIBRARY_API_KEY)",
    )
    parser.add_argument(
        "--import-key",
        default=None,
        help="Bearer key for the live import (default: --key)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Include unlocked local prose too; by default only fields that "
            "are already locked locally are pushed"
        ),
    )
    parser.add_argument(
        "--no-lock",
        action="store_false",
        dest="lock",
        help=(
            "Do not lock fields that were not already locked locally "
            "(live enrichment may overwrite them)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count on live without committing",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Write the generated snapshot to this file",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds (default: 120)",
    )
    args = parser.parse_args(argv)

    source_key = args.key.strip()
    if not source_key:
        parser.error("no local key: pass --key or set LIBRARY_API_KEY")
    import_key = (args.import_key or source_key).strip()

    source = _base(args.source)
    target = _base(args.target)

    local_snapshot = _call(
        "GET",
        f"{source}/api/library/export",
        key=source_key,
        timeout=args.timeout,
    )
    live_snapshot = _call(
        "GET",
        f"{target}/api/library/export",
        key=import_key,
        timeout=args.timeout,
    )
    for label, snapshot in (
        ("local", local_snapshot),
        ("live", live_snapshot),
    ):
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise SystemExit(
                f"unsupported {label} snapshot schema_version: "
                f"{snapshot.get('schema_version')!r}"
            )

    local_tracks = local_snapshot.get("tracks") or []
    live_tracks = live_snapshot.get("tracks") or []
    live_by_id = {
        track.get("youtube_video_id"): track for track in live_tracks
    }

    selected_tracks: list[dict] = []
    counts = {field: 0 for field in STORY_FIELDS}
    unlocked_fields = 0
    unlocked_tracks = 0
    empty_tracks = 0
    unmatched = 0
    for local_track in local_tracks:
        detail = local_track.get("detail")
        if not detail:
            continue
        selected, local_locks, unlocked = _selected_fields(
            detail, include_unlocked=args.all
        )
        unlocked_fields += unlocked
        if not selected:
            if any(_text(detail.get(field)) for field in STORY_FIELDS):
                unlocked_tracks += 1
            else:
                empty_tracks += 1
            continue

        video_id = local_track.get("youtube_video_id")
        live_track = live_by_id.get(video_id)
        if live_track is None:
            unmatched += 1
            continue

        selected_tracks.append(
            _build_track(
                live_track,
                local_track,
                selected,
                local_locks,
                lock=args.lock,
            )
        )
        for field in selected:
            counts[field] += 1

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "playlists": [],
        "tracks": selected_tracks,
    }

    print(
        f"local snapshot: {len(local_tracks)} tracks, "
        f"{sum(1 for track in local_tracks if track.get('detail'))} details"
    )
    print(
        f"live snapshot:  {len(live_tracks)} tracks, "
        f"{sum(1 for track in live_tracks if track.get('detail'))} details"
    )
    print(
        f"selected:       {len(selected_tracks)} tracks "
        f"({counts['summary']} summary, {counts['story']} story, "
        f"{counts['dj_note']} DJ note)"
    )
    if unlocked_fields:
        print(
            f"skipped:        {unlocked_fields} unlocked field(s) "
            "(pass --all to include them)"
        )
    if unlocked_tracks:
        print(
            f"skipped:        {unlocked_tracks} track(s) with only "
            "unlocked fields (pass --all)"
        )
    if empty_tracks:
        print(
            f"skipped:        {empty_tracks} track(s) with no story fields"
        )
    if unmatched:
        print(
            f"skipped:        {unmatched} track(s) with no live match"
        )
    print(f"payload:        {len(selected_tracks)} tracks, 0 playlists")

    if not selected_tracks:
        print("nothing to push")
        return 0

    if args.save:
        args.save.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"saved snapshot to {args.save}")

    if args.all and not args.lock:
        print(
            "warning: unlocked fields may be overwritten by live enrichment",
            file=sys.stderr,
        )

    url = f"{target}/api/library/import"
    if args.dry_run:
        url += "?dry_run=true"
    result = _call(
        "POST",
        url,
        key=import_key,
        payload=payload,
        timeout=args.timeout,
    )
    print("dry run: no live changes applied" if args.dry_run else "pushed")
    for line in _format_result(result):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
