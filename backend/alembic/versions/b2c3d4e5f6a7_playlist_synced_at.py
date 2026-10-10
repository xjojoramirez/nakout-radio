"""playlist synced_at

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("playlist") as batch_op:
        batch_op.add_column(sa.Column("synced_at", sa.DateTime(), nullable=True))
    op.execute(
        "UPDATE playlist SET synced_at = ("
        " SELECT MAX(fetched_at) FROM trackcache WHERE trackcache.playlist_id = playlist.id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("playlist") as batch_op:
        batch_op.drop_column("synced_at")
