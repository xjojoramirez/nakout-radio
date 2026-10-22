from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import NamedTuple
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.config import get_settings
from app.models import ScheduleSlot, Setting, Genre, TrackCache
from app.routers.genres import (
    ordered_tracks_for_genre,
    save_order,
    tracks_for_genre,
)
from app.scheduler import resolve_genre_id


def utcnow() -> datetime:
    """Naive UTC, matching models._utcnow."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_seed(genre_id: int | None, started_at: datetime) -> str:
    """Stable seed for one automatic genre run.

    Keyed on the genre and the run's start time so that ``_peek_next``, which
    advances a *copy* of the state to the boundary, reproduces the same order
    the committed run will play. Only needs to be stable within the running
    process: the concrete order is persisted in ``broadcast_state``, so the
    seed itself need not be reproducible across versions.
    """
    return f"{genre_id}:{started_at.isoformat()}"


def _rng_factory(seed: str) -> random.Random:
    """Indirection over the RNG so tests can inject a deterministic one."""
    return random.Random(seed)


def _shuffle_pairs(
    ids: list[int], durations: list[int], seed: str
) -> tuple[list[int], list[int]]:
    """Fisher-Yates shuffle of ``(id, duration)`` pairs, kept in lockstep."""
    if len(ids) != len(durations):
        raise ValueError("ids and durations must be the same length")
    pairs = list(zip(ids, durations))
    _rng_factory(seed).shuffle(pairs)
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _avoid_immediate_repeat(
    ids: list[int], durations: list[int], previous_id: int | None
) -> tuple[list[int], list[int]]:
    """Keep a wrapped pass from opening on the track that just finished.

    Swaps the head with position 1 when it still holds ``previous_id``. The
    target position is fixed — no extra randomness is drawn — so the result
    stays a pure function of ``(genre_id, run start time, previous track)`` and
    ``_peek_next`` reproduces the committed order. A one-track genre cannot
    avoid the replay; nothing changes when the head is already fine.
    """
    if previous_id is None or len(ids) < 2 or ids[0] != previous_id:
        return ids, durations
    ids = list(ids)
    durations = list(durations)
    ids[0], ids[1] = ids[1], ids[0]
    durations[0], durations[1] = durations[1], durations[0]
    return ids, durations


def _auto_randomize(
    genre_id: int | None,
    started_at: datetime,
    ids: list[int],
    durations: list[int],
    previous_id: int | None = None,
) -> tuple[list[int], list[int]]:
    """Shuffle one automatic genre run's queue (no-op for < 2 tracks).

    ``previous_id`` is the track that just finished when the queue is rebuilt
    mid-run (a wrap), or ``None`` for a fresh run; it is kept out of the first
    slot so consecutive passes never replay it back-to-back.
    """
    if len(ids) != len(durations):
        raise ValueError("ids and durations must be the same length")
    if len(ids) < 2:
        return list(ids), list(durations)
    ids, durations = _shuffle_pairs(ids, durations, _run_seed(genre_id, started_at))
    return _avoid_immediate_repeat(ids, durations, previous_id)


@dataclass
class BroadcastState:
    genre_id: int | None
    track_ids: list[int]
    durations: list[int]
    index: int
    started_at: datetime
    manual: bool = False


class QueueState(NamedTuple):
    genre_id: int
    track_ids: list[int]
    index: int
    live: bool
    manual: bool


def advance(
    state: BroadcastState,
    now: datetime,
    desired: Callable[[datetime], int | None],
    snapshot: Callable[[int], tuple[list[int], list[int]]],
    gap_seconds: float = 0.0,
    randomize: (
        Callable[
            [int | None, datetime, list[int], list[int], int | None],
            tuple[list[int], list[int]],
        ]
        | None
    ) = None,
) -> BroadcastState:
    """Advance ``state`` forward through finished tracks.

    ``desired(at)`` returns the genre that should be live at time ``at``.
    ``snapshot(genre_id)`` returns that genre's ``(track_ids, durations)``.
    ``randomize(genre_id, started_at, ids, durations, previous_id)``, when
    given, reshuffles the queue each time it is (re)built, including genre
    switches and wraps. ``previous_id`` is the track that just finished (or
    ``None`` on the initial fill), so the hook can keep a wrapped pass from
    replaying it. Each track occupies ``duration + gap_seconds``: the extra
    seconds are a silent interval after the song, before the next one starts.
    Boundary times are evaluated at the boundary itself so the result is
    correct even after a long gap with no requests. Does not mutate the input.
    """
    state = replace(
        state,
        track_ids=list(state.track_ids),
        durations=list(state.durations),
    )
    if not state.track_ids:
        state.index = 0
    elif not 0 <= state.index < len(state.track_ids):
        state.index = 0

    def build(
        genre_id: int, started_at: datetime, previous_id: int | None
    ) -> tuple[list[int], list[int]]:
        ids, durations = snapshot(genre_id)
        if randomize is not None:
            ids, durations = randomize(
                genre_id, started_at, ids, durations, previous_id
            )
        return ids, durations

    if state.manual:
        return _advance_manual(state, now, gap_seconds)

    for _ in range(10000):
        if not state.track_ids:
            target = desired(now)
            if target is None:
                return state
            ids, durations = build(target, now, None)
            if not ids:
                state.genre_id = target
                state.track_ids = []
                state.durations = []
                return state
            state.genre_id = target
            state.track_ids = ids
            state.durations = durations
            state.index = 0
            state.started_at = now
            continue

        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration + gap_seconds)
        if now < end:
            return state

        finished_id = state.track_ids[state.index]
        target = desired(end)
        if target is not None and target != state.genre_id:
            state.genre_id = target
            state.track_ids, state.durations = build(target, end, finished_id)
            state.index = 0
            state.started_at = end
        else:
            state.index += 1
            state.started_at = end
            if state.index >= len(state.track_ids):
                state.index = 0
                state.track_ids, state.durations = build(
                    state.genre_id, end, finished_id
                )
    return state


def _advance_manual(
    state: BroadcastState, now: datetime, gap_seconds: float
) -> BroadcastState:
    for _ in range(10000):
        if not state.track_ids:
            return state
        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration + gap_seconds)
        if now < end:
            return state
        state.index += 1
        state.started_at = end
        if state.index >= len(state.track_ids):
            state.index = 0
    return state


STATE_KEY = "broadcast_state"
_lock = Lock()


class NowState(NamedTuple):
    genre: Genre | None
    track: TrackCache | None
    offset_seconds: int
    source: str
    phase: str = "playing"
    next_track: TrackCache | None = None
    seconds_until_start: float | None = None


def _resolve(session: Session, at_utc: datetime) -> tuple[int | None, bool]:
    settings = get_settings()
    local = at_utc.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo(settings.genre_tz)
    )
    default = session.exec(
        select(Genre).where(Genre.is_default.is_(True))
    ).first()
    slots = session.exec(
        select(ScheduleSlot).order_by(ScheduleSlot.id)
    ).all()
    rows = [(s.genre_id, s.days_of_week, s.start_time) for s in slots]
    matched = any(days for _, days, _ in rows)
    genre_id = resolve_genre_id(rows, local, default.id if default else None)
    return genre_id, matched


def _desired(session: Session, at_utc: datetime) -> int | None:
    genre_id, _ = _resolve(session, at_utc)
    if genre_id is not None and tracks_for_genre(session, genre_id):
        return genre_id
    default = session.exec(
        select(Genre).where(Genre.is_default.is_(True))
    ).first()
    if default is not None and tracks_for_genre(session, default.id):
        return default.id
    return genre_id


def _snapshot(session: Session, genre_id: int) -> tuple[list[int], list[int]]:
    tracks = ordered_tracks_for_genre(session, genre_id)
    return [int(t.id) for t in tracks], [t.duration_seconds or 1 for t in tracks]


def _source(session: Session, state: BroadcastState, now: datetime) -> str:
    if state.manual:
        return "manual"
    resolved_id, matched = _resolve(session, now)
    return "schedule" if (matched and resolved_id == state.genre_id) else "default"


def _load(session: Session) -> BroadcastState | None:
    row = session.get(Setting, STATE_KEY)
    if row is None or not row.value:
        return None
    try:
        data = json.loads(row.value)
        if not isinstance(data, dict):
            return None
        sid = data.get("genre_id")
        genre_id = int(sid) if sid is not None else None
        track_ids = [int(x) for x in data["track_ids"]]
        durations = [int(x) for x in data["durations"]]
        index = int(data["index"])
        started_at = datetime.fromisoformat(data["started_at_utc"])
        manual = bool(data.get("manual", False))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if started_at.tzinfo is not None:
        started_at = started_at.astimezone(timezone.utc).replace(tzinfo=None)
    if len(track_ids) != len(durations):
        return None
    return BroadcastState(
        genre_id=genre_id,
        track_ids=track_ids,
        durations=durations,
        index=index,
        started_at=started_at,
        manual=manual,
    )


def _save(session: Session, state: BroadcastState) -> None:
    payload = json.dumps(
        {
            "genre_id": state.genre_id,
            "track_ids": state.track_ids,
            "durations": state.durations,
            "index": state.index,
            "started_at_utc": state.started_at.isoformat(),
            "manual": state.manual,
        }
    )
    session.merge(Setting(key=STATE_KEY, value=payload))
    session.commit()


def _init(session: Session, now: datetime) -> BroadcastState:
    genre_id = _desired(session, now)
    if genre_id is None:
        return BroadcastState(None, [], [], 0, now)
    ids, durations = _snapshot(session, genre_id)
    ids, durations = _auto_randomize(genre_id, now, ids, durations)
    return BroadcastState(genre_id, ids, durations, 0, now)


def _peek_next(
    session: Session, state: BroadcastState, now: datetime, gap: float
) -> tuple[TrackCache | None, float]:
    """The track that starts after the current one, and seconds until it starts.

    Evaluated at the current track's boundary (track end + gap), which also
    covers schedule genre changes and manual queues.
    """
    duration = state.durations[state.index] or 1
    end = state.started_at + timedelta(seconds=duration + gap)
    following = advance(
        state,
        end,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
        gap,
        randomize=_auto_randomize,
    )
    next_track = None
    if following.genre_id is not None and following.track_ids:
        next_track = session.get(TrackCache, following.track_ids[following.index])
    return next_track, max(0.0, (end - now).total_seconds())


def _advance_run(session: Session, now: datetime) -> BroadcastState:
    """Load (or initialize) the on-air run and advance it to ``now``.

    Saves the run when it was just created or when it moved, matching the
    lazy-advance behaviour of :func:`get_current`.
    """
    state = _load(session)
    initialized = state is None
    if state is None:
        state = _init(session, now)
    before = state
    state = advance(
        state,
        now,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
        get_settings().track_gap_seconds,
        randomize=_auto_randomize,
    )
    if initialized or state != before:
        _save(session, state)
    return state


def live_queue(
    session: Session, genre_id: int, now: datetime | None = None
) -> QueueState:
    """The queue the studio should display for ``genre_id``.

    The on-air genre returns its live (possibly shuffled) order and index; any
    other genre returns the saved order with ``index == -1`` and ``live``
    false, because it is not currently playing.
    """
    now = now or utcnow()
    with _lock:
        state = _advance_run(session, now)
        if state.genre_id == genre_id and state.track_ids:
            return QueueState(
                genre_id,
                list(state.track_ids),
                state.index,
                True,
                state.manual,
            )
        ids, _ = _snapshot(session, genre_id)
        return QueueState(genre_id, ids, -1, False, False)


def get_current(session: Session, now: datetime | None = None) -> NowState:
    now = now or utcnow()
    gap = get_settings().track_gap_seconds
    with _lock:
        state = _advance_run(session, now)

        if state.genre_id is None or not state.track_ids:
            return NowState(None, None, 0, "none")
        track = session.get(TrackCache, state.track_ids[state.index])
        genre = session.get(Genre, state.genre_id)
        if track is None or genre is None:
            if state.manual and state.genre_id is not None:
                ids, durations = _snapshot(session, state.genre_id)
                state = BroadcastState(
                    state.genre_id, ids, durations, 0, now, True
                )
            else:
                state = _init(session, now)
            _save(session, state)
            if state.genre_id is None or not state.track_ids:
                return NowState(None, None, 0, "none")
            track = session.get(TrackCache, state.track_ids[state.index])
            genre = session.get(Genre, state.genre_id)
            if track is None or genre is None:
                return NowState(None, None, 0, "none")
            next_track, until = _peek_next(session, state, now, gap)
            return NowState(
                genre, track, 0, _source(session, state, now), "playing",
                next_track, until,
            )
        duration = state.durations[state.index] or 1
        offset = int((now - state.started_at).total_seconds())
        offset = max(0, min(offset, duration - 1))
        source = _source(session, state, now)
        next_track, until = _peek_next(session, state, now, gap)
        if now >= state.started_at + timedelta(seconds=duration):
            return NowState(
                genre, track, offset, source, "gap", next_track, until
            )
        return NowState(
            genre, track, offset, source, "playing", next_track, until
        )


def _load_and_advance(session: Session, now: datetime) -> BroadcastState:
    state = _load(session)
    if state is None:
        state = _init(session, now)
    return advance(
        state,
        now,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
        get_settings().track_gap_seconds,
        randomize=_auto_randomize,
    )


def _build_manual(
    session: Session, genre_id: int, index: int, now: datetime
) -> BroadcastState:
    ids, durations = _snapshot(session, genre_id)
    return BroadcastState(genre_id, ids, durations, index, now, True)


def play_now(
    session: Session, genre_id: int, video_id: str, now: datetime | None = None
) -> None:
    now = now or utcnow()
    with _lock:
        tracks = ordered_tracks_for_genre(session, genre_id)
        index = next(
            (i for i, t in enumerate(tracks) if t.youtube_video_id == video_id),
            None,
        )
        if index is None:
            raise ValueError("track not found")
        _save(session, _build_manual(session, genre_id, index, now))


def skip(
    session: Session, genre_id: int, direction: str, now: datetime | None = None
) -> None:
    now = now or utcnow()
    with _lock:
        state = _load_and_advance(session, now)
        if state.genre_id != genre_id or not state.track_ids:
            tracks = ordered_tracks_for_genre(session, genre_id)
            if not tracks:
                raise ValueError("genre has no tracks")
            index = 0 if direction == "next" else len(tracks) - 1
            _save(session, _build_manual(session, genre_id, index, now))
            return
        total = len(state.track_ids)
        delta = 1 if direction == "next" else -1
        state.manual = True
        state.index = (state.index + delta) % total
        state.started_at = now
        _save(session, state)


def set_auto(session: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    with _lock:
        state = _init(session, now)
        _save(session, state)


def stop(session: Session, now: datetime | None = None) -> None:
    """Take the station off air until an explicit play/skip/auto resumes it.

    Stored as an empty *manual* state: ``advance`` routes manual states to
    ``_advance_manual``, which returns immediately when there are no tracks, so
    the schedule/default is not re-resolved while stopped.
    """
    now = now or utcnow()
    with _lock:
        _save(session, BroadcastState(None, [], [], 0, now, True))


def set_order(
    session: Session,
    genre_id: int,
    video_ids: list[str],
    now: datetime | None = None,
) -> None:
    """Replace a genre's saved order and apply it to the live run.

    The current track keeps playing at its new index with its elapsed time
    preserved; when it is no longer in the queue, playback restarts at the
    head. Applies to automatic and manual runs alike, so what the studio
    shows is what plays next.
    """
    now = now or utcnow()
    with _lock:
        save_order(session, genre_id, video_ids)
        if _load(session) is None:
            return
        state = _load_and_advance(session, now)
        if state.genre_id != genre_id or not state.track_ids:
            return
        current_id = state.track_ids[state.index]
        ids, durations = _snapshot(session, genre_id)
        if not ids:
            return
        if current_id in ids:
            new_index = ids.index(current_id)
            started_at = state.started_at
        else:
            new_index = 0
            started_at = now
        _save(
            session,
            BroadcastState(
                genre_id, ids, durations, new_index, started_at, state.manual
            ),
        )
