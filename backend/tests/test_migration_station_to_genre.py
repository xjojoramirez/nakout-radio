import json
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


def _seed_legacy(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO station (id, name, slug, is_default, sort_order) "
        "VALUES (1, 'Morning', 'morning', 1, 0)"
    )
    cur.execute(
        "INSERT INTO playlist (id, station_id, youtube_playlist_id, label) "
        "VALUES (1, 1, 'PL1', '')"
    )
    cur.execute(
        "INSERT INTO scheduleslot "
        "(id, station_id, days_of_week, start_time, end_time) "
        "VALUES (1, 1, '[0,1,2,3,4,5,6]', '00:00', '23:59')"
    )
    cur.execute("INSERT INTO setting (key, value) VALUES ('station_order:1', '[\"a\"]')")
    cur.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?)",
        (
            "broadcast_state",
            json.dumps(
                {
                    "station_id": 1,
                    "track_ids": [],
                    "durations": [],
                    "index": 0,
                    "started_at_utc": "2026-01-01T00:00:00",
                    "manual": False,
                }
            ),
        ),
    )
    con.commit()
    con.close()


def test_station_to_genre_migration_preserves_data(tmp_path):
    db_path = tmp_path / "mig.db"
    db_url = f"sqlite:///{db_path}"
    _alembic(db_url, "upgrade", "b2f4c1a9d3e7")
    _seed_legacy(db_path)
    _alembic(db_url, "upgrade", "head")

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    tables = {
        r[0]
        for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "genre" in tables
    assert "station" not in tables

    assert cur.execute("SELECT name FROM genre WHERE id = 1").fetchone()[0] == "Morning"
    assert cur.execute("SELECT genre_id FROM playlist WHERE id = 1").fetchone()[0] == 1
    assert cur.execute("SELECT genre_id FROM scheduleslot WHERE id = 1").fetchone()[0] == 1

    keys = {r[0] for r in cur.execute("SELECT key FROM setting")}
    assert "genre_order:1" in keys
    assert "station_order:1" not in keys

    value = cur.execute(
        "SELECT value FROM setting WHERE key = 'broadcast_state'"
    ).fetchone()[0]
    data = json.loads(value)
    assert data["genre_id"] == 1
    assert "station_id" not in data

    indexes = {
        r[0]
        for r in cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "ix_genre_slug" in indexes
    assert "ix_station_slug" not in indexes
    assert "ix_playlist_genre_id" in indexes
    assert "ix_scheduleslot_genre_id" in indexes

    columns = {r[1] for r in cur.execute("PRAGMA table_info(scheduleslot)")}
    assert "end_time" not in columns
    con.close()
