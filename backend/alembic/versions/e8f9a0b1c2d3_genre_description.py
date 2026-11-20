"""genre description

Revision ID: e8f9a0b1c2d3
Revises: b7c1d2e3f4a5
Create Date: 2026-11-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.add_column(
            sa.Column(
                "description",
                sa.String(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.drop_column("description")
