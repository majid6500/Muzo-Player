"""SQLite persistence for playlists and their ordered track membership."""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from app.data.database import Database
from app.models import Playlist


class PlaylistRepository:
    def __init__(self, database: Database) -> None:
        self._conn = database.connection

    def list_all(self) -> list[Playlist]:
        rows = self._conn.execute(
            "SELECT id, name FROM playlists ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [Playlist(row["id"], row["name"]) for row in rows]

    def get(self, playlist_id: int) -> Playlist | None:
        row = self._conn.execute(
            "SELECT id, name FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        return Playlist(row["id"], row["name"]) if row else None

    def create(self, name: str) -> Playlist:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO playlists (name) VALUES (?)", (name,)
            )
        return Playlist(cursor.lastrowid, name)

    def rename(self, playlist_id: int, name: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE playlists SET name = ? WHERE id = ?",
                (name, playlist_id),
            )

    def delete(self, playlist_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def list_track_ids(self, playlist_id: int) -> list[int]:
        rows = self._conn.execute(
            "SELECT track_id FROM playlist_tracks "
            "WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        return [row["track_id"] for row in rows]

    def add_tracks(self, playlist_id: int, track_ids: Sequence[int]) -> int:
        if self.get(playlist_id) is None:
            raise ValueError("Playlist no longer exists.")
        added = 0
        with self._conn:
            for track_id in dict.fromkeys(track_ids):
                cursor = self._conn.execute(
                    "INSERT OR IGNORE INTO playlist_tracks "
                    "(playlist_id, track_id, position) "
                    "SELECT ?, id, COALESCE(("
                    "SELECT MAX(position) + 1 FROM playlist_tracks "
                    "WHERE playlist_id = ?), 0) "
                    "FROM tracks WHERE id = ?",
                    (playlist_id, playlist_id, track_id),
                )
                added += cursor.rowcount
        return added

    def remove_track(self, playlist_id: int, track_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            self._normalize_positions(playlist_id)

    def set_track_order(self, playlist_id: int, track_ids: Sequence[int]) -> None:
        expected = set(self.list_track_ids(playlist_id))
        if len(track_ids) != len(expected) or set(track_ids) != expected:
            raise ValueError(
                "Playlist order must contain each playlist track exactly once."
            )
        with self._conn:
            self._conn.executemany(
                "UPDATE playlist_tracks SET position = ? "
                "WHERE playlist_id = ? AND track_id = ?",
                [
                    (index - len(track_ids), playlist_id, track_id)
                    for index, track_id in enumerate(track_ids)
                ],
            )
            self._conn.executemany(
                "UPDATE playlist_tracks SET position = ? "
                "WHERE playlist_id = ? AND track_id = ?",
                [
                    (index, playlist_id, track_id)
                    for index, track_id in enumerate(track_ids)
                ],
            )

    def _normalize_positions(self, playlist_id: int) -> None:
        rows = self._conn.execute(
            "SELECT track_id FROM playlist_tracks "
            "WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        self._conn.executemany(
            "UPDATE playlist_tracks SET position = ? "
            "WHERE playlist_id = ? AND track_id = ?",
            [
                (index, playlist_id, row["track_id"])
                for index, row in enumerate(rows)
            ],
        )
