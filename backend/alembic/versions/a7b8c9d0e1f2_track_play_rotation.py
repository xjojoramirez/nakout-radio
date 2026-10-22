"""track play rotation history

Revision ID: a7b8c9d0e1f2
Revises: f3a4b5c6d7e8
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trackplay",
        sa.Column("genre_id", sa.Integer(), nullable=False),
        sa.Column(
            "video_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("last_played_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_started_at", sa.DateTime(), nullable=False),
        sa.Column(
            "play_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.ForeignKeyConstraint(["genre_id"], ["genre.id"]),
        sa.PrimaryKeyConstraint("genre_id", "video_id"),
    )


def downgrade() -> None:
    op.drop_table("trackplay")
