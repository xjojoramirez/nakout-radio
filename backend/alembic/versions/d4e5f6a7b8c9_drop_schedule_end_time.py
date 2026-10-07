"""drop schedule end_time

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3c4d5e6
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scheduleslot") as batch_op:
        batch_op.drop_column("end_time")


def downgrade() -> None:
    with op.batch_alter_table("scheduleslot") as batch_op:
        batch_op.add_column(
            sa.Column(
                "end_time", sa.String(), nullable=False, server_default="00:00"
            )
        )
