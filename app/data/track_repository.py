from __future__ import annotations

import sqlite3
from typing import Iterable, Sequence

from app.data.database import Database
from app.models import NewTrack, Track

_COLUMNS = "id, path, title, artist, album, duration_ms, is_favorite"


def _to_track(row: sqlite3.Row) -> Track:
    return Track(
        id=row["id"],
        path=row["path"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        duration_ms=row["duration_ms"],
        is_favorite=bool(row["is_favorite"]),
    )


class TrackRepository:
    def __init__(self, database: Database) -> None:
        self._conn = database.connection

    def list_all(self) -> list[Track]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM tracks "
            "ORDER BY title COLLATE NOCASE, artist COLLATE NOCASE, id"
        ).fetchall()
        return [_to_track(row) for row in rows]

    def add_many(self, items: Iterable[NewTrack]) -> int:
        """Insert tracks, skipping paths that already exist. Returns rows added."""
        rows = [
            (t.path, t.title, t.artist, t.album, t.duration_ms) for t in items
        ]
        before = self._conn.total_changes
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO tracks (path, title, artist, album, duration_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return self._conn.total_changes - before

    def delete_many(self, track_ids: Sequence[int]) -> None:
        with self._conn:
            self._conn.executemany(
                "DELETE FROM tracks WHERE id = ?", [(i,) for i in track_ids]
            )

    def set_favorite(self, track_id: int, is_favorite: bool) -> None:
        self.set_favorites([track_id], is_favorite)

    def set_favorites(self, track_ids: Sequence[int], is_favorite: bool) -> None:
        with self._conn:
            self._conn.executemany(
                "UPDATE tracks SET is_favorite = ? WHERE id = ?",
                [(int(is_favorite), track_id) for track_id in track_ids],
            )
