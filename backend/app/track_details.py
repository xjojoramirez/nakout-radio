"""Track detail reads/writes shared by the public and Studio APIs."""

from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.models import (
    Genre,
    Playlist,
    TrackCache,
    TrackChartEntry,
    TrackDetail,
    _utcnow,
)
from app.schemas import (
    ChartEntryOut,
    SimilarTrackOut,
    TrackDetailBase,
    TrackDetailIn,
    TrackDetailOut,
    TrackLibraryItem,
    TrackLibraryOut,
)

# Fields copied verbatim from the Studio payload onto the model.
_DETAIL_FIELDS = (
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
    "dj_note_public",
    "lyric_snippet",
    "moods",
    "similar_video_ids",
    "credits",
    "links",
    "locked_fields",
)

_TEXT_CONTENT_FIELDS = (
    "album",
    "album_artist",
    "release_date",
    "release_year",
    "label",
    "catalog_number",
    "isrc",
    "track_number",
    "disc_number",
    "country",
    "language",
    "bpm",
    "musical_key",
    "cover_url",
    "summary",
    "story",
    "dj_note",
    "lyric_snippet",
)

# Fields counted by the Studio completeness meter.
_COMPLETENESS_FIELDS = ("album", "release_year", "label", "credits", "story")


def track_row(session: Session, video_id: str) -> TrackCache | None:
    return session.exec(
        select(TrackCache).where(TrackCache.youtube_video_id == video_id)
    ).first()


def charts_for(session: Session, video_id: str) -> list[TrackChartEntry]:
    return list(
        session.exec(
            select(TrackChartEntry)
            .where(TrackChartEntry.youtube_video_id == video_id)
            .order_by(TrackChartEntry.chart_name, TrackChartEntry.year)
        ).all()
    )


def chart_counts(session: Session) -> dict[str, int]:
    rows = session.exec(
        select(TrackChartEntry.youtube_video_id, func.count()).group_by(
            TrackChartEntry.youtube_video_id
        )
    ).all()
    return {video_id: count for video_id, count in rows}


def has_content(row: TrackDetail | None, chart_total: int = 0) -> bool:
    if row is None:
        return False
    if chart_total:
        return True
    if any(getattr(row, field) for field in _TEXT_CONTENT_FIELDS):
        return True
    return bool(row.genres or row.moods or row.credits or row.links)


def status_for(row: TrackDetail | None, chart_total: int = 0) -> str:
    if row is None:
        return "empty"
    if row.locked_fields:
        return "curated"
    if row.enriched_at is not None:
        return "auto"
    return "curated" if has_content(row, chart_total) else "empty"


def completeness_for(row: TrackDetail | None, chart_total: int = 0) -> int:
    if row is None:
        return 0
    filled = sum(
        1 for field in _COMPLETENESS_FIELDS if getattr(row, field, None)
    )
    if chart_total:
        filled += 1
    return filled


def _similar_tracks(
    session: Session, video_ids: list[str]
) -> list[SimilarTrackOut]:
    if not video_ids:
        return []
    rows = session.exec(
        select(TrackCache).where(TrackCache.youtube_video_id.in_(video_ids))
    ).all()
    found = {row.youtube_video_id: row for row in rows}
    out: list[SimilarTrackOut] = []
    for video_id in video_ids:
        row = found.get(video_id)
        out.append(
            SimilarTrackOut(
                youtube_video_id=video_id,
                title=row.title if row else "",
                artist=row.artist if row else "",
            )
        )
    return out


def _base_payload(
    session: Session, video_id: str, row: TrackDetail | None
) -> dict:
    track = track_row(session, video_id)
    charts = charts_for(session, video_id)
    return {
        "youtube_video_id": video_id,
        "title": track.title if track else "",
        "artist": track.artist if track else "",
        "album": row.album if row else None,
        "album_artist": row.album_artist if row else None,
        "release_date": row.release_date if row else None,
        "release_year": row.release_year if row else None,
        "label": row.label if row else None,
        "catalog_number": row.catalog_number if row else None,
        "isrc": row.isrc if row else None,
        "track_number": row.track_number if row else None,
        "disc_number": row.disc_number if row else None,
        "genres": list(row.genres or []) if row else [],
        "country": row.country if row else None,
        "language": row.language if row else None,
        "bpm": row.bpm if row else None,
        "musical_key": row.musical_key if row else None,
        "cover_url": row.cover_url if row else None,
        "summary": row.summary if row else None,
        "story": row.story if row else None,
        "dj_note": (
            row.dj_note if row and row.dj_note_public else None
        ),
        "lyric_snippet": row.lyric_snippet if row else None,
        "moods": list(row.moods or []) if row else [],
        "credits": list(row.credits or []) if row else [],
        "links": list(row.links or []) if row else [],
        "charts": [
            ChartEntryOut(
                chart_name=entry.chart_name,
                country=entry.country or "",
                peak=entry.peak,
                weeks_on_chart=entry.weeks_on_chart,
                year=entry.year,
                source_url=entry.source_url or "",
            )
            for entry in charts
        ],
        "similar": _similar_tracks(
            session, list(row.similar_video_ids or []) if row else []
        ),
    }


