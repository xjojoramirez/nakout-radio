#!/usr/bin/env python3
"""Pull the live Nakout music library into a local deployment.

The script talks only to the two HTTP APIs:

  GET  <live>/api/library/export
  POST <local>/api/library/import

It uses the standard library, so it runs on any machine with Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1


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
        raise SystemExit(
            f"{method} {url} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise SystemExit(f"{method} {url} failed: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{method} {url} returned non-JSON data") from exc


def _summary(snapshot: dict) -> str:
    tracks = snapshot.get("tracks") or []
    standalone = sum(1 for track in tracks if not track.get("playlists"))
    return (
        f"live snapshot: {len(tracks)} tracks "
        f"({standalone} with no playlist), "
        f"{len(snapshot.get('playlists') or [])} playlists"
    )


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
            f"  locks:       {result['locked_fields_skipped']} field(s) kept local"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull the live Nakout library into a local deployment."
    )
    parser.add_argument(
        "--from",
        dest="source",
        required=True,
        help="Live base URL, e.g. https://radio.example.com",
    )
    parser.add_argument(
        "--to",
        dest="target",
        default="http://localhost:8011",
        help="Local base URL (default: http://localhost:8011)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("LIBRARY_API_KEY", ""),
        help="Bearer key for the live export (default: $LIBRARY_API_KEY)",
    )
    parser.add_argument(
        "--import-key",
        default=None,
        help="Bearer key for the local import (default: --key)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count locally without committing",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Write the downloaded snapshot to this file",
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
        parser.error("no live key: pass --key or set LIBRARY_API_KEY")
    import_key = (args.import_key or source_key).strip()

    source = _base(args.source)
    target = _base(args.target)

    snapshot = _call(
        "GET",
        f"{source}/api/library/export",
        key=source_key,
        timeout=args.timeout,
    )
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(
            "unsupported snapshot schema_version: "
            f"{snapshot.get('schema_version')!r}"
        )

    print(_summary(snapshot))
    if args.save:
        args.save.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
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
        payload=snapshot,
        timeout=args.timeout,
    )
    print("dry run: no local changes applied" if args.dry_run else "imported")
    for line in _format_result(result):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
