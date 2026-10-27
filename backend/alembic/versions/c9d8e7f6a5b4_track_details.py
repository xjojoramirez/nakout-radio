"""track details and chart history

Revision ID: c9d8e7f6a5b4
Revises: a7b8c9d0e1f2
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trackdetail",
        sa.Column(
            "youtube_video_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("album", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "album_artist", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "release_date", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "catalog_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("isrc", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("track_number", sa.Integer(), nullable=True),
        sa.Column("disc_number", sa.Integer(), nullable=True),
        sa.Column("genres", sa.JSON(), nullable=True),
        sa.Column("country", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("language", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("bpm", sa.Integer(), nullable=True),
        sa.Column(
            "musical_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("cover_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("story", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("dj_note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "dj_note_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "lyric_snippet", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("moods", sa.JSON(), nullable=True),
        sa.Column("similar_video_ids", sa.JSON(), nullable=True),
        sa.Column("credits", sa.JSON(), nullable=True),
        sa.Column("links", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("locked_fields", sa.JSON(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(), nullable=True),
        sa.Column(
            "enrich_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("youtube_video_id"),
    )
    op.create_table(
        "trackchartentry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "youtube_video_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("chart_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "country",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.Column("peak", sa.Integer(), nullable=False),
        sa.Column("weeks_on_chart", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column(
            "source_url",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_trackchartentry_youtube_video_id"),
        "trackchartentry",
        ["youtube_video_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_trackchartentry_youtube_video_id"),
        table_name="trackchartentry",
    )
    op.drop_table("trackchartentry")
    op.drop_table("trackdetail")
