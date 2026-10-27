"""allow tracks without a playlist

Revision ID: b7c1d2e3f4a5
Revises: d8e9f0a1b2c3
Create Date: 2026-10-27 00:00:00.000000

A track is a permanent library record. Playlist membership is optional, so
``trackcache.playlist_id`` must be nullable. Existing rows are unaffected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trackcache") as batch_op:
        batch_op.alter_column(
            "playlist_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    # SQLite cannot add a NOT NULL constraint while standalone rows exist.
    op.execute("DELETE FROM trackcache WHERE playlist_id IS NULL")
    with op.batch_alter_table("trackcache") as batch_op:
        batch_op.alter_column(
            "playlist_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
