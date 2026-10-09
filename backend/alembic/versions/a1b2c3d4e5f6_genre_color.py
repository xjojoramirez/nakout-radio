"""genre accent color

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9d0
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app.models.GENRE_PALETTE; duplicated inline because migrations must
# not import side-effectful application modules.
_PALETTE: tuple[str, ...] = (
    "#f2a33a",
    "#e0654a",
    "#8fb996",
    "#5fb3b3",
    "#6fa3e0",
    "#a58be0",
    "#e58fb0",
    "#d8c18a",
)


def upgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.add_column(sa.Column("color", sa.String(9), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM genre ORDER BY id")).fetchall()
    used: set[str] = set()
    for index, (genre_id,) in enumerate(rows):
        color = next(
            (c for c in _PALETTE if c not in used),
            _PALETTE[index % len(_PALETTE)],
        )
        conn.execute(
            sa.text("UPDATE genre SET color = :c WHERE id = :id"),
            {"c": color, "id": genre_id},
        )
        used.add(color)


def downgrade() -> None:
    with op.batch_alter_table("genre") as batch_op:
        batch_op.drop_column("color")
