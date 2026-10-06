"""Playlist operations and error reporting, independent of the UI."""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from PySide6.QtCore import QObject, Signal

from app.data.playlist_repository import PlaylistRepository
from app.models import Playlist


class PlaylistService(QObject):
    playlists_changed = Signal()
    error_occurred = Signal(str)

    def __init__(
        self, repository: PlaylistRepository, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._repository = repository

    def playlists(self) -> list[Playlist]:
        try:
            return self._repository.list_all()
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not read playlists: {exc}")
            return []

    def track_ids(self, playlist_id: int) -> list[int]:
        try:
            return self._repository.list_track_ids(playlist_id)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not read playlist tracks: {exc}")
            return []

    def create(self, name: str) -> Playlist | None:
        normalized = name.strip()
        if not normalized:
            self.error_occurred.emit("Playlist name cannot be empty.")
            return None
        try:
            playlist = self._repository.create(normalized)
        except sqlite3.IntegrityError:
            self.error_occurred.emit("A playlist with that name already exists.")
            return None
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not create playlist: {exc}")
            return None
        self.playlists_changed.emit()
        return playlist

    def rename(self, playlist_id: int, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            self.error_occurred.emit("Playlist name cannot be empty.")
            return False
        try:
            self._repository.rename(playlist_id, normalized)
        except sqlite3.IntegrityError:
            self.error_occurred.emit("A playlist with that name already exists.")
            return False
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not rename playlist: {exc}")
            return False
        self.playlists_changed.emit()
        return True

    def delete(self, playlist_id: int) -> bool:
        try:
            self._repository.delete(playlist_id)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not delete playlist: {exc}")
            return False
        self.playlists_changed.emit()
        return True

    def add_tracks(self, playlist_id: int, track_ids: Sequence[int]) -> int | None:
        if not track_ids:
            return 0
        try:
            added = self._repository.add_tracks(playlist_id, track_ids)
        except ValueError as exc:
            self.error_occurred.emit(str(exc))
            return None
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not add songs to playlist: {exc}")
            return None
        if added:
            self.playlists_changed.emit()
        return added

    def remove_track(self, playlist_id: int, track_id: int) -> bool:
        try:
            self._repository.remove_track(playlist_id, track_id)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not remove song from playlist: {exc}")
            return False
        self.playlists_changed.emit()
        return True

    def set_track_order(
        self, playlist_id: int, track_ids: Sequence[int]
    ) -> bool:
        try:
            self._repository.set_track_order(playlist_id, track_ids)
        except ValueError as exc:
            self.error_occurred.emit(str(exc))
            return False
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not reorder playlist: {exc}")
            return False
        self.playlists_changed.emit()
        return True
