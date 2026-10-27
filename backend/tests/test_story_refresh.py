"""Maintenance refresh for provider-written story prose."""

from sqlmodel import Session, SQLModel, create_engine

from app import story_refresh
from app.models import TrackDetail


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/story-refresh.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _source(provider: str = "wikipedia") -> dict:
    return {
        "provider": provider,
        "url": "https://en.wikipedia.org/wiki/Test",
        "fetched_at": "2020-01-01",
    }


def test_provider_prose_ids_only_selects_unlocked_wikipedia(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                summary="Wikipedia summary",
                sources={"summary": _source()},
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="v2",
                story="Deezer text",
                sources={"story": _source("deezer")},
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="v3",
                story="Locked Wikipedia text",
                sources={"story": _source()},
                locked_fields=["story"],
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="v4",
                story="Wikipedia story",
                sources={"story": _source()},
            )
        )
        session.commit()

        assert story_refresh.provider_prose_ids(session) == ["v1", "v4"]


def test_provider_prose_ids_can_limit_to_overlong_rows(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="long-summary",
                summary="x" * 300,
                sources={"summary": _source()},
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="short-summary",
                summary="Short enough.",
                sources={"summary": _source()},
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="long-story",
                story="x" * 500,
                sources={"story": _source()},
            )
        )
        session.add(
            TrackDetail(
                youtube_video_id="locked-story",
                story="x" * 500,
                sources={"story": _source()},
                locked_fields=["story"],
            )
        )
        session.commit()

        assert story_refresh.provider_prose_ids(
            session, only_long=True
        ) == ["long-story", "long-summary"]


def test_main_dry_run_lists_tracks(tmp_path, monkeypatch, capsys):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            TrackDetail(
                youtube_video_id="v1",
                story="Wikipedia story",
                sources={"story": _source()},
            )
        )
        session.commit()

    monkeypatch.setattr(story_refresh, "engine", engine)

    assert story_refresh.main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "v1" in output
    assert "would refresh 1 tracks" in output
