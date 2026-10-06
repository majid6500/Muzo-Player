"""SQLite connection and schema migrations."""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Each entry upgrades the schema by one version. Never edit old entries;
# append a new one (e.g. favorites, playlists tables) instead.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE tracks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        path        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        title       TEXT NOT NULL,
        artist      TEXT NOT NULL DEFAULT '',
        album       TEXT NOT NULL DEFAULT '',
        duration_ms INTEGER NOT NULL DEFAULT 0,
        added_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE tracks ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0;
    """,
    """
    CREATE TABLE videos (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        path     TEXT NOT NULL UNIQUE COLLATE NOCASE,
        title    TEXT NOT NULL,
        added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE playlists (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE playlist_tracks (
        playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
        track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
        position    INTEGER NOT NULL,
        PRIMARY KEY (playlist_id, track_id),
        UNIQUE (playlist_id, position)
    );
    """,
    """
    ALTER TABLE videos ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0;
    """,
]


class Database:
    def __init__(self, path: Path | str) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for target, script in enumerate(MIGRATIONS[version:], start=version + 1):
            try:
                self._conn.executescript(
                    f"BEGIN; {script} PRAGMA user_version = {target}; COMMIT;"
                )
            except sqlite3.Error:
                self._conn.rollback()
                raise
