from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Genre, Playlist, ScheduleSlot, TrackCache, TrackPlay
from app.rotation import (
    RotationEntry,
    TrackPlayInfo,
    build_rotation_order,
    estimate_window_tracks,
    genre_has_history,
    record_play,
    rotation_entries,
)

START = datetime(2026, 1, 1, 0, 0, 0)
TZ = ZoneInfo("Asia/Manila")


class KeepOrderRng:
    def shuffle(self, seq):
        return None


class ReverseRng:
    def shuffle(self, seq):
        seq.reverse()


def _entry(
    track_id: int,
    *,
    video: str | None = None,
    run_start: datetime | None = None,
    played_at: datetime | None = None,
    duration: int = 100,
) -> RotationEntry:
    play = (
        TrackPlayInfo(
            last_played_at=played_at or run_start,
            last_run_started_at=run_start,
        )
        if run_start is not None
        else None
    )
    return RotationEntry(
        track_id=track_id,
        duration=duration,
        video_id=video or f"v{track_id}",
        play=play,
    )


def test_no_history_shuffles_the_whole_genre():
    entries = [_entry(index) for index in range(5)]
    result = build_rotation_order(
        entries,
        seed="seed",
        window_tracks=10,
        rng_factory=lambda seed: ReverseRng(),
    )
    assert result.track_ids == [4, 3, 2, 1, 0]
    assert result.window_tracks == 5
    assert result.window_repeat_count == 0
    assert result.previous_run_started_at is None


