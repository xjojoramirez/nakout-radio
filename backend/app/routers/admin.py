import json
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, delete, select, update

from app import ratelimit
from app.auth import (
    COOKIE_NAME,
    create_session_token,
    decode_session_token,
    is_session_revoked,
    revoke_session,
    verify_password,
)
from app.broadcast import play_now, set_auto, set_order, skip, stop, utcnow
from app.config import get_settings
from app.db import get_session
from app.models import (
    Playlist,
    ScheduleSlot,
    Setting,
    Genre,
    TrackCache,
    GENRE_PALETTE,
)
from app.routers.genres import ordered_tracks_for_genre
from app.routers.now import build_now
from app.routers.ws import notify_radio
from app.schemas import (
    ChannelIn,
    ChannelOut,
    ChannelPlaylistOut,
    OrderIn,
    PlayIn,
    PlaylistIn,
    PlaylistOut,
    SlotIn,
    SlotOut,
    SlotUpdate,
    GenreRefIn,
    TrackOut,
)
from app.sync import sync_playlist
from app.youtube import (
    TrackData,
    fetch_channel_playlists,
    fetch_playlist_items,
    fetch_video_durations,
    parse_playlist_id,
    resolve_channel_id,
)

router = APIRouter(prefix="/api/studio", tags=["admin"])

logger = logging.getLogger(__name__)

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_SECRET_QUERY_RE = re.compile(r"([?&])key=[^&\s]+")


def _redact_secrets(value: object) -> str:
    return _SECRET_QUERY_RE.sub(r"\1key=REDACTED", str(value))


class LoginIn(BaseModel):
    password: str


class GenreIn(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    is_default: bool = False
    sort_order: int = 0
    color: str | None = None


class GenreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None
    sort_order: int | None = None
    color: str | None = Field(default=None, min_length=1)


_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_color(value: str | None) -> str | None:
    if value is None:
        return None
    if not _COLOR_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="color must be #rrggbb")
    return value.lower()


def _first_unused_color(session: Session) -> str:
    used = {row for row in session.exec(select(Genre.color)).all() if row}
    if len(used) < len(GENRE_PALETTE):
        return next(c for c in GENRE_PALETTE if c not in used)
    genre_count = len(session.exec(select(Genre.id)).all())
    return GENRE_PALETTE[genre_count % len(GENRE_PALETTE)]


def require_admin(
    request: Request, session: Session = Depends(get_session)
) -> None:
    settings = get_settings()
    token = request.cookies.get(COOKIE_NAME, "")
    payload = decode_session_token(token, settings.secret_key)
    jti = payload.get("jti") if payload else None
    if not jti or is_session_revoked(session, jti):
        raise HTTPException(status_code=401, detail="not authenticated")


def _save_channel(session: Session, channel_id: str, title: str) -> None:
    session.merge(Setting(key="youtube_channel_id", value=channel_id))
    session.merge(Setting(key="youtube_channel_title", value=title))
    session.commit()


def _get_saved_channel(session: Session) -> tuple[str | None, str | None]:
    channel_id = session.get(Setting, "youtube_channel_id")
    title = session.get(Setting, "youtube_channel_title")
    return (
        (channel_id.value or None) if channel_id else None,
        (title.value or None) if title else None,
    )


