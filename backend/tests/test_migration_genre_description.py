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


def test_genre_description_migration_defaults_empty(tmp_path):
    db_path = tmp_path / "genre-description.db"
    db_url = f"sqlite:///{db_path}"
    _alembic(db_url, "upgrade", "b7c1d2e3f4a5")

    con = sqlite3.connect(db_path)
    con.execute(
        """
        INSERT INTO genre (name, slug, is_default, sort_order, color)
        VALUES ('Jazz', 'jazz', 0, 0, '#f2a33a')
        """
    )
    con.commit()
    con.close()

    _alembic(db_url, "upgrade", "head")

    con = sqlite3.connect(db_path)
    assert con.execute(
        "SELECT description FROM genre WHERE slug = 'jazz'"
    ).fetchone() == ("",)
    columns = {
        row[1]: row for row in con.execute("PRAGMA table_info(genre)")
    }
    assert columns["description"][3] == 1  # notnull flag
    con.close()
