from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import track_details
from app.db import get_session
from app.routers.admin import require_admin
from app.schemas import (
    TrackDetailBase,
    TrackDetailIn,
    TrackDetailOut,
    TrackLibraryOut,
)

router = APIRouter(prefix="/api", tags=["tracks"])


@router.get("/tracks/{video_id}", response_model=TrackDetailBase)
def get_track_detail(
    video_id: str, session: Session = Depends(get_session)
) -> TrackDetailBase:
    detail = track_details.public_detail(session, video_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="track details not available")
    return detail


studio_router = APIRouter(
    prefix="/api/studio",
    tags=["studio-tracks"],
    dependencies=[Depends(require_admin)],
)


@studio_router.get("/tracks", response_model=TrackLibraryOut)
def list_tracks(
    q: str = "",
    status: Literal["empty", "auto", "curated"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> TrackLibraryOut:
    return track_details.library_page(
        session, query=q, status=status, limit=limit, offset=offset
    )


@studio_router.get("/tracks/{video_id}", response_model=TrackDetailOut)
def get_studio_track(
    video_id: str, session: Session = Depends(get_session)
) -> TrackDetailOut:
    detail = track_details.admin_detail(session, video_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="track not found")
    return detail


@studio_router.put("/tracks/{video_id}", response_model=TrackDetailOut)
def save_studio_track(
    video_id: str,
    body: TrackDetailIn,
    session: Session = Depends(get_session),
) -> TrackDetailOut:
    detail = track_details.save_detail(session, video_id, body)
    if detail is None:
        raise HTTPException(status_code=404, detail="track not found")
    return detail


@studio_router.delete("/tracks/{video_id}")
def delete_studio_track(
    video_id: str, session: Session = Depends(get_session)
) -> dict[str, str]:
    if not track_details.delete_detail(session, video_id):
        raise HTTPException(status_code=404, detail="track not found")
    return {"status": "deleted"}
