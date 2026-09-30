from __future__ import annotations

import sqlite3
from typing import Iterable, Sequence

from app.data.database import Database
from app.models import NewVideo, Video


def _to_video(row: sqlite3.Row) -> Video:
    return Video(id=row["id"], path=row["path"], title=row["title"])


class VideoRepository:
    def __init__(self, database: Database) -> None:
        self._conn = database.connection

    def list_all(self) -> list[Video]:
        rows = self._conn.execute(
            "SELECT id, path, title FROM videos "
            "ORDER BY title COLLATE NOCASE, id"
        ).fetchall()
        return [_to_video(row) for row in rows]

    def add_many(self, videos: Iterable[NewVideo]) -> int:
        rows = [(video.path, video.title) for video in videos]
        before = self._conn.total_changes
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO videos (path, title) VALUES (?, ?)", rows
            )
        return self._conn.total_changes - before

    def delete_many(self, video_ids: Sequence[int]) -> None:
        with self._conn:
            self._conn.executemany(
                "DELETE FROM videos WHERE id = ?", [(video_id,) for video_id in video_ids]
            )