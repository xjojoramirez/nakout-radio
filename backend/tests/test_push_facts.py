"""Tests for the reviewed-facts push bridge."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "push_facts.py"
_spec = importlib.util.spec_from_file_location("push_facts", SCRIPT)
assert _spec is not None and _spec.loader is not None
push_facts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(push_facts)


def _track(video_id: str = "abc123", **detail) -> dict:
    return {
        "youtube_video_id": video_id,
        "title": "Song",
        "artist": "Artist",
        "thumbnail_url": "",
        "duration_seconds": 200,
        "gain_db": None,
        "playlists": [],
        "detail": detail,
    }


def test_only_locked_local_facts_are_overlaid() -> None:
    live = _track(
        album="Old Album",
        release_year=1999,
        summary="Live summary",
        story="Live story",
        charts=[{"chart_name": "Test", "peak": 1}],
        sources={"summary": {"provider": "wikipedia", "url": "live"}},
        locked_fields=["summary"],
    )
    local = _track(
        album="New Album",
        release_year=2000,
        summary="Local summary",
        story="Local story",
        charts=[],
        sources={"album": {"provider": "wikipedia", "url": "local"}},
        locked_fields=["album", "summary", "story"],
    )

    track, diffs, skipped = push_facts.build_track(live, local)

    assert track is not None
    detail = track["detail"]
    assert detail["album"] == "New Album"
    assert detail["release_year"] == 1999  # not locked locally
    assert detail["summary"] == "Live summary"
    assert detail["story"] == "Live story"
    assert detail["charts"] == [{"chart_name": "Test", "peak": 1}]
    assert detail["locked_fields"] == ["summary", "album"]
    assert detail["sources"]["album"]["url"] == "local"
    assert detail["sources"]["summary"]["url"] == "live"
    assert track["playlists"] == []
    assert diffs == [("album", "Old Album", "New Album")]
    assert skipped == []


def test_live_lock_keeps_the_live_value() -> None:
    live = _track(
        album="Live Album",
        label="Live Label",
        sources={},
        locked_fields=["label"],
    )
    local = _track(
        album="Local Album",
        label="Local Label",
        sources={
            "album": {"provider": "wikipedia", "url": "album"},
            "label": {"provider": "wikipedia", "url": "label"},
        },
        locked_fields=["album", "label"],
    )

    track, diffs, skipped = push_facts.build_track(live, local)

    assert track is not None
    assert track["detail"]["album"] == "Local Album"
    assert track["detail"]["label"] == "Live Label"
    assert "label: live field is locked" in skipped
    assert diffs == [("album", "Live Album", "Local Album")]


def test_unlocked_local_fact_is_not_pushed() -> None:
    live = _track(album="Live Album", sources={}, locked_fields=[])
    local = _track(
        album="Local Album",
        sources={"album": {"provider": "wikipedia", "url": "album"}},
        locked_fields=[],
    )

    track, diffs, skipped = push_facts.build_track(live, local)

    assert track is None
    assert diffs == []
    assert skipped == ["no locked fact fields locally"]


def test_locked_fact_without_a_source_is_skipped() -> None:
    live = _track(album="Live Album", sources={}, locked_fields=[])
    local = _track(album="Local Album", sources={}, locked_fields=["album"])

    track, diffs, skipped = push_facts.build_track(live, local)

    assert track is None
    assert diffs == []
    assert skipped == ["album: no local source"]


def test_playlist_free_payload_and_missing_tracks_are_reported() -> None:
    local = {"schema_version": 1, "playlists": [], "tracks": [_track()]}
    local["tracks"][0]["detail"]["album"] = "Local Album"
    local["tracks"][0]["detail"]["sources"] = {
        "album": {"provider": "wikipedia", "url": "album"}
    }
    local["tracks"][0]["detail"]["locked_fields"] = ["album"]
    live = {
        "schema_version": 1,
        "playlists": [],
        "tracks": [
            _track(album="Live Album", sources={}, locked_fields=[])
        ],
    }

    payload, report, skipped = push_facts.build_payload(
        local, live, ["abc123", "missing"]
    )

    assert payload["playlists"] == []
    assert len(payload["tracks"]) == 1
    assert payload["tracks"][0]["playlists"] == []
    assert len(report) == 1
    assert skipped == ["missing: not found locally"]


def test_load_ids_from_flags_file_comments_and_commas(tmp_path: Path) -> None:
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text(
        "# reviewed\nabc123\n\ndef456, ghi789\nabc123\n",
        encoding="utf-8",
    )

    ids = push_facts.load_ids(["first1"], ids_file)

    assert ids == ["first1", "abc123", "def456", "ghi789"]
