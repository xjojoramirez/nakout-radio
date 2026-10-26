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


LOCKABLE_FIELDS: tuple[str, ...] = (
    "album",
    "album_artist",
    "release_date",
    "release_year",
    "label",
    "catalog_number",
    "isrc",
    "track_number",
    "disc_number",
    "genres",
    "country",
    "language",
    "bpm",
    "musical_key",
    "cover_url",
    "summary",
    "story",
    "dj_note",
    "lyric_snippet",
    "moods",
    "credits",
    "links",
)


class TrackDetail(SQLModel, table=True):
    """Editorial metadata for a track, keyed by YouTube video id.

    ``TrackCache`` rows are deleted and recreated by playlist syncs, so details
    deliberately hang off the video id instead of a cache row. The same video in
    two playlists shares one detail record.
    """

    youtube_video_id: str = Field(primary_key=True)

    album: str | None = None
    album_artist: str | None = None
    release_date: str | None = None
    release_year: int | None = None
    label: str | None = None
    catalog_number: str | None = None
    isrc: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    genres: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    country: str | None = None
    language: str | None = None
    bpm: int | None = None
    musical_key: str | None = None
    cover_url: str | None = None

    summary: str | None = None
    story: str | None = None
    dj_note: str | None = None
    dj_note_public: bool = True
    lyric_snippet: str | None = None
    moods: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    similar_video_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    credits: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    links: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    sources: dict = Field(default_factory=dict, sa_column=Column(JSON))
    locked_fields: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    enriched_at: datetime | None = None
    enrich_error: str | None = None
    needs_review: bool = False
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class TrackChartEntry(SQLModel, table=True):
    """One chart placement for a track (Billboard, local charts, ...)."""

    id: int | None = Field(default=None, primary_key=True)
    youtube_video_id: str = Field(index=True)
    chart_name: str
    country: str = ""
    peak: int
    weeks_on_chart: int | None = None
    year: int | None = None
    source_url: str = ""


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""


class RevokedSession(SQLModel, table=True):
    jti: str = Field(primary_key=True)
    expires_at: datetime = Field(index=True)
