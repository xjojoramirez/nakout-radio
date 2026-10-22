from datetime import datetime, timezone

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from app.loudness import offset_for_gain


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


GENRE_PALETTE: tuple[str, ...] = (
    "#f2a33a",
    "#e0654a",
    "#8fb996",
    "#5fb3b3",
    "#6fa3e0",
    "#a58be0",
    "#e58fb0",
    "#d8c18a",
)


class Genre(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    is_default: bool = False
    sort_order: int = 0
    color: str | None = Field(default=None)


class Playlist(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    youtube_playlist_id: str
    label: str = ""
    synced_at: datetime | None = Field(default=None)


class TrackCache(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    playlist_id: int = Field(foreign_key="playlist.id", index=True)
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    position: int = 0
    fetched_at: datetime = Field(default_factory=_utcnow)
    gain_db: float | None = Field(default=None)
    gain_checked_at: datetime | None = Field(default=None)

    @property
    def volume_offset_db(self) -> float:
        """Volume correction in dB derived from the track's loudness data."""
        return offset_for_gain(self.gain_db)


class ScheduleSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)
    days_of_week: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    start_time: str


class TrackPlay(SQLModel, table=True):
    """The last automatic airing of a track within a genre.

    Keyed by video id rather than ``TrackCache.id`` because playlist syncs
    delete and recreate the cached rows. Manual overrides are deliberately not
    recorded: the rotation guard only describes automatic schedule playback.
    """

    genre_id: int = Field(foreign_key="genre.id", primary_key=True)
    video_id: str = Field(primary_key=True)
    last_played_at: datetime
    last_run_started_at: datetime
    play_count: int = 0


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""


class RevokedSession(SQLModel, table=True):
    jti: str = Field(primary_key=True)
    expires_at: datetime = Field(index=True)