def public_detail(session: Session, video_id: str) -> TrackDetailBase | None:
    row = session.get(TrackDetail, video_id)
    if row is None:
        return None
    chart_total = len(charts_for(session, video_id))
    if not has_content(row, chart_total):
        return None
    return TrackDetailBase(**_base_payload(session, video_id, row))


def admin_detail(session: Session, video_id: str) -> TrackDetailOut | None:
    if track_row(session, video_id) is None:
        return None
    row = session.get(TrackDetail, video_id)
    payload = _base_payload(session, video_id, row)
    chart_total = len(payload["charts"])
    payload.update(
        {
            "dj_note": row.dj_note if row else None,
            "dj_note_public": row.dj_note_public if row else True,
            "sources": dict(row.sources or {}) if row else {},
            "locked_fields": list(row.locked_fields or []) if row else [],
            "needs_review": row.needs_review if row else False,
            "enriched_at": row.enriched_at if row else None,
            "enrich_error": row.enrich_error if row else None,
            "created_at": row.created_at if row else None,
            "updated_at": row.updated_at if row else None,
            "status": status_for(row, chart_total),
            "completeness": completeness_for(row, chart_total),
        }
    )
    return TrackDetailOut(**payload)


def save_detail(
    session: Session, video_id: str, data: TrackDetailIn
) -> TrackDetailOut | None:
    if track_row(session, video_id) is None:
        return None

    row = session.get(TrackDetail, video_id)
    if row is None:
        row = TrackDetail(youtube_video_id=video_id)
    for field in _DETAIL_FIELDS:
        value = getattr(data, field)
        if field == "credits" or field == "links":
            value = [entry.model_dump() for entry in value]
        setattr(row, field, value)
    row.updated_at = _utcnow()
    session.add(row)

    session.exec(
        delete(TrackChartEntry).where(
            TrackChartEntry.youtube_video_id == video_id
        )
    )
    for entry in data.charts:
        session.add(
            TrackChartEntry(
                youtube_video_id=video_id, **entry.model_dump()
            )
        )
    session.commit()
    session.refresh(row)
    return admin_detail(session, video_id)


def delete_detail(session: Session, video_id: str) -> bool:
    if track_row(session, video_id) is None:
        return False
    session.exec(
        delete(TrackChartEntry).where(
            TrackChartEntry.youtube_video_id == video_id
        )
    )
    row = session.get(TrackDetail, video_id)
    if row is not None:
        session.delete(row)
    session.commit()
    return True


def _genre_names(session: Session) -> dict[str, set[str]]:
    rows = session.exec(
        select(TrackCache.youtube_video_id, Genre.name)
        .join(Playlist, TrackCache.playlist_id == Playlist.id)
        .join(Genre, Playlist.genre_id == Genre.id)
    ).all()
    names: dict[str, set[str]] = {}
    for video_id, name in rows:
        names.setdefault(video_id, set()).add(name)
    return names


def library_page(
    session: Session,
    *,
    query: str = "",
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TrackLibraryOut:
    # The library is a few hundred tracks; dedupe and filter in Python so the
    # listing stays readable. Move to SQL if it ever grows to thousands.
    unique: dict[str, TrackCache] = {}
    for row in session.exec(select(TrackCache)).all():
        unique.setdefault(row.youtube_video_id, row)

    details = {
        row.youtube_video_id: row
        for row in session.exec(select(TrackDetail)).all()
    }
    counts = chart_counts(session)
    genres = _genre_names(session)

    needle = (query or "").strip().casefold()
    items: list[TrackLibraryItem] = []
    for video_id, track in unique.items():
        if needle and (
            needle not in track.title.casefold()
            and needle not in track.artist.casefold()
        ):
            continue
        row = details.get(video_id)
        chart_total = counts.get(video_id, 0)
        item_status = status_for(row, chart_total)
        if status and item_status != status:
            continue
        items.append(
            TrackLibraryItem(
                youtube_video_id=video_id,
                title=track.title,
                artist=track.artist,
                thumbnail_url=track.thumbnail_url,
                duration_seconds=track.duration_seconds,
                album=row.album if row else None,
                release_year=row.release_year if row else None,
                status=item_status,
                completeness=completeness_for(row, chart_total),
                genres=sorted(genres.get(video_id, set())),
            )
        )

    items.sort(key=lambda item: (item.artist.casefold(), item.title.casefold()))
    return TrackLibraryOut(
        items=items[offset : offset + limit],
        total=len(items),
        limit=limit,
        offset=offset,
    )
