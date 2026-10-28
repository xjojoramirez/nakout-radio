#!/usr/bin/env python3
"""Push reviewed, locked fact fields from local to the live library.

The normal direction is live -> local. This tool is the narrow reverse path for
facts that were corrected locally and reviewed: album, release date/year,
label, catalog/track/disc numbers, ISRC, genres, country, language, BPM,
musical key, cover, credits and links.

Only fields that are *locked locally* are candidates. That makes the lock the
review boundary: if a field was not explicitly kept, this tool will not send
it. Tracks are selected explicitly with ``--video-id`` or ``--ids-file``; the
tool never pushes the whole library by accident.

The payload starts from the live detail and overlays only the selected local
fields, so live prose, charts, timestamps and every other field are preserved.
The sent snapshot has no playlists, so live memberships are never reconciled.

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

# The reviewed fact fields this tool is allowed to send. Keep this list
# explicit: adding a new field here is a deliberate widening of the write.
FACT_FIELDS = (
    "album",
    "album_artist",
    "release_date",
    "release_year",
    "label",
    "catalog_number",
    "track_number",
    "disc_number",
    "isrc",
    "genres",
    "country",
    "language",
    "bpm",
    "musical_key",
    "cover_url",
    "credits",
    "links",
)


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


def load_ids(video_ids: list[str], ids_file: Path | None) -> list[str]:
    """Return unique ids from repeated flags and/or a text file.

    The file accepts one id per line, comma/whitespace-separated values, and
    ``#`` comments.
    """
    ids: list[str] = []
    for value in video_ids:
        value = value.strip()
        if value:
            ids.append(value)
    if ids_file is not None:
        text = ids_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.split("#", 1)[0]
            for token in line.replace(",", " ").split():
                if token:
                    ids.append(token)
    return list(dict.fromkeys(ids))


def build_track(
    live_track: dict,
    local_track: dict,
) -> tuple[dict | None, list[tuple[str, object, object]], list[str]]:
    """Overlay reviewed local facts onto a copy of the live track.

    Returns ``(track, diffs, skipped)``. ``track`` is ``None`` when there is
    nothing safe to push. ``diffs`` contains ``(field, live, local)`` for values
    that actually differ; equal values are still included in the payload so
    their locks travel, but they are not reported as changes.
    """
    local_detail = local_track.get("detail") or {}
    live_detail = live_track.get("detail") or {}
    if not live_detail:
        return None, [], ["no live detail"]

    local_locks = set(local_detail.get("locked_fields") or [])
    live_locks = set(live_detail.get("locked_fields") or [])
    local_sources = local_detail.get("sources") or {}
    candidates = [field for field in FACT_FIELDS if field in local_locks]
    if not candidates:
        return None, [], ["no locked fact fields locally"]

    detail = copy.deepcopy(live_detail)
    sources = dict(detail.get("sources") or {})
    diffs: list[tuple[str, object, object]] = []
    skipped: list[str] = []
    pushed: list[str] = []

    for field in candidates:
        if field in live_locks:
            skipped.append(f"{field}: live field is locked")
            continue
        if field not in local_sources:
            skipped.append(f"{field}: no local source")
            continue
        local_value = local_detail.get(field)
        live_value = live_detail.get(field)
        detail[field] = local_value
        sources[field] = local_sources[field]
        pushed.append(field)
        if local_value != live_value:
            diffs.append((field, live_value, local_value))

    if not pushed:
        return None, [], skipped

    detail["sources"] = sources
    detail["locked_fields"] = list(
        dict.fromkeys(list(live_detail.get("locked_fields") or []) + pushed)
    )
    track = copy.deepcopy(live_track)
    track["playlists"] = []
    track["detail"] = detail
    return track, diffs, skipped


def build_payload(
    local_snapshot: dict,
    live_snapshot: dict,
    ids: list[str],
) -> tuple[dict, list[tuple[dict, list[tuple[str, object, object]], list[str]]], list[str]]:
    """Build a playlist-free facts snapshot and a per-track report."""
    local_tracks = {
        track["youtube_video_id"]: track
        for track in local_snapshot.get("tracks") or []
    }
    live_tracks = {
        track["youtube_video_id"]: track
        for track in live_snapshot.get("tracks") or []
    }

    tracks: list[dict] = []
    report: list[tuple[dict, list[tuple[str, object, object]], list[str]]] = []
    skipped_tracks: list[str] = []
    for video_id in ids:
        local_track = local_tracks.get(video_id)
        live_track = live_tracks.get(video_id)
        if local_track is None:
            skipped_tracks.append(f"{video_id}: not found locally")
            continue
        if live_track is None:
            skipped_tracks.append(f"{video_id}: not found on live")
            continue
        track, diffs, skipped = build_track(live_track, local_track)
        if track is None:
            reason = "; ".join(skipped) if skipped else "nothing to push"
            skipped_tracks.append(f"{video_id}: {reason}")
            continue
        tracks.append(track)
        report.append((track, diffs, skipped))

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "playlists": [],
        "tracks": tracks,
    }
    return payload, report, skipped_tracks


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
            "Push reviewed, locked fact fields from local to the live library."
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
        "--video-id",
        action="append",
        default=[],
        help="Video id to push; repeat for multiple tracks",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="File with video ids (one per line or comma/space-separated)",
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

    ids = load_ids(args.video_id, args.ids_file)
    if not ids:
        parser.error("pass at least one --video-id or an --ids-file")

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

    payload, report, skipped_tracks = build_payload(
        local_snapshot, live_snapshot, ids
    )

    changed = sum(len(diffs) for _, diffs, _ in report)
    print(f"local snapshot: {len(local_snapshot.get('tracks') or [])} tracks")
    print(f"live snapshot:  {len(live_snapshot.get('tracks') or [])} tracks")
    print(
        f"selected:       {len(payload['tracks'])} tracks, "
        f"{changed} changed field(s)"
    )
    print(f"payload:        {len(payload['tracks'])} tracks, 0 playlists")

    for track, diffs, skipped in report:
        detail = track.get("detail") or {}
        print(
            f"\n{track.get('artist', '')} - {track.get('title', '')} "
            f"[{track.get('youtube_video_id', '')}]"
        )
        for field, live_value, local_value in diffs:
            print(f"  {field}: {live_value!r} -> {local_value!r}")
        for item in skipped:
            print(f"  skipped: {item}")
        if detail.get("locked_fields"):
            print(f"  locks after: {detail['locked_fields']}")

    if skipped_tracks:
        print("\nskipped tracks:")
        for item in skipped_tracks:
            print(f"  {item}")

    if not payload["tracks"]:
        print("\nnothing to push")
        return 0

    if args.save:
        args.save.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"saved snapshot to {args.save}")

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