def _build_fetch() -> Callable[[str], list[TrackData]]:
    settings = get_settings()

    def fetch(playlist_id: str) -> list[TrackData]:
        with httpx.Client(timeout=10) as client:
            tracks = fetch_playlist_items(playlist_id, settings.yt_api_key, client)
            durations = fetch_video_durations(
                [t.youtube_video_id for t in tracks], settings.yt_api_key, client
            )
            for track in tracks:
                track.duration_seconds = durations.get(track.youtube_video_id, 0)
            return tracks

    return fetch


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict[str, str]:
    settings = get_settings()
    client_key = request.client.host if request.client else "unknown"
    if ratelimit.is_locked(client_key):
        raise HTTPException(
            status_code=429,
            detail="too many failed login attempts, try again later",
        )
    if not verify_password(body.password, settings.admin_password):
        ratelimit.record_failure(client_key)
        raise HTTPException(status_code=401, detail="invalid password")
    ratelimit.reset(client_key)
    token = create_session_token(settings.secret_key)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=86400,
    )
    return {"status": "ok"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    settings = get_settings()
    payload = decode_session_token(
        request.cookies.get(COOKIE_NAME, ""), settings.secret_key
    )
    if payload is not None and payload.get("jti"):
        revoke_session(
            session,
            payload["jti"],
            datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return {"status": "ok"}


@router.get("/session", dependencies=[Depends(require_admin)])
def session_status() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/genres", status_code=201, dependencies=[Depends(require_admin)])
def create_genre(body: GenreIn, session: Session = Depends(get_session)) -> Genre:
    existing = session.exec(select(Genre).where(Genre.slug == body.slug)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="genre slug already exists")
    genre = Genre(**body.model_dump())
    genre.color = _validate_color(genre.color) or _first_unused_color(session)
    session.add(genre)
    session.commit()
    session.refresh(genre)
    return genre


@router.put("/genres/{genre_id}", dependencies=[Depends(require_admin)])
def update_genre(
    genre_id: int, body: GenreUpdate, session: Session = Depends(get_session)
) -> Genre:
    genre = session.get(Genre, genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="genre not found")
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates:
        clash = session.exec(
            select(Genre).where(Genre.slug == updates["slug"], Genre.id != genre_id)
        ).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail="genre slug already exists")
    if "color" in updates:
        valid = _validate_color(updates["color"])
        if valid is None:
            raise HTTPException(status_code=422, detail="color must be #rrggbb")
        updates["color"] = valid
    if updates.get("is_default"):
        session.exec(
            update(Genre)
            .where(col(Genre.id) != genre_id)
            .values(is_default=False)
        )
    for field, value in updates.items():
        setattr(genre, field, value)
    session.add(genre)
    session.commit()
    notify_radio(build_now(session, utcnow()).model_dump())
    session.refresh(genre)
    return genre


@router.delete("/genres/{genre_id}", dependencies=[Depends(require_admin)])
def delete_genre(genre_id: int, session: Session = Depends(get_session)) -> dict:
    genre = session.get(Genre, genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="genre not found")
    playlist_ids = session.exec(
        select(Playlist.id).where(Playlist.genre_id == genre_id)
    ).all()
    if playlist_ids:
        session.exec(delete(TrackCache).where(TrackCache.playlist_id.in_(playlist_ids)))
    session.exec(delete(Playlist).where(Playlist.genre_id == genre_id))
    session.exec(delete(ScheduleSlot).where(ScheduleSlot.genre_id == genre_id))
    order_key = session.get(Setting, f"genre_order:{genre_id}")
    if order_key is not None:
        session.delete(order_key)
    session.delete(genre)
    session.commit()
    return {"status": "deleted"}


@router.post("/playlists", status_code=201, dependencies=[Depends(require_admin)])
def create_playlist(
    body: PlaylistIn, session: Session = Depends(get_session)
) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        yt_id = parse_playlist_id(body.youtube_playlist_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    playlist = Playlist(
        genre_id=body.genre_id, youtube_playlist_id=yt_id, label=body.label
    )
    session.add(playlist)
    session.commit()
    session.refresh(playlist)
    synced = 0
    sync_error: str | None = None
    try:
        synced = sync_playlist(session, playlist, _build_fetch())
    except httpx.HTTPError as exc:
        sync_error = _redact_secrets(exc)
    return {
        "id": playlist.id,
        "youtube_playlist_id": yt_id,
        "synced": synced,
        "sync_error": sync_error,
    }


@router.get(
    "/playlists",
    response_model=list[PlaylistOut],
    dependencies=[Depends(require_admin)],
)
def list_added_playlists(
    session: Session = Depends(get_session),
) -> list[PlaylistOut]:
    playlists = session.exec(
        select(Playlist).order_by(Playlist.genre_id, Playlist.id)
    ).all()
    genre_names = {s.id: s.name for s in session.exec(select(Genre)).all()}
    counts = dict(
        session.exec(
            select(TrackCache.playlist_id, func.count(TrackCache.id)).group_by(
                TrackCache.playlist_id
            )
        ).all()
    )
    return [
        PlaylistOut(
            id=p.id,
            genre_id=p.genre_id,
            genre_name=genre_names.get(p.genre_id, ""),
            youtube_playlist_id=p.youtube_playlist_id,
            label=p.label,
            track_count=counts.get(p.id, 0),
        )
        for p in playlists
    ]


@router.delete(
    "/playlists/{playlist_id}", dependencies=[Depends(require_admin)]
)
def delete_playlist(
    playlist_id: int, session: Session = Depends(get_session)
) -> dict:
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="playlist not found")
    session.exec(delete(TrackCache).where(TrackCache.playlist_id == playlist_id))
    session.delete(playlist)
    session.commit()
    return {"status": "deleted"}


@router.post("/playlists/{playlist_id}/refresh", dependencies=[Depends(require_admin)])
def refresh_playlist(
    playlist_id: int, session: Session = Depends(get_session)
) -> dict:
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="playlist not found")
    try:
        synced = sync_playlist(session, playlist, _build_fetch())
    except httpx.HTTPError as exc:
        logger.warning("YouTube refresh failed: %s", _redact_secrets(exc))
        raise HTTPException(status_code=502, detail="YouTube fetch failed") from exc
    return {"id": playlist.id, "synced": synced}


