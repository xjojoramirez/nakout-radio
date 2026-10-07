import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import Playlist, Setting, Genre, TrackCache
from app.queue import encode_cursor
from app.schemas import GenreDetail, GenreOut, TrackOut

router = APIRouter(prefix="/api/genres", tags=["genres"])

ORDER_KEY_PREFIX = "genre_order:"


def load_order(session: Session, genre_id: int) -> list[str]:
    row = session.get(Setting, f"{ORDER_KEY_PREFIX}{genre_id}")
    if row is None or not row.value:
        return []
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(v) for v in data]


def save_order(session: Session, genre_id: int, video_ids: list[str]) -> None:
    payload = json.dumps([str(v) for v in video_ids])
    session.merge(Setting(key=f"{ORDER_KEY_PREFIX}{genre_id}", value=payload))
    session.commit()


def tracks_for_genre(session: Session, genre_id: int) -> list[TrackCache]:
    playlist_ids = session.exec(
        select(Playlist.id).where(Playlist.genre_id == genre_id)
    ).all()
    if not playlist_ids:
        return []
    rows = session.exec(
        select(TrackCache)
        .where(TrackCache.playlist_id.in_(playlist_ids))
        .order_by(TrackCache.playlist_id, TrackCache.position, TrackCache.id)
    ).all()
    return list(rows)


def ordered_tracks_for_genre(session: Session, genre_id: int) -> list[TrackCache]:
    tracks = tracks_for_genre(session, genre_id)
    order = load_order(session, genre_id)
    if not order:
        return tracks
    by_video: dict[str, list[TrackCache]] = {}
    for t in tracks:
        by_video.setdefault(t.youtube_video_id, []).append(t)
    result: list[TrackCache] = []
    used: set[int] = set()
    for vid in order:
        chosen = next(
            (t for t in by_video.get(vid, []) if t.id not in used),
            None,
        )
        if chosen is not None:
            result.append(chosen)
            used.add(chosen.id)
    for t in tracks:
        if t.id not in used:
            result.append(t)
    return result


def first_track_response(
    session: Session, genre: Genre
) -> tuple[TrackOut | None, str | None, int]:
    tracks = tracks_for_genre(session, genre.id)
    if not tracks:
        return None, None, 0
    cursor = encode_cursor(get_settings().secret_key, genre.slug, 0)
    return TrackOut.model_validate(tracks[0]), cursor, len(tracks)


@router.get("", response_model=list[GenreOut])
def list_genres(session: Session = Depends(get_session)) -> list[GenreOut]:
    genres = session.exec(select(Genre).order_by(Genre.sort_order)).all()
    return [
        GenreOut(
            id=s.id,
            name=s.name,
            slug=s.slug,
            is_default=s.is_default,
            track_count=len(tracks_for_genre(session, s.id)),
        )
        for s in genres
    ]


@router.get("/{slug}", response_model=GenreDetail)
def get_genre(slug: str, session: Session = Depends(get_session)) -> GenreDetail:
    genre = session.exec(select(Genre).where(Genre.slug == slug)).first()
    if genre is None:
        raise HTTPException(status_code=404, detail="genre not found")
    track, cursor, total = first_track_response(session, genre)
    return GenreDetail(
        id=genre.id,
        name=genre.name,
        slug=genre.slug,
        is_default=genre.is_default,
        track_count=total,
        track=track,
        cursor=cursor,
    )
