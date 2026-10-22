from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.config import get_settings
from app.models import Genre, ScheduleSlot, TrackCache, TrackPlay
from app.scheduler import next_genre_change

RngFactory = Callable[[str], random.Random]


@dataclass(frozen=True)
class TrackPlayInfo:
    last_played_at: datetime
    last_run_started_at: datetime


@dataclass(frozen=True)
class RotationEntry:
    track_id: int
    duration: int
    video_id: str
    play: TrackPlayInfo | None = None


@dataclass(frozen=True)
class RotationResult:
    entries: list[RotationEntry]
    window_tracks: int
    window_repeat_count: int
    previous_run_started_at: datetime | None

    @property
    def track_ids(self) -> list[int]:
        return [entry.track_id for entry in self.entries]

    @property
    def durations(self) -> list[int]:
        return [entry.duration for entry in self.entries]


def _fresh_group_seed(seed: str, index: int) -> str:
    return seed if index == 0 else f"{seed}:fresh:{index}"


def _repeat_positions(window: int, count: int) -> list[int]:
    """Evenly spaced repeat slots, never at position zero."""
    if count <= 0:
        return []
    positions = {
        max(1, min(window - 1, int((index + 1) * window / (count + 1))))
        for index in range(count)
    }
    while len(positions) < count:
        for candidate in range(1, window):
            if candidate not in positions:
                positions.add(candidate)
                break
    return sorted(positions)[:count]


def build_rotation_order(
    entries: list[RotationEntry],
    *,
    seed: str,
    window_tracks: int,
    repeat_fraction: float = 0.10,
    min_window: int = 5,
    rng_factory: RngFactory = random.Random,
) -> RotationResult:
    """Build one automatic run's order.

    The previous automatic airing's tracks are the repeat pool. Tracks from
    older runs (and tracks that have never aired) form the fresh pool, oldest
    first. The first ``window_tracks`` songs are the estimated airing window:
    when the fresh pool is large enough, at most ``repeat_fraction`` of it
    comes from the previous airing and the repeats are spread out rather than
    clustered. If the fresh pool is smaller than the window, the unavoidable
    repeats follow the fresh tracks. Everything after the window is the rest
    of the fresh pool followed by the rest of the repeat pool.
    """
    unique: list[RotationEntry] = []
    seen: set[str] = set()
    for entry in entries:
        key = entry.video_id or f"track:{entry.track_id}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)

    if not unique:
        return RotationResult([], 0, 0, None)

    window = max(1, min(int(window_tracks), len(unique)))
    history = [entry for entry in unique if entry.play is not None]
    if not history:
        ordered = list(unique)
        rng_factory(seed).shuffle(ordered)
        return RotationResult(ordered, window, 0, None)

    previous_run = max(
        entry.play.last_run_started_at
        for entry in history
        if entry.play is not None
    )
    repeat_pool = [
        entry
        for entry in unique
        if entry.play is not None
        and entry.play.last_run_started_at == previous_run
    ]
    repeat_ids = {entry.track_id for entry in repeat_pool}
    fresh_pool = [entry for entry in unique if entry.track_id not in repeat_ids]

    if not fresh_pool:
        # A full pass has just finished: every track is a repeat. Reshuffle the
        # whole pass, matching the old wrap behaviour.
        ordered = list(unique)
        rng_factory(seed).shuffle(ordered)
        return RotationResult(ordered, window, len(ordered), previous_run)

    groups: dict[datetime | None, list[RotationEntry]] = {}
    for entry in fresh_pool:
        key = entry.play.last_run_started_at if entry.play is not None else None
        groups.setdefault(key, []).append(entry)

    ordered_fresh: list[RotationEntry] = []
    group_keys = sorted(
        groups,
        key=lambda key: (key is not None, key or datetime.min),
    )
    for index, key in enumerate(group_keys):
        group = groups[key]
        rng_factory(_fresh_group_seed(seed, index)).shuffle(group)
        ordered_fresh.extend(group)

    budget = 0
    if repeat_pool and window >= min_window and repeat_fraction > 0:
        budget = max(1, int(window * repeat_fraction))
    budget = min(
        budget,
        len(repeat_pool),
        max(0, window - 1),
    )
    fresh_window = min(len(ordered_fresh), window - budget)
    repeat_count = min(len(repeat_pool), window - fresh_window)

    selected_repeats: list[RotationEntry] = []
    if repeat_count:
        selected_repeats = sorted(
            repeat_pool,
            key=lambda entry: entry.play.last_played_at
            if entry.play is not None
            else datetime.min,
        )[:repeat_count]
        rng_factory(f"{seed}:repeat-pick").shuffle(selected_repeats)

    fresh_selected = ordered_fresh[:fresh_window]
    window_entries: list[RotationEntry] = []
    if not selected_repeats:
        window_entries = fresh_selected
    elif fresh_window < window - budget:
        # The fresh pool cannot fill the non-repeat part of the window. Keep
        # all fresh tracks first and let the unavoidable repeats follow them.
        window_entries = fresh_selected + selected_repeats
    else:
        position_set = set(_repeat_positions(window, len(selected_repeats)))
        fresh_index = 0
        repeat_index = 0
        for position in range(window):
            if position in position_set and repeat_index < len(selected_repeats):
                window_entries.append(selected_repeats[repeat_index])
                repeat_index += 1
            elif fresh_index < len(fresh_selected):
                window_entries.append(fresh_selected[fresh_index])
                fresh_index += 1
            elif repeat_index < len(selected_repeats):
                window_entries.append(selected_repeats[repeat_index])
                repeat_index += 1
        while len(window_entries) < window and fresh_index < len(fresh_selected):
            window_entries.append(fresh_selected[fresh_index])
            fresh_index += 1
        while len(window_entries) < window and repeat_index < len(selected_repeats):
            window_entries.append(selected_repeats[repeat_index])
            repeat_index += 1

    selected_ids = {entry.track_id for entry in selected_repeats}
    tail_repeats = sorted(
        (entry for entry in repeat_pool if entry.track_id not in selected_ids),
        key=lambda entry: entry.play.last_played_at
        if entry.play is not None
        else datetime.min,
    )
    tail_fresh = ordered_fresh[fresh_window:]
    ordered = window_entries + tail_fresh + tail_repeats
    return RotationResult(
        ordered,
        window,
        repeat_count,
        previous_run,
    )


