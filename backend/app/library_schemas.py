"""Pydantic contracts for the music library API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas import ChartEntryOut, CreditIn, LinkIn

SCHEMA_VERSION = 1


class LibraryGenreOut(BaseModel):
    slug: str
    name: str
    color: str = ""
    is_default: bool = False
    sort_order: int = 0


class LibraryPlaylistOut(BaseModel):
    youtube_playlist_id: str
    label: str = ""
    genre: LibraryGenreOut
    position: int = 0
    gain_db: float | None = None


class LibraryPlaylistManifestOut(BaseModel):
    youtube_playlist_id: str
    label: str = ""
    genre: LibraryGenreOut
    track_count: int = 0


class LibraryDetailOut(BaseModel):
    album: str | None = None
    album_artist: str | None = None
    release_date: str | None = None
    release_year: int | None = None
    label: str | None = None
    catalog_number: str | None = None
    isrc: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    genres: list[str] = Field(default_factory=list)
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
    moods: list[str] = Field(default_factory=list)
    similar_video_ids: list[str] = Field(default_factory=list)
    credits: list[CreditIn] = Field(default_factory=list)
    links: list[LinkIn] = Field(default_factory=list)
    charts: list[ChartEntryOut] = Field(default_factory=list)

    sources: dict = Field(default_factory=dict)
    locked_fields: list[str] = Field(default_factory=list)
    needs_review: bool = False
    enriched_at: datetime | None = None
    story_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LibraryTrackOut(BaseModel):
    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    gain_db: float | None = None
    playlists: list[LibraryPlaylistOut] = Field(default_factory=list)
    detail: LibraryDetailOut | None = None

    @field_validator("playlists")
    @classmethod
    def _unique_playlists(
        cls, value: list[LibraryPlaylistOut]
    ) -> list[LibraryPlaylistOut]:
        seen: set[str] = set()
        for membership in value:
            if membership.youtube_playlist_id in seen:
                raise ValueError("duplicate playlist membership")
            seen.add(membership.youtube_playlist_id)
        return value


class LibrarySnapshotOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    generated_at: datetime
    playlists: list[LibraryPlaylistManifestOut] = Field(default_factory=list)
    tracks: list[LibraryTrackOut] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {value}")
        return value

    @model_validator(mode="after")
    def _consistent_snapshot(self) -> "LibrarySnapshotOut":
        playlist_ids = [p.youtube_playlist_id for p in self.playlists]
        if len(playlist_ids) != len(set(playlist_ids)):
            raise ValueError("duplicate playlist in manifest")
        known = set(playlist_ids)
        video_ids: set[str] = set()
        for track in self.tracks:
            if track.youtube_video_id in video_ids:
                raise ValueError("duplicate track in snapshot")
            video_ids.add(track.youtube_video_id)
            for membership in track.playlists:
                if membership.youtube_playlist_id not in known:
                    raise ValueError(
                        "track references a playlist missing from the manifest"
                    )
        return self


class LibraryImportIn(LibrarySnapshotOut):
    pass


class LibraryListOut(BaseModel):
    items: list[LibraryTrackOut]
    total: int
    limit: int
    offset: int


class LibraryMetaOut(BaseModel):
    schema_version: int
    version: str
    generated_at: datetime
    tracks: int
    standalone_tracks: int
    details: int
    playlists: int
    genres: int


class LibraryImportOut(BaseModel):
    dry_run: bool = False
    genres_created: int = 0
    genres_updated: int = 0
    playlists_created: int = 0
    playlists_updated: int = 0
    tracks_created: int = 0
    tracks_updated: int = 0
    tracks_unchanged: int = 0
    memberships_added: int = 0
    memberships_updated: int = 0
    memberships_removed: int = 0
    tracks_detached: int = 0
    details_created: int = 0
    details_updated: int = 0
    details_unchanged: int = 0
    charts_replaced: int = 0
    locked_fields_skipped: int = 0
