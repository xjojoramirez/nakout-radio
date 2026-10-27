"""Music library persistence: detach, reconcile, snapshot, and import.

Playlists are views over the library. A ``TrackCache`` row with a
``playlist_id`` is a playlist membership; a row with ``playlist_id IS NULL`` is
a standalone library track. Removing a membership never deletes the track.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlmodel import Session, delete, select

from app import __version__
from app.library_schemas import (
    SCHEMA_VERSION,
    LibraryDetailOut,
    LibraryGenreOut,
    LibraryImportOut,
    LibraryListOut,
    LibraryMetaOut,
    LibraryPlaylistManifestOut,
    LibraryPlaylistOut,
    LibrarySnapshotOut,
    LibraryTrackOut,
)
from app.models import (
    Genre,
    Playlist,
    TrackCache,
    TrackChartEntry,
    TrackDetail,
    _utcnow,
)
from app.schemas import ChartEntryOut, CreditIn, LinkIn

# Editable detail fields copied field-by-field from a snapshot.
DETAIL_COPY_FIELDS: tuple[str, ...] = (
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
    "similar_video_ids",
    "credits",
    "links",
)


@dataclass
class IncomingTrack:
    """A track as delivered by YouTube or the library snapshot."""

    youtube_video_id: str
    title: str
    artist: str
    thumbnail_url: str = ""
    duration_seconds: int = 0
    position: int = 0
    gain_db: float | None = None


@dataclass
class ReconcileResult:
    memberships_added: int = 0
    memberships_updated: int = 0
    memberships_removed: int = 0
    tracks_detached: int = 0
    created_video_ids: set[str] = field(default_factory=set)
    changed_video_ids: set[str] = field(default_factory=set)


def detach_membership(session: Session, row: TrackCache) -> bool:
    """Keep the track, drop this membership.

    Returns ``True`` when the row became a standalone library track. When the
    same video survives in another row, this membership row is deleted instead.
    """
    other = session.exec(
        select(TrackCache).where(
            TrackCache.youtube_video_id == row.youtube_video_id,
            TrackCache.id != row.id,
        )
    ).first()
    if other is not None:
        session.delete(row)
        return False
    row.playlist_id = None
    row.position = 0
    session.add(row)
    return True


def _assign_track_fields(row: TrackCache, item: IncomingTrack) -> bool:
    changed = False
    for field_name in (
        "title",
        "artist",
        "thumbnail_url",
        "duration_seconds",
        "position",
    ):
        value = getattr(item, field_name)
        if getattr(row, field_name) != value:
            setattr(row, field_name, value)
            changed = True
    return changed


def reconcile_playlist(
    session: Session,
    playlist: Playlist,
    incoming: Iterable[IncomingTrack],
    *,
    preserve_gain: bool,
) -> ReconcileResult:
    """Make ``playlist``'s memberships match ``incoming``.

    Existing rows are updated in place so their IDs survive. Tracks that left
    the playlist are detached (or their membership row is dropped when another
    playlist still owns them).
    """
    result = ReconcileResult()
    incoming_by_video: dict[str, IncomingTrack] = {}
    for item in incoming:
        if item.youtube_video_id in incoming_by_video:
            continue
        incoming_by_video[item.youtube_video_id] = item

    current: dict[str, TrackCache] = {}
    rows = session.exec(
        select(TrackCache).where(TrackCache.playlist_id == playlist.id)
    ).all()
    for row in rows:
        if row.youtube_video_id in current:
            # Defensive: duplicate memberships are not part of the model.
            result.memberships_removed += 1
            session.delete(row)
            continue
        current[row.youtube_video_id] = row

    standalone: dict[str, TrackCache] = {}
    if incoming_by_video:
        rows = session.exec(
            select(TrackCache).where(
                TrackCache.playlist_id.is_(None),
                TrackCache.youtube_video_id.in_(list(incoming_by_video)),
            )
        ).all()
        for row in rows:
            if row.youtube_video_id in standalone:
                result.memberships_removed += 1
                session.delete(row)
                continue
            standalone[row.youtube_video_id] = row

    for video_id, item in incoming_by_video.items():
        row = current.pop(video_id, None)
        if row is None:
            row = standalone.pop(video_id, None)

        if row is None:
            row = TrackCache(youtube_video_id=video_id, playlist_id=playlist.id)
            result.memberships_added += 1
            result.created_video_ids.add(video_id)
            row_changed = True
        else:
            row_changed = False
            if row.playlist_id != playlist.id:
                row.playlist_id = playlist.id
                result.memberships_added += 1
                row_changed = True

        if preserve_gain:
            if row.title != item.title or row.artist != item.artist:
                if row.gain_db is not None or row.gain_checked_at is not None:
                    row.gain_db = None
                    row.gain_checked_at = None
                    row_changed = True
        elif item.gain_db is not None and row.gain_db != item.gain_db:
            row.gain_db = item.gain_db
            row.gain_checked_at = None
            row_changed = True

        if _assign_track_fields(row, item):
            row_changed = True
        row.fetched_at = _utcnow()
        session.add(row)

        if row_changed and row.id is not None:
            result.memberships_updated += 1
            result.changed_video_ids.add(video_id)

    # A video that already had a membership in this playlist does not need its
    # standalone duplicate.
    for row in standalone.values():
        result.memberships_removed += 1
        session.delete(row)

    for row in current.values():
        if detach_membership(session, row):
            result.tracks_detached += 1
        else:
            result.memberships_removed += 1
        result.changed_video_ids.add(row.youtube_video_id)

    return result


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------


def _genre_out(genre: Genre) -> LibraryGenreOut:
    return LibraryGenreOut(
        slug=genre.slug,
        name=genre.name,
        color=genre.color or "",
        is_default=genre.is_default,
        sort_order=genre.sort_order,
    )


def _chart_dicts(session: Session, video_id: str) -> list[dict]:
    rows = session.exec(
        select(TrackChartEntry)
        .where(TrackChartEntry.youtube_video_id == video_id)
        .order_by(TrackChartEntry.chart_name, TrackChartEntry.year)
    ).all()
    return [
        ChartEntryOut(
            chart_name=row.chart_name,
            country=row.country or "",
            peak=row.peak,
            weeks_on_chart=row.weeks_on_chart,
            year=row.year,
            source_url=row.source_url or "",
        ).model_dump()
        for row in rows
    ]


def _detail_out(session: Session, video_id: str) -> LibraryDetailOut | None:
    row = session.get(TrackDetail, video_id)
    charts = _chart_dicts(session, video_id)
    if row is None and not charts:
        return None
    if row is None:
        return LibraryDetailOut(charts=[ChartEntryOut(**c) for c in charts])
    return LibraryDetailOut(
        album=row.album,
        album_artist=row.album_artist,
        release_date=row.release_date,
        release_year=row.release_year,
        label=row.label,
        catalog_number=row.catalog_number,
        isrc=row.isrc,
        track_number=row.track_number,
        disc_number=row.disc_number,
        genres=list(row.genres or []),
        country=row.country,
        language=row.language,
        bpm=row.bpm,
        musical_key=row.musical_key,
        cover_url=row.cover_url,
        summary=row.summary,
        story=row.story,
        dj_note=row.dj_note,
        dj_note_public=row.dj_note_public,
        lyric_snippet=row.lyric_snippet,
        moods=list(row.moods or []),
        similar_video_ids=list(row.similar_video_ids or []),
        credits=[CreditIn(**entry) for entry in (row.credits or [])],
        links=[LinkIn(**entry) for entry in (row.links or [])],
        charts=[ChartEntryOut(**entry) for entry in charts],
        sources=dict(row.sources or {}),
        locked_fields=list(row.locked_fields or []),
        needs_review=row.needs_review,
        enriched_at=row.enriched_at,
        story_at=row.story_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _track_payload(
    session: Session,
    video_id: str,
    rows: list[TrackCache],
    playlists: dict[int, Playlist],
    genres: dict[int, Genre],
) -> LibraryTrackOut:
    canonical = max(
        rows,
        key=lambda row: (row.fetched_at or datetime.min, row.id or 0),
    )
    standalone = next((row for row in rows if row.playlist_id is None), None)
    memberships: list[tuple[tuple[int, int, int], LibraryPlaylistOut]] = []
    seen_playlists: set[int] = set()
    for row in rows:
        if row.playlist_id is None or row.playlist_id in seen_playlists:
            continue
        seen_playlists.add(row.playlist_id)
        playlist = playlists.get(row.playlist_id)
        if playlist is None:
            continue
        genre = genres.get(playlist.genre_id)
        if genre is None:
            continue
        membership = LibraryPlaylistOut(
            youtube_playlist_id=playlist.youtube_playlist_id,
            label=playlist.label,
            genre=_genre_out(genre),
            position=row.position,
            gain_db=row.gain_db,
        )
        memberships.append(
            (
                (genre.sort_order, playlist.id or 0, row.position),
                membership,
            )
        )
    memberships.sort(key=lambda pair: pair[0])
    return LibraryTrackOut(
        youtube_video_id=video_id,
        title=canonical.title,
        artist=canonical.artist,
        thumbnail_url=canonical.thumbnail_url,
        duration_seconds=canonical.duration_seconds,
        gain_db=standalone.gain_db if standalone is not None else None,
        playlists=[membership for _, membership in memberships],
        detail=_detail_out(session, video_id),
    )


def _track_payloads(session: Session) -> list[LibraryTrackOut]:
    rows = session.exec(select(TrackCache).order_by(TrackCache.id)).all()
    grouped: dict[str, list[TrackCache]] = {}
    for row in rows:
        grouped.setdefault(row.youtube_video_id, []).append(row)
    playlists = {p.id: p for p in session.exec(select(Playlist)).all() if p.id}
    genres = {g.id: g for g in session.exec(select(Genre)).all() if g.id}
    tracks = [
        _track_payload(session, video_id, group, playlists, genres)
        for video_id, group in grouped.items()
    ]
    tracks.sort(
        key=lambda track: (
            track.artist.casefold(),
            track.title.casefold(),
            track.youtube_video_id,
        )
    )
    return tracks


def build_snapshot(session: Session) -> LibrarySnapshotOut:
    rows = session.exec(select(TrackCache)).all()
    counts: dict[int, set[str]] = {}
    for row in rows:
        if row.playlist_id is not None:
            counts.setdefault(row.playlist_id, set()).add(row.youtube_video_id)
    playlists = session.exec(select(Playlist)).all()
    genres = {g.id: g for g in session.exec(select(Genre)).all() if g.id}
    manifest: list[LibraryPlaylistManifestOut] = []
    for playlist in playlists:
        genre = genres.get(playlist.genre_id)
        if genre is None:
            continue
        manifest.append(
            LibraryPlaylistManifestOut(
                youtube_playlist_id=playlist.youtube_playlist_id,
                label=playlist.label,
                genre=_genre_out(genre),
                track_count=len(counts.get(playlist.id, set())),
            )
        )
    manifest.sort(
        key=lambda p: (p.genre.sort_order, p.youtube_playlist_id)
    )
    return LibrarySnapshotOut(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc),
        playlists=manifest,
        tracks=_track_payloads(session),
    )


def list_tracks(
    session: Session,
    *,
    group: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> LibraryListOut:
    tracks = _track_payloads(session)
    if group == "unassigned":
        tracks = [track for track in tracks if not track.playlists]
    total = len(tracks)
    return LibraryListOut(
        items=tracks[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_track(session: Session, video_id: str) -> LibraryTrackOut | None:
    for track in _track_payloads(session):
        if track.youtube_video_id == video_id:
            return track
    return None


def meta(session: Session) -> LibraryMetaOut:
    rows = session.exec(select(TrackCache)).all()
    grouped: dict[str, list[TrackCache]] = {}
    for row in rows:
        grouped.setdefault(row.youtube_video_id, []).append(row)
    standalone = sum(
        1
        for group in grouped.values()
        if all(row.playlist_id is None for row in group)
    )
    return LibraryMetaOut(
        schema_version=SCHEMA_VERSION,
        version=__version__,
        generated_at=datetime.now(timezone.utc),
        tracks=len(grouped),
        standalone_tracks=standalone,
        details=len(session.exec(select(TrackDetail.youtube_video_id)).all()),
        playlists=len(session.exec(select(Playlist.id)).all()),
        genres=len(session.exec(select(Genre.id)).all()),
    )


# ---------------------------------------------------------------------------
# Write side: import
# ---------------------------------------------------------------------------


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _detail_values(detail: LibraryDetailOut) -> dict:
    values: dict = {}
    for field_name in DETAIL_COPY_FIELDS:
        value = getattr(detail, field_name)
        if field_name in {"credits", "links"}:
            value = [entry.model_dump() for entry in value]
        values[field_name] = value
    return values


def _apply_detail(
    session: Session,
    video_id: str,
    detail: LibraryDetailOut,
    now: datetime,
    out: LibraryImportOut,
) -> bool:
    """Merge one detail. Returns True when the track changed."""
    row = session.get(TrackDetail, video_id)
    if row is None:
        row = TrackDetail(youtube_video_id=video_id)
        for field_name, value in _detail_values(detail).items():
            setattr(row, field_name, value)
        row.dj_note_public = detail.dj_note_public
        row.sources = dict(detail.sources or {})
        row.locked_fields = list(dict.fromkeys(detail.locked_fields or []))
        row.needs_review = detail.needs_review
        row.enriched_at = _naive_utc(detail.enriched_at)
        row.story_at = _naive_utc(detail.story_at)
        row.created_at = _naive_utc(detail.created_at) or now
        row.updated_at = now
        session.add(row)
        for chart in detail.charts:
            session.add(
                TrackChartEntry(
                    youtube_video_id=video_id, **chart.model_dump()
                )
            )
        out.details_created += 1
        return True

    locked = set(row.locked_fields or [])
    live_locked = set(detail.locked_fields or [])
    sources = dict(row.sources or {})
    changed = False
    skipped = 0

    for field_name, live_value in _detail_values(detail).items():
        if field_name in locked:
            if getattr(row, field_name) != live_value:
                skipped += 1
            continue
        if field_name in detail.sources:
            sources[field_name] = detail.sources[field_name]
        else:
            sources.pop(field_name, None)
        if getattr(row, field_name) != live_value:
            setattr(row, field_name, live_value)
            changed = True

    if "dj_note" in locked:
        if row.dj_note_public != detail.dj_note_public:
            skipped += 1
    elif row.dj_note_public != detail.dj_note_public:
        row.dj_note_public = detail.dj_note_public
        changed = True

    merged_locks = list(row.locked_fields or [])
    for lock in live_locked:
        if lock not in merged_locks:
            merged_locks.append(lock)
    if merged_locks != list(row.locked_fields or []):
        row.locked_fields = merged_locks
        changed = True

    if detail.needs_review and not row.needs_review:
        row.needs_review = True
        changed = True

    for field_name in ("enriched_at", "story_at"):
        value = _naive_utc(getattr(detail, field_name))
        if value is not None and getattr(row, field_name) != value:
            setattr(row, field_name, value)
            changed = True
    if row.created_at is None and detail.created_at is not None:
        row.created_at = _naive_utc(detail.created_at)
        changed = True

    current_charts = _chart_dicts(session, video_id)
    live_charts = [chart.model_dump() for chart in detail.charts]
    if "charts" in locked:
        if current_charts != live_charts:
            skipped += 1
    else:
        if "charts" in detail.sources:
            sources["charts"] = detail.sources["charts"]
        else:
            sources.pop("charts", None)
        if current_charts != live_charts:
            session.exec(
                delete(TrackChartEntry).where(
                    TrackChartEntry.youtube_video_id == video_id
                )
            )
            for chart in detail.charts:
                session.add(
                    TrackChartEntry(
                        youtube_video_id=video_id, **chart.model_dump()
                    )
                )
            out.charts_replaced += 1
            changed = True

    if sources != dict(row.sources or {}):
        row.sources = sources
        changed = True

    out.locked_fields_skipped += skipped
    if changed:
        row.updated_at = now
        out.details_updated += 1
        return True
    out.details_unchanged += 1
    return False


def apply_snapshot(
    session: Session,
    snapshot: LibrarySnapshotOut,
    *,
    dry_run: bool = False,
) -> LibraryImportOut:
    out = LibraryImportOut(dry_run=dry_run)
    now = _utcnow()
    before = set(session.exec(select(TrackCache.youtube_video_id)).all())

    genre_by_slug = {g.slug: g for g in session.exec(select(Genre)).all()}
    for manifest in snapshot.playlists:
        spec = manifest.genre
        genre = genre_by_slug.get(spec.slug)
        if genre is None:
            genre = Genre(
                name=spec.name,
                slug=spec.slug,
                color=spec.color or None,
                sort_order=spec.sort_order,
                is_default=False,
            )
            if spec.is_default and not any(
                g.is_default for g in genre_by_slug.values()
            ):
                genre.is_default = True
            session.add(genre)
            session.flush()
            genre_by_slug[spec.slug] = genre
            out.genres_created += 1
            continue

        changed = False
        for field_name, value in (
            ("name", spec.name),
            ("color", spec.color or None),
            ("sort_order", spec.sort_order),
        ):
            if getattr(genre, field_name) != value:
                setattr(genre, field_name, value)
                changed = True
        if (
            spec.is_default
            and not genre.is_default
            and not any(
                g.is_default
                for slug, g in genre_by_slug.items()
                if slug != spec.slug
            )
        ):
            genre.is_default = True
            changed = True
        if changed:
            out.genres_updated += 1

    playlist_by_yt = {
        p.youtube_playlist_id: p
        for p in session.exec(select(Playlist)).all()
    }
    for manifest in snapshot.playlists:
        genre = genre_by_slug[manifest.genre.slug]
        playlist = playlist_by_yt.get(manifest.youtube_playlist_id)
        if playlist is None:
            playlist = Playlist(
                genre_id=genre.id,
                youtube_playlist_id=manifest.youtube_playlist_id,
                label=manifest.label,
            )
            session.add(playlist)
            session.flush()
            playlist_by_yt[manifest.youtube_playlist_id] = playlist
            out.playlists_created += 1
            continue
        changed = False
        if playlist.genre_id != genre.id:
            playlist.genre_id = genre.id
            changed = True
        if playlist.label != manifest.label:
            playlist.label = manifest.label
            changed = True
        if changed:
            out.playlists_updated += 1

    incoming: dict[str, list[IncomingTrack]] = {
        manifest.youtube_playlist_id: [] for manifest in snapshot.playlists
    }
    for track in snapshot.tracks:
        for membership in track.playlists:
            incoming[membership.youtube_playlist_id].append(
                IncomingTrack(
                    youtube_video_id=track.youtube_video_id,
                    title=track.title,
                    artist=track.artist,
                    thumbnail_url=track.thumbnail_url,
                    duration_seconds=track.duration_seconds,
                    position=membership.position,
                    gain_db=membership.gain_db,
                )
            )

    changed_video_ids: set[str] = set()
    for manifest in snapshot.playlists:
        result = reconcile_playlist(
            session,
            playlist_by_yt[manifest.youtube_playlist_id],
            incoming[manifest.youtube_playlist_id],
            preserve_gain=False,
        )
        out.memberships_added += result.memberships_added
        out.memberships_updated += result.memberships_updated
        out.memberships_removed += result.memberships_removed
        out.tracks_detached += result.tracks_detached
        changed_video_ids |= result.changed_video_ids

    for track in snapshot.tracks:
        rows = session.exec(
            select(TrackCache).where(
                TrackCache.youtube_video_id == track.youtube_video_id
            )
        ).all()
        if not rows:
            if track.playlists:
                raise ValueError(
                    f"track {track.youtube_video_id} has no membership after import"
                )
            row = TrackCache(
                playlist_id=None,
                youtube_video_id=track.youtube_video_id,
                title=track.title,
                artist=track.artist,
                thumbnail_url=track.thumbnail_url,
                duration_seconds=track.duration_seconds,
                position=0,
                gain_db=track.gain_db,
                fetched_at=now,
            )
            session.add(row)
            rows = [row]
        for row in rows:
            row_changed = False
            for field_name in (
                "title",
                "artist",
                "thumbnail_url",
                "duration_seconds",
            ):
                value = getattr(track, field_name)
                if getattr(row, field_name) != value:
                    setattr(row, field_name, value)
                    row_changed = True
            if (
                not track.playlists
                and row.playlist_id is None
                and track.gain_db is not None
                and row.gain_db != track.gain_db
            ):
                row.gain_db = track.gain_db
                row_changed = True
            if row_changed:
                changed_video_ids.add(track.youtube_video_id)

        if track.detail is not None:
            if _apply_detail(session, track.youtube_video_id, track.detail, now, out):
                changed_video_ids.add(track.youtube_video_id)

    after = set(session.exec(select(TrackCache.youtube_video_id)).all())
    created = after - before
    out.tracks_created = len(created)
    out.tracks_updated = len(changed_video_ids - created)
    snapshot_ids = {track.youtube_video_id for track in snapshot.tracks}
    out.tracks_unchanged = len(snapshot_ids - created - changed_video_ids)
    return out
