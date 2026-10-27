from collections.abc import Callable

from sqlmodel import Session

from app.library import IncomingTrack, reconcile_playlist
from app.models import Playlist, _utcnow
from app.youtube import TrackData


def sync_playlist(
    session: Session,
    playlist: Playlist,
    fetch: Callable[[str], list[TrackData]],
) -> int:
    tracks = fetch(playlist.youtube_playlist_id)
    reconcile_playlist(
        session,
        playlist,
        [
            IncomingTrack(
                youtube_video_id=t.youtube_video_id,
                title=t.title,
                artist=t.artist,
                thumbnail_url=t.thumbnail_url,
                duration_seconds=t.duration_seconds,
                position=t.position,
            )
            for t in tracks
        ],
        preserve_gain=True,
    )
    playlist.synced_at = _utcnow()
    session.add(playlist)
    session.commit()
    return len(tracks)