@router.post("/sync", dependencies=[Depends(require_admin)])
def sync_all(session: Session = Depends(get_session)) -> dict:
    playlists = session.exec(select(Playlist)).all()
    results = []
    for pl in playlists:
        try:
            synced = sync_playlist(session, pl, _build_fetch())
            results.append({"id": pl.id, "synced": synced, "error": None})
        except httpx.HTTPError as exc:
            results.append({"id": pl.id, "synced": 0, "error": _redact_secrets(exc)})
    return {"results": results}


def _assert_unique_start(
    session: Session,
    days: list[int],
    start_time: str,
    exclude_id: int | None = None,
) -> None:
    for other in session.exec(select(ScheduleSlot)).all():
        if exclude_id is not None and other.id == exclude_id:
            continue
        if datetime.strptime(other.start_time, "%H:%M").time() != datetime.strptime(
            start_time, "%H:%M"
        ).time():
            continue
        shared = sorted(set(other.days_of_week) & set(days))
        if shared:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"a slot already starts at {start_time} "
                    f"on {DAY_LABELS[shared[0]]}"
                ),
            )


def _slot_out(slot: ScheduleSlot, genre_names: dict[int, str]) -> SlotOut:
    return SlotOut(
        id=slot.id,
        genre_id=slot.genre_id,
        genre_name=genre_names.get(slot.genre_id, ""),
        days_of_week=slot.days_of_week,
        start_time=slot.start_time,
    )


@router.get(
    "/slots",
    response_model=list[SlotOut],
    dependencies=[Depends(require_admin)],
)
def list_slots(session: Session = Depends(get_session)) -> list[SlotOut]:
    slots = session.exec(select(ScheduleSlot).order_by(ScheduleSlot.id)).all()
    genre_names = {s.id: s.name for s in session.exec(select(Genre)).all()}
    return [_slot_out(s, genre_names) for s in slots]


@router.post(
    "/slots",
    status_code=201,
    response_model=SlotOut,
    dependencies=[Depends(require_admin)],
)
def create_slot(body: SlotIn, session: Session = Depends(get_session)) -> SlotOut:
    genre = session.get(Genre, body.genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="genre not found")
    _assert_unique_start(session, body.days_of_week, body.start_time)
    slot = ScheduleSlot(**body.model_dump())
    session.add(slot)
    session.commit()
    session.refresh(slot)
    return _slot_out(slot, {genre.id: genre.name})