def test_previous_airing_repeats_are_budgeted_and_spread():
    previous = [
        _entry(
            index,
            run_start=START,
            played_at=START + timedelta(seconds=index),
        )
        for index in range(10)
    ]
    fresh = [_entry(index) for index in range(10, 20)]
    result = build_rotation_order(
        previous + fresh,
        seed="seed",
        window_tracks=10,
        repeat_fraction=0.10,
        min_window=5,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    # 10% of a 10-song window is one repeat: the song that played earliest in
    # the previous airing.
    assert result.window_repeat_count == 1
    assert result.track_ids[0] == 10
    assert result.track_ids[5] == 0  # roughly the middle
    assert len([entry for entry in result.track_ids[:10] if entry < 10]) == 1
    # The other nine previous-airing songs stay after all fresh songs.
    assert set(result.track_ids[10:]) == set(range(1, 10)) | {19}
    assert result.track_ids[-9:] == list(range(1, 10))


def test_repeat_budget_is_about_ten_percent_of_the_window():
    previous = [
        _entry(
            index,
            run_start=START,
            played_at=START + timedelta(seconds=index),
        )
        for index in range(30)
    ]
    fresh = [_entry(index) for index in range(30, 130)]
    result = build_rotation_order(
        previous + fresh,
        seed="seed",
        window_tracks=30,
        repeat_fraction=0.10,
        min_window=5,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    assert result.window_repeat_count == 3
    repeats = [entry for entry in result.track_ids[:30] if entry < 30]
    assert repeats == [0, 1, 2]
    assert result.track_ids[0] >= 30
    assert result.track_ids.count(0) == 1


def test_short_window_keeps_the_unavoidable_repeats_last():
    entries = [
        _entry(0, run_start=START, played_at=START),
        _entry(1, run_start=START, played_at=START + timedelta(seconds=1)),
        _entry(2),
    ]
    result = build_rotation_order(
        entries,
        seed="seed",
        window_tracks=4,
        repeat_fraction=0.10,
        min_window=5,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    # The whole genre fits in the window, so there is no fresh pool left to
    # fill it with; the fresh song still opens the queue.
    assert result.track_ids == [2, 0, 1]
    assert result.window_repeat_count == 2


def test_zero_repeat_fraction_disables_the_guard():
    entries = [
        _entry(0, run_start=START, played_at=START),
        _entry(1),
        _entry(2),
        _entry(3),
    ]
    result = build_rotation_order(
        entries,
        seed="seed",
        window_tracks=2,
        repeat_fraction=0.0,
        min_window=1,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    assert result.window_repeat_count == 0
    assert result.track_ids == [1, 2, 3, 0]


def test_full_pass_reshuffles_everything():
    entries = [
        _entry(index, run_start=START, played_at=START + timedelta(seconds=index))
        for index in range(4)
    ]
    result = build_rotation_order(
        entries,
        seed="seed",
        window_tracks=4,
        rng_factory=lambda seed: ReverseRng(),
    )
    assert result.track_ids == [3, 2, 1, 0]
    assert result.window_repeat_count == 4


def test_small_fresh_pool_fills_the_window_with_repeats():
    previous = [
        _entry(index, run_start=START, played_at=START + timedelta(seconds=index))
        for index in range(8)
    ]
    fresh = [_entry(8), _entry(9)]
    result = build_rotation_order(
        previous + fresh,
        seed="seed",
        window_tracks=6,
        repeat_fraction=0.10,
        min_window=5,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    assert result.track_ids[:6] == [8, 9, 0, 1, 2, 3]
    assert result.track_ids[6:] == [4, 5, 6, 7]
    assert result.window_repeat_count == 4


def test_duplicate_videos_appear_once():
    entries = [
        _entry(0, video="same"),
        _entry(1, video="same"),
        _entry(2, video="other"),
    ]
    result = build_rotation_order(
        entries,
        seed="seed",
        window_tracks=3,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    assert result.track_ids == [0, 2]


def test_older_runs_come_before_the_previous_airing():
    entries = [
        _entry(0, run_start=START + timedelta(days=2), played_at=START + timedelta(days=2)),
        _entry(1, run_start=START, played_at=START),
        _entry(2),
    ]
    result = build_rotation_order(
        entries,
        seed="seed",
        window_tracks=3,
        repeat_fraction=0.0,
        min_window=1,
        rng_factory=lambda seed: KeepOrderRng(),
    )
    # Never played, then the older run; the most recent run is last.
    assert result.track_ids == [2, 1, 0]


def test_seed_is_deterministic():
    entries = [_entry(index) for index in range(20)]
    first = build_rotation_order(entries, seed="same", window_tracks=10)
    again = build_rotation_order(entries, seed="same", window_tracks=10)
    assert first.track_ids == again.track_ids


def _engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/rotation.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_genre(session, slug, videos, default=False):
    genre = Genre(name=slug.title(), slug=slug, is_default=default)
    session.add(genre)
    session.commit()
    session.refresh(genre)
    playlist = Playlist(genre_id=genre.id, youtube_playlist_id=f"PL-{slug}")
    session.add(playlist)
    session.commit()
    session.refresh(playlist)
    tracks = []
    for position, video in enumerate(videos):
        track = TrackCache(
            playlist_id=playlist.id,
            youtube_video_id=video,
            title=video,
            artist="A",
            position=position,
            duration_seconds=100,
        )
        session.add(track)
        tracks.append(track)
    session.commit()
    for track in tracks:
        session.refresh(track)
    return genre, tracks


def test_record_play_upserts_by_video_id(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        genre, _ = _seed_genre(session, "rock", ["a"])
        record_play(session, genre.id, "a", START, START)
        record_play(
            session, genre.id, "a", START + timedelta(seconds=5), START
        )
        session.commit()
        rows = session.exec(select(TrackPlay)).all()
        assert len(rows) == 1
        assert rows[0].play_count == 2
        assert rows[0].last_played_at == START + timedelta(seconds=5)


def test_rotation_entries_map_current_track_ids_to_history(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        genre, tracks = _seed_genre(session, "rock", ["a", "b"])
        record_play(session, genre.id, "a", START, START)
        session.commit()
        entries = rotation_entries(
            session,
            genre.id,
            [track.id for track in tracks],
            [100, 100],
        )
        assert [entry.track_id for entry in entries] == [
            track.id for track in tracks
        ]
        assert entries[0].play is not None
        assert entries[0].play.last_run_started_at == START
        assert entries[1].play is None


def test_genre_has_history(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        genre, _ = _seed_genre(session, "rock", ["a"])
        assert genre_has_history(session, genre.id) is False
        record_play(session, genre.id, "a", START, START)
        session.commit()
        assert genre_has_history(session, genre.id) is True


def test_estimate_window_uses_the_next_schedule_change(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        current, tracks = _seed_genre(
            session, "current", [f"a{index}" for index in range(40)], default=True
        )
        other, _ = _seed_genre(session, "other", ["b"])
        session.add(
            ScheduleSlot(
                genre_id=other.id,
                days_of_week=[0],  # Monday
                start_time="09:00",
            )
        )
        session.commit()
        # Monday 08:00 in Manila.
        local_now = datetime(2026, 1, 5, 8, 0, tzinfo=TZ)
        at_utc = local_now.astimezone(timezone.utc).replace(tzinfo=None)
        window = estimate_window_tracks(
            session,
            current.id,
            at_utc,
            [100 for _ in tracks],
        )
        assert window == 36  # one hour / 100 seconds


def test_estimate_window_falls_back_without_a_change(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        current, tracks = _seed_genre(session, "current", ["a"], default=True)
        local_now = datetime(2026, 1, 5, 8, 0, tzinfo=TZ)
        at_utc = local_now.astimezone(timezone.utc).replace(tzinfo=None)
        window = estimate_window_tracks(
            session,
            current.id,
            at_utc,
            [100 for _ in tracks],
        )
        assert window == 1  # fallback 20 capped by one track
