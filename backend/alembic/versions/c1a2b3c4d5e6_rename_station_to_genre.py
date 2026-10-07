"""rename station to genre

Revision ID: c1a2b3c4d5e6
Revises: b2f4c1a9d3e7
Create Date: 2026-10-06 00:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, None] = "b2f4c1a9d3e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE station RENAME TO genre")
    op.execute("ALTER TABLE playlist RENAME COLUMN station_id TO genre_id")
    op.execute("ALTER TABLE scheduleslot RENAME COLUMN station_id TO genre_id")

    op.execute("DROP INDEX IF EXISTS ix_station_slug")
    op.execute("CREATE UNIQUE INDEX ix_genre_slug ON genre (slug)")
    op.execute("DROP INDEX IF EXISTS ix_playlist_station_id")
    op.execute("CREATE INDEX ix_playlist_genre_id ON playlist (genre_id)")
    op.execute("DROP INDEX IF EXISTS ix_scheduleslot_station_id")
    op.execute("CREATE INDEX ix_scheduleslot_genre_id ON scheduleslot (genre_id)")

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE setting SET key = replace(key, 'station_order:', 'genre_order:') "
            "WHERE key LIKE 'station_order:%'"
        )
    )
    row = conn.execute(
        sa.text("SELECT value FROM setting WHERE key = 'broadcast_state'")
    ).first()
    if row is not None and row[0]:
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict) and "station_id" in data:
            data["genre_id"] = data.pop("station_id")
            conn.execute(
                sa.text(
                    "UPDATE setting SET value = :v WHERE key = 'broadcast_state'"
                ),
                {"v": json.dumps(data)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT value FROM setting WHERE key = 'broadcast_state'")
    ).first()
    if row is not None and row[0]:
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict) and "genre_id" in data:
            data["station_id"] = data.pop("genre_id")
            conn.execute(
                sa.text(
                    "UPDATE setting SET value = :v WHERE key = 'broadcast_state'"
                ),
                {"v": json.dumps(data)},
            )
    conn.execute(
        sa.text(
            "UPDATE setting SET key = replace(key, 'genre_order:', 'station_order:') "
            "WHERE key LIKE 'genre_order:%'"
        )
    )

    op.execute("ALTER TABLE playlist RENAME COLUMN genre_id TO station_id")
    op.execute("ALTER TABLE scheduleslot RENAME COLUMN genre_id TO station_id")
    op.execute("DROP INDEX IF EXISTS ix_playlist_genre_id")
    op.execute("CREATE INDEX ix_playlist_station_id ON playlist (station_id)")
    op.execute("DROP INDEX IF EXISTS ix_scheduleslot_genre_id")
    op.execute("CREATE INDEX ix_scheduleslot_station_id ON scheduleslot (station_id)")
    op.execute("DROP INDEX IF EXISTS ix_genre_slug")
    op.execute("ALTER TABLE genre RENAME TO station")
    op.execute("CREATE UNIQUE INDEX ix_station_slug ON station (slug)")
