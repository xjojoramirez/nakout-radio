"""Agent composer: fill-only facts, curated prose, and the detail_tools CLI."""

import json

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.composer import compose_detail, infer_provider
from app.enrichment.base import ProviderData
from app.enrichment.pipeline import enrich_story, enrich_track
from app.models import (
    Genre,
    Playlist,
    TrackCache,
    TrackDetail,
)

PAGE_URL = "https://en.wikipedia.org/wiki/Kind_of_Blue"
MB_URL = "https://musicbrainz.org/release/abc"
STORY = (
    "Miles Davis wrote the piece with Bill Evans in 1959, sketching the "
    "harmonic frame during the Kind of Blue sessions at Columbia's 30th "
    "Street Studio."
)
SUMMARY = "A modal jazz ballad from Miles Davis's 1959 album Kind of Blue."


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/composer.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        genre = Genre(name="Jazz", slug="jazz", is_default=True)
        session.add(genre)
        session.commit()
        session.refresh(genre)
        playlist = Playlist(genre_id=genre.id, youtube_playlist_id="PL1")
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
        session.add(
            TrackCache(
                playlist_id=playlist.id,
                youtube_video_id="v1",
                title="Blue in Green",
                artist="Miles Davis",
                thumbnail_url="",
                duration_seconds=300,
            )
        )
        session.commit()
    return engine


def test_compose_fills_empty_facts_and_locks_them(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                story="An auto article dump that the composer should replace.",
                sources={
                    "story": {
                        "provider": "wikipedia",
                        "url": PAGE_URL,
                        "fetched_at": "2020-01-01",
                    }
                },
            )
        )
        session.commit()

        result = compose_detail(
            session,
            "v1",
            story=STORY,
            album="Kind of Blue",
            release_year=1959,
            label="Columbia",
            isrc="us-sm7-59-00001",
            credits=[{"role": "Producer", "name": "Irving Townsend"}],
            source_url=PAGE_URL,
        )
        row = session.get(TrackDetail, "v1")

    assert result is not None
    assert {change.field for change in result.changes} == {
        "story",
        "album",
        "release_year",
        "label",
        "isrc",
        "credits",
    }
    assert row.story == STORY
    assert row.album == "Kind of Blue"
    assert row.release_year == 1959
    assert row.label == "Columbia"
    assert row.isrc == "USSM75900001"
    assert row.credits == [{"role": "Producer", "name": "Irving Townsend"}]
    assert set(row.locked_fields) == {
        "story",
        "album",
        "release_year",
        "label",
        "isrc",
        "credits",
    }
    assert row.sources["album"] == {
        "provider": "wikipedia",
        "url": PAGE_URL,
        "fetched_at": row.sources["album"]["fetched_at"],
    }
    assert row.sources["story"]["url"] == PAGE_URL
    assert row.story_at is not None
    assert result.detail is not None
    assert result.detail.album == "Kind of Blue"


def test_compose_skips_manual_prose_and_existing_facts(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                album="Kind of Blue",
                summary="A hand-written summary.",
                story="Old auto text",
                sources={
                    "story": {
                        "provider": "wikipedia",
                        "url": PAGE_URL,
                        "fetched_at": "2020-01-01",
                    }
                },
            )
        )
        session.commit()

        result = compose_detail(
            session,
            "v1",
            summary=SUMMARY,
            story=STORY,
            album="Kind of Blue (Legacy Edition)",
            source_url=PAGE_URL,
        )
        row = session.get(TrackDetail, "v1")

    assert result is not None
    assert [change.field for change in result.changes] == ["story"]
    assert row.story == STORY
    assert row.summary == "A hand-written summary."
    assert row.album == "Kind of Blue"
    skipped = {skip.field: skip for skip in result.skipped}
    assert skipped["summary"].reason == "manual prose"
    assert skipped["album"].reason == "already set"
    assert skipped["album"].current == "Kind of Blue"


def test_compose_skips_locked_fields(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                story="Curated by a human.",
                album="Kind of Blue",
                locked_fields=["story", "album"],
            )
        )
        session.commit()

        result = compose_detail(
            session,
            "v1",
            story=STORY,
            album="Kind of Blue",
            source_url=PAGE_URL,
        )
        row = session.get(TrackDetail, "v1")

    assert result is not None
    assert result.changes == []
    assert {skip.field: skip.reason for skip in result.skipped} == {
        "story": "locked",
        "album": "locked",
    }
    assert row.story == "Curated by a human."


