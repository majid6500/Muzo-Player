from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtCore import QObject, Signal

from app.config import is_video_supported
from app.data.video_repository import VideoRepository
from app.models import NewVideo, Video
from app.workers.video_scan_worker import VideoScanWorker


class VideoLibraryService(QObject):
    videos_changed = Signal()
    import_started = Signal()
    import_progress = Signal(int)
    import_finished = Signal(int, int, int)  # added, duplicates, unreadable
    error_occurred = Signal(str)

    def __init__(
        self, repository: VideoRepository, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._videos: list[Video] = []
        self._worker: VideoScanWorker | None = None
        self._added = 0
        self._duplicates = 0
        self._unreadable = 0
        self.refresh()

    def videos(self) -> list[Video]:
        return list(self._videos)

    def get_video(self, video_id: int) -> Video | None:
        return next((video for video in self._videos if video.id == video_id), None)

    @property
    def is_importing(self) -> bool:
        return self._worker is not None

    def add_files(self, paths: Iterable[str]) -> None:
        if self._reject_if_busy():
            return
        known_paths = {
            os.path.normcase(os.path.abspath(video.path)) for video in self._videos
        }
        new_paths = [
            Path(path) for path in paths
            if os.path.normcase(os.path.abspath(path)) not in known_paths
        ]
        if new_paths:
            self._start_import(VideoScanWorker(files=new_paths))

    def add_folder(self, folder: str) -> None:
        if self._reject_if_busy():
            return
        path = Path(folder)
        if not path.is_dir():
            self.error_occurred.emit(f"Folder not found: {folder}")
            return
        self._start_import(VideoScanWorker(folder=path))

    def remove_many(self, video_ids: Sequence[int]) -> None:
        if not video_ids:
            return
        try:
            self._repository.delete_many(video_ids)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not remove videos: {exc}")
            return
        self.refresh()

    def set_favorite(self, video_id: int, is_favorite: bool) -> None:
        self.set_favorites([video_id], is_favorite)

    def set_favorites(self, video_ids: Sequence[int], is_favorite: bool) -> None:
        if not video_ids:
            return
        try:
            self._repository.set_favorites(video_ids, is_favorite)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not update video favorite: {exc}")
            return
        self.refresh()

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.requestInterruption()
            self._worker.wait()

    def refresh(self) -> None:
        try:
            self._videos = self._repository.list_all()
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not read videos: {exc}")
            self._videos = []
        self.videos_changed.emit()

    def _reject_if_busy(self) -> bool:
        if self.is_importing:
            self.error_occurred.emit("A video import is already in progress.")
            return True
        return False

    def _start_import(self, worker: VideoScanWorker) -> None:
        self._added = 0
        self._duplicates = 0
        worker.batch_ready.connect(self._on_batch)
        worker.progress.connect(self.import_progress)
        worker.scan_done.connect(self._on_scan_done)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.import_started.emit()
        worker.start()

    def _on_batch(self, batch: list[NewVideo]) -> None:
        try:
            added = self._repository.add_many(batch)
            self._added += added
            self._duplicates += len(batch) - added
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not save videos: {exc}")

    def _on_scan_done(self, unreadable: int) -> None:
        self._unreadable = unreadable
        self.refresh()

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
            self.import_finished.emit(
                self._added, self._duplicates, self._unreadable
            )