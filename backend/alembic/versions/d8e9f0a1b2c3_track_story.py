"""track story enrichment marker

Revision ID: d8e9f0a1b2c3
Revises: c9d8e7f6a5b4
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c9d8e7f6a5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trackdetail", sa.Column("story_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "trackdetail",
        sa.Column(
            "story_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("trackdetail", "story_error")
    op.drop_column("trackdetail", "story_at")