def test_compose_summary_only_does_not_mark_the_story_checked(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        result = compose_detail(
            session, "v1", summary=SUMMARY, source_url=PAGE_URL
        )
        row = session.get(TrackDetail, "v1")

    assert result is not None
    assert [change.field for change in result.changes] == ["summary"]
    assert row.summary == SUMMARY
    assert row.story_at is None
    assert "summary" in row.locked_fields


def test_compose_dry_run_writes_nothing(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        result = compose_detail(
            session,
            "v1",
            story=STORY,
            album="Kind of Blue",
            source_url=PAGE_URL,
            dry_run=True,
        )

        assert result is not None
        assert result.dry_run is True
        assert {change.field for change in result.changes} == {"story", "album"}
        assert result.detail is None
        assert session.get(TrackDetail, "v1") is None


def test_compose_rejects_unknown_track(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        assert (
            compose_detail(session, "missing", album="x", source_url=PAGE_URL)
            is None
        )


def test_compose_requires_evidence_url(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="source URL"):
            compose_detail(session, "v1", album="Kind of Blue", source_url="")
        with pytest.raises(ValueError, match="source URL"):
            compose_detail(
                session, "v1", album="Kind of Blue", source_url="not-a-url"
            )


def test_compose_validates_prose_and_isrc(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="story"):
            compose_detail(session, "v1", story="too short", source_url=PAGE_URL)
        with pytest.raises(ValueError, match="story"):
            compose_detail(session, "v1", story="x" * 401, source_url=PAGE_URL)
        with pytest.raises(ValueError, match="summary"):
            compose_detail(session, "v1", summary="x" * 221, source_url=PAGE_URL)
        with pytest.raises(ValueError, match="ISRC"):
            compose_detail(session, "v1", isrc="NOPE", source_url=PAGE_URL)
        with pytest.raises(ValueError, match="at least one"):
            compose_detail(session, "v1", source_url=PAGE_URL)
        with pytest.raises(ValueError, match="credit"):
            compose_detail(
                session,
                "v1",
                credits=[{"role": "", "name": "Irving Townsend"}],
                source_url=PAGE_URL,
            )


def test_compose_credits_only_fill_empty_lists(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                credits=[{"role": "Producer", "name": "Irving Townsend"}],
            )
        )
        session.commit()

        result = compose_detail(
            session,
            "v1",
            credits=[{"role": "Engineer", "name": "Fred Plaut"}],
            source_url=MB_URL,
        )
        row = session.get(TrackDetail, "v1")

    assert result is not None
    assert result.changes == []
    assert result.skipped[0].field == "credits"
    assert result.skipped[0].reason == "already set"
    assert row.credits == [{"role": "Producer", "name": "Irving Townsend"}]


def test_enrichment_cannot_overwrite_composed_fields(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        compose_detail(
            session,
            "v1",
            story=STORY,
            album="Kind of Blue",
            source_url=PAGE_URL,
        )

        enrich_track(
            session,
            "v1",
            force=True,
            client=object(),
            deezer=lambda *_: ProviderData(
                provider="deezer",
                url="https://deezer/track/1",
                fields={"album": "Wrong Album", "label": "Wrong Label"},
            ),
            musicbrainz=None,
        )
        enrich_story(
            session,
            "v1",
            force=True,
            client=object(),
            wikipedia=lambda *_: _wiki(story="Auto story", summary="Auto summary"),
        )
        row = session.get(TrackDetail, "v1")

    assert row.album == "Kind of Blue"
    assert row.story == STORY
    assert row.story_at is not None


def test_infer_provider():
    assert infer_provider(PAGE_URL) == "wikipedia"
    assert infer_provider(MB_URL) == "musicbrainz"
    assert infer_provider("https://api.deezer.com/track/1") == "deezer"
    assert infer_provider("https://example.com/song") == "editor"
    assert infer_provider("https://notwikipedia.org/song") == "editor"


def test_detail_tools_find_and_show(tmp_path, monkeypatch, capsys):
    from app import detail_tools

    engine = _engine(tmp_path)
    monkeypatch.setattr(detail_tools, "engine", engine)
    with Session(engine) as session:
        session.add(TrackDetail(youtube_video_id="v1", album="Kind of Blue"))
        session.commit()

    assert detail_tools.main(["find", "miles"]) == 0
    matches = json.loads(capsys.readouterr().out)
    assert matches[0]["youtube_video_id"] == "v1"
    assert matches[0]["album"] == "Kind of Blue"

    assert detail_tools.main(["show", "v1"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["album"] == "Kind of Blue"
    assert shown["title"] == "Blue in Green"

    assert detail_tools.main(["show", "missing"]) == 1


def test_detail_tools_apply_and_dry_run(tmp_path, monkeypatch, capsys):
    from app import detail_tools

    engine = _engine(tmp_path)
    monkeypatch.setattr(detail_tools, "engine", engine)

    code = detail_tools.main(
        [
            "apply",
            "v1",
            "--source-url",
            PAGE_URL,
            "--story",
            STORY,
            "--album",
            "Kind of Blue",
            "--credit",
            "Producer=Irving Townsend",
            "--dry-run",
        ]
    )
    assert code == 0
    assert "would apply" in capsys.readouterr().out
    with Session(engine) as session:
        assert session.get(TrackDetail, "v1") is None

    code = detail_tools.main(
        [
            "apply",
            "v1",
            "--source-url",
            PAGE_URL,
            "--story",
            STORY,
            "--album",
            "Kind of Blue",
            "--credit",
            "Producer=Irving Townsend",
        ]
    )
    assert code == 0
    assert "applied" in capsys.readouterr().out
    with Session(engine) as session:
        row = session.get(TrackDetail, "v1")
        assert row.story == STORY
        assert row.album == "Kind of Blue"
        assert row.credits == [{"role": "Producer", "name": "Irving Townsend"}]
        assert "album" in row.locked_fields


def test_detail_tools_apply_errors(tmp_path, monkeypatch, capsys):
    from app import detail_tools

    engine = _engine(tmp_path)
    monkeypatch.setattr(detail_tools, "engine", engine)

    assert (
        detail_tools.main(
            ["apply", "v1", "--source-url", PAGE_URL, "--story", "too short"]
        )
        == 2
    )
    assert "error" in capsys.readouterr().err
    assert (
        detail_tools.main(
            ["apply", "missing", "--source-url", PAGE_URL, "--album", "Kind of Blue"]
        )
        == 1
    )
    assert "not found" in capsys.readouterr().err


def _wiki(**overrides):
    from app.enrichment.wikipedia import WikipediaData

    data = WikipediaData(
        title="Blue in Green",
        url=PAGE_URL,
        summary="A jazz ballad.",
        story="Auto story",
        charts=[],
        confidence="exact",
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data
