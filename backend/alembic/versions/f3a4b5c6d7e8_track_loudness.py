"""track loudness metadata

Revision ID: f3a4b5c6d7e8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trackcache") as batch_op:
        batch_op.add_column(sa.Column("gain_db", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("gain_checked_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("trackcache") as batch_op:
        batch_op.drop_column("gain_checked_at")
        batch_op.drop_column("gain_db")
