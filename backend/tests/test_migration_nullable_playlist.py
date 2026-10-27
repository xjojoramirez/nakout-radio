import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic(db_url: str, *args: str) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
        capture_output=True,
    )


def test_nullable_playlist_migration_preserves_tracks(tmp_path):
    db_path = tmp_path / "nullable-playlist.db"
    db_url = f"sqlite:///{db_path}"
    _alembic(db_url, "upgrade", "d8e9f0a1b2c3")

    con = sqlite3.connect(db_path)
    con.executescript(
        """
        INSERT INTO genre (id, name, slug, is_default, sort_order)
            VALUES (1, 'Rock', 'rock', 0, 0);
        INSERT INTO playlist (id, genre_id, youtube_playlist_id, label)
            VALUES (1, 1, 'PL1', 'Rock');
        INSERT INTO trackcache (
            id, playlist_id, youtube_video_id, title, artist, thumbnail_url,
            duration_seconds, position, fetched_at
        ) VALUES (1, 1, 'v1', 'One', 'Art', '', 0, 0, '2026-10-01 10:00:00');
        """
    )
    con.commit()
    con.close()

    _alembic(db_url, "upgrade", "head")

    con = sqlite3.connect(db_path)
    columns = {
        row[1]: row for row in con.execute("PRAGMA table_info(trackcache)")
    }
    assert columns["playlist_id"][3] == 0  # notnull flag
    assert con.execute(
        "SELECT playlist_id, youtube_video_id FROM trackcache"
    ).fetchall() == [(1, "v1")]

    con.execute(
        """
        INSERT INTO trackcache (
            playlist_id, youtube_video_id, title, artist, thumbnail_url,
            duration_seconds, position, fetched_at
        ) VALUES (NULL, 'v2', 'Two', 'Art', '', 0, 0, '2026-10-01 10:00:00')
        """
    )
    con.commit()
    assert con.execute(
        "SELECT playlist_id FROM trackcache WHERE youtube_video_id = 'v2'"
    ).fetchone() == (None,)
    con.close()