@router.put(
    "/slots/{slot_id}",
    response_model=SlotOut,
    dependencies=[Depends(require_admin)],
)
def update_slot(
    slot_id: int, body: SlotUpdate, session: Session = Depends(get_session)
) -> SlotOut:
    slot = session.get(ScheduleSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if updates.get("genre_id") is not None:
        if session.get(Genre, updates["genre_id"]) is None:
            raise HTTPException(status_code=404, detail="genre not found")
    final_days = updates.get("days_of_week", slot.days_of_week)
    final_start = updates.get("start_time", slot.start_time)
    if final_start is not None:
        _assert_unique_start(
            session, final_days or [], final_start, exclude_id=slot_id
        )
    for field, value in updates.items():
        setattr(slot, field, value)
    session.add(slot)
    session.commit()
    session.refresh(slot)
    genre_names = {s.id: s.name for s in session.exec(select(Genre)).all()}
    return _slot_out(slot, genre_names)


@router.delete("/slots/{slot_id}", dependencies=[Depends(require_admin)])
def delete_slot(slot_id: int, session: Session = Depends(get_session)) -> dict:
    slot = session.get(ScheduleSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    session.delete(slot)
    session.commit()
    return {"status": "deleted"}


@router.get(
    "/youtube/channel",
    response_model=ChannelOut,
    dependencies=[Depends(require_admin)],
)
def get_youtube_channel(session: Session = Depends(get_session)) -> ChannelOut:
    channel_id, title = _get_saved_channel(session)
    return ChannelOut(channel_id=channel_id, title=title)


@router.put(
    "/youtube/channel",
    response_model=ChannelOut,
    dependencies=[Depends(require_admin)],
)
def set_youtube_channel(
    body: ChannelIn, session: Session = Depends(get_session)
) -> ChannelOut:
    if not body.channel.strip():
        raise HTTPException(status_code=400, detail="channel is required")
    settings = get_settings()
    try:
        with httpx.Client(timeout=10) as client:
            channel_id, title = resolve_channel_id(
                body.channel, settings.yt_api_key, client
            )
    except json.JSONDecodeError as exc:
        logger.warning("YouTube channel lookup returned invalid JSON")
        raise HTTPException(
            status_code=502, detail="YouTube lookup failed"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.warning("YouTube channel lookup failed: %s", _redact_secrets(exc))
        raise HTTPException(
            status_code=502, detail="YouTube lookup failed"
        ) from exc
    _save_channel(session, channel_id, title)
    return ChannelOut(channel_id=channel_id, title=title)


@router.get(
    "/youtube/playlists",
    response_model=list[ChannelPlaylistOut],
    dependencies=[Depends(require_admin)],
)
def list_youtube_playlists(
    session: Session = Depends(get_session),
) -> list[ChannelPlaylistOut]:
    channel_id, _ = _get_saved_channel(session)
    if not channel_id:
        return []
    settings = get_settings()
    try:
        with httpx.Client(timeout=10) as client:
            playlists = fetch_channel_playlists(
                channel_id, settings.yt_api_key, client
            )
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("YouTube playlist fetch failed: %s", _redact_secrets(exc))
        raise HTTPException(
            status_code=502, detail="YouTube fetch failed"
        ) from exc
    existing = set(session.exec(select(Playlist.youtube_playlist_id)).all())
    return [
        ChannelPlaylistOut(
            youtube_playlist_id=p.youtube_playlist_id,
            title=p.title,
            item_count=p.item_count,
            thumbnail_url=p.thumbnail_url,
            already_added=p.youtube_playlist_id in existing,
        )
        for p in playlists
    ]


@router.get(
    "/genres/{genre_id}/tracks",
    response_model=list[TrackOut],
    dependencies=[Depends(require_admin)],
)
def genre_tracks(
    genre_id: int, session: Session = Depends(get_session)
) -> list[TrackOut]:
    if session.get(Genre, genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    return [
        TrackOut.model_validate(t)
        for t in ordered_tracks_for_genre(session, genre_id)
    ]


@router.post("/playback/play", dependencies=[Depends(require_admin)])
def playback_play(body: PlayIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        play_now(session, body.genre_id, body.youtube_video_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.post("/playback/next", dependencies=[Depends(require_admin)])
def playback_next(body: GenreRefIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        skip(session, body.genre_id, "next")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.post("/playback/prev", dependencies=[Depends(require_admin)])
def playback_prev(body: GenreRefIn, session: Session = Depends(get_session)) -> dict:
    if session.get(Genre, body.genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    try:
        skip(session, body.genre_id, "prev")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.post("/playback/auto", dependencies=[Depends(require_admin)])
def playback_auto(session: Session = Depends(get_session)) -> dict:
    set_auto(session)
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.post("/playback/stop", dependencies=[Depends(require_admin)])
def playback_stop(session: Session = Depends(get_session)) -> dict:
    stop(session)
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}


@router.put("/genres/{genre_id}/order", dependencies=[Depends(require_admin)])
def set_genre_order(
    genre_id: int, body: OrderIn, session: Session = Depends(get_session)
) -> dict:
    if session.get(Genre, genre_id) is None:
        raise HTTPException(status_code=404, detail="genre not found")
    set_order(session, genre_id, body.video_ids)
    notify_radio(build_now(session, utcnow()).model_dump())
    return {"status": "ok"}