def record_play(
    session: Session,
    genre_id: int,
    video_id: str,
    played_at: datetime,
    run_started_at: datetime,
) -> None:
    """Record one automatic airing, updating the latest row for the video."""
    row = session.exec(
        select(TrackPlay).where(
            TrackPlay.genre_id == genre_id,
            TrackPlay.video_id == video_id,
        )
    ).first()
    if row is None:
        row = TrackPlay(
            genre_id=genre_id,
            video_id=video_id,
            last_played_at=played_at,
            last_run_started_at=run_started_at,
            play_count=1,
        )
    else:
        row.last_played_at = played_at
        row.last_run_started_at = run_started_at
        row.play_count += 1
    session.add(row)


def genre_has_history(session: Session, genre_id: int) -> bool:
    return (
        session.exec(
            select(TrackPlay.genre_id)
            .where(TrackPlay.genre_id == genre_id)
            .limit(1)
        ).first()
        is not None
    )


def rotation_entries(
    session: Session,
    genre_id: int,
    ids: list[int],
    durations: list[int],
) -> list[RotationEntry]:
    if not ids:
        return []
    video_rows = session.exec(
        select(TrackCache.id, TrackCache.youtube_video_id).where(
            TrackCache.id.in_(ids)
        )
    ).all()
    video_by_id = {int(track_id): str(video_id) for track_id, video_id in video_rows}
    plays = session.exec(
        select(TrackPlay).where(TrackPlay.genre_id == genre_id)
    ).all()
    play_by_video = {
        play.video_id: TrackPlayInfo(
            play.last_played_at,
            play.last_run_started_at,
        )
        for play in plays
    }
    entries: list[RotationEntry] = []
    for track_id, duration in zip(ids, durations):
        video_id = video_by_id.get(int(track_id), "")
        entries.append(
            RotationEntry(
                track_id=int(track_id),
                duration=int(duration),
                video_id=video_id,
                play=play_by_video.get(video_id) if video_id else None,
            )
        )
    return entries


def estimate_window_tracks(
    session: Session,
    genre_id: int,
    at_utc: datetime,
    durations: list[int],
) -> int:
    """How many songs fit before the next scheduled genre switch."""
    if not durations:
        return 0
    settings = get_settings()
    average = sum(duration or 1 for duration in durations) / len(durations)
    aware = (
        at_utc
        if at_utc.tzinfo is not None
        else at_utc.replace(tzinfo=timezone.utc)
    )
    local = aware.astimezone(ZoneInfo(settings.genre_tz))
    default = session.exec(
        select(Genre).where(Genre.is_default.is_(True))
    ).first()
    slots = session.exec(select(ScheduleSlot).order_by(ScheduleSlot.id)).all()
    rows = [
        (slot.genre_id, slot.days_of_week, slot.start_time) for slot in slots
    ]
    change = next_genre_change(
        rows,
        local,
        genre_id,
        default.id if default is not None else None,
    )
    if change is None:
        target = settings.rotation_fallback_window
    else:
        seconds = max(0.0, (change - local).total_seconds())
        target = int(seconds / max(average, 1.0))
    return max(1, min(target, len(durations)))
