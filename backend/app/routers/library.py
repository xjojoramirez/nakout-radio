"""Authenticated music library API (Nakout 2.0)."""

import hmac
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session

from app import library
from app.config import get_settings
from app.db import get_session
from app.library_schemas import (
    LibraryImportIn,
    LibraryImportOut,
    LibraryListOut,
    LibraryMetaOut,
    LibrarySnapshotOut,
    LibraryTrackOut,
)


def require_library_key(
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not settings.library_api_key:
        raise HTTPException(status_code=503, detail="library API is disabled")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token, settings.library_api_key
    ):
        raise HTTPException(
            status_code=401,
            detail="invalid library API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_import_enabled() -> None:
    if not get_settings().library_import_enabled:
        raise HTTPException(status_code=404, detail="not found")


router = APIRouter(
    prefix="/api/library",
    tags=["library"],
    dependencies=[Depends(require_library_key)],
)


@router.get("/meta", response_model=LibraryMetaOut)
def library_meta(session: Session = Depends(get_session)) -> LibraryMetaOut:
    return library.meta(session)


@router.get("/tracks", response_model=LibraryListOut)
def library_tracks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    group: Literal["all", "unassigned"] = "all",
    session: Session = Depends(get_session),
) -> LibraryListOut:
    return library.list_tracks(
        session, group=group, limit=limit, offset=offset
    )


@router.get("/tracks/{video_id}", response_model=LibraryTrackOut)
def library_track(
    video_id: str, session: Session = Depends(get_session)
) -> LibraryTrackOut:
    track = library.get_track(session, video_id)
    if track is None:
        raise HTTPException(status_code=404, detail="track not found")
    return track


@router.get("/export", response_model=LibrarySnapshotOut)
def library_export(
    session: Session = Depends(get_session),
) -> LibrarySnapshotOut:
    return library.build_snapshot(session)


@router.post(
    "/import",
    response_model=LibraryImportOut,
    dependencies=[Depends(require_import_enabled)],
)
def library_import(
    body: LibraryImportIn,
    dry_run: bool = False,
    session: Session = Depends(get_session),
) -> LibraryImportOut:
    try:
        result = library.apply_snapshot(session, body, dry_run=dry_run)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return result
