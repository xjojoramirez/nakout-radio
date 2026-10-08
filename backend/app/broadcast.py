from __future__ import annotations

import json
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


@dataclass
class BroadcastState:
    genre_id: int | None
    track_ids: list[int]
    durations: list[int]
    index: int
    started_at: datetime
    manual: bool = False


def advance(
    state: BroadcastState,
    now: datetime,
    desired: Callable[[datetime], int | None],
    snapshot: Callable[[int], tuple[list[int], list[int]]],
) -> BroadcastState:
    """Advance ``state`` forward through finished tracks.

    ``desired(at)`` returns the genre that should be live at time ``at``.
    ``snapshot(genre_id)`` returns that genre's ``(track_ids, durations)``.
    Boundary times are evaluated at the boundary itself so the result is correct
    even after a long gap with no requests. Does not mutate the input.
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

    if state.manual:
        return _advance_manual(state, now)

    for _ in range(10000):
        if not state.track_ids:
            target = desired(now)
            if target is None:
                return state
            ids, durations = snapshot(target)
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
        end = state.started_at + timedelta(seconds=duration)
        if now < end:
            return state

        target = desired(end)
        if target is not None and target != state.genre_id:
            state.genre_id = target
            state.track_ids, state.durations = snapshot(target)
            state.index = 0
            state.started_at = end
        else:
            state.index += 1
            state.started_at = end
            if state.index >= len(state.track_ids):
                state.index = 0
                state.track_ids, state.durations = snapshot(state.genre_id)
    return state


def _advance_manual(state: BroadcastState, now: datetime) -> BroadcastState:
    for _ in range(10000):
        if not state.track_ids:
            return state
        duration = state.durations[state.index] or 1
        end = state.started_at + timedelta(seconds=duration)
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
    return BroadcastState(genre_id, ids, durations, 0, now)


def get_current(session: Session, now: datetime | None = None) -> NowState:
    now = now or utcnow()
    with _lock:
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
        )
        if initialized or state != before:
            _save(session, state)

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
            return NowState(genre, track, 0, _source(session, state, now))
        duration = state.durations[state.index] or 1
        offset = int((now - state.started_at).total_seconds())
        offset = max(0, min(offset, duration - 1))
        return NowState(genre, track, offset, _source(session, state, now))


def _load_and_advance(session: Session, now: datetime) -> BroadcastState:
    state = _load(session)
    if state is None:
        state = _init(session, now)
    return advance(
        state,
        now,
        lambda at: _desired(session, at),
        lambda sid: _snapshot(session, sid),
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
    now = now or utcnow()
    with _lock:
        save_order(session, genre_id, video_ids)
        state = _load_and_advance(session, now)
        if not state.manual or state.genre_id != genre_id:
            return
        current_id = state.track_ids[state.index] if state.track_ids else None
        ids, durations = _snapshot(session, genre_id)
        if not ids:
            return
        started_at = state.started_at
        if current_id is not None:
            try:
                new_index = ids.index(current_id)
            except ValueError:
                new_index = 0
                started_at = now
        else:
            new_index = 0
            started_at = now
        _save(
            session,
            BroadcastState(genre_id, ids, durations, new_index, started_at, True),
        )
