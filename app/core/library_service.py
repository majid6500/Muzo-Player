"""The music library: storage, importing and lookups. No UI code."""
from __future__ import annotations

import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtCore import QObject, QThreadPool, Signal

from app.data.track_repository import TrackRepository
from app.models import NewTrack, Track
from app.workers.cover_worker import CoverWorker
from app.workers.scan_worker import ScanWorker

MAX_CACHED_COVERS = 16


class LibraryService(QObject):
    library_changed = Signal()
    import_started = Signal()
    import_progress = Signal(int)
    import_finished = Signal(int, int, int, int)  # added, duplicates, unreadable, failed to save
    error_occurred = Signal(str)
    cover_loaded = Signal(int, object)  # track id, image bytes or None

    def __init__(self, repository: TrackRepository, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._tracks: list[Track] = []
        self._by_id: dict[int, Track] = {}
        self._worker: ScanWorker | None = None
        self._added = 0
        self._duplicates = 0
        self._save_failures = 0
        self._cover_pool = QThreadPool(self)
        self._cover_pool.setMaxThreadCount(2)
        self._cover_cache: OrderedDict[int, bytes | None] = OrderedDict()
        self._cover_workers: dict[int, CoverWorker] = {}
        self.refresh()

    # ---- queries ----
    def tracks(self) -> list[Track]:
        return self._tracks

    def get_track(self, track_id: int) -> Track | None:
        return self._by_id.get(track_id)

    def get_cover(self, track_id: int) -> bytes | None:
        if track_id in self._cover_cache:
            self._cover_cache.move_to_end(track_id)
            return self._cover_cache[track_id]
        if track_id in self._cover_workers:
            return None
        track = self.get_track(track_id)
        if track is not None:
            worker = CoverWorker(track_id, Path(track.path))
            worker.loaded.connect(self._on_cover_loaded)
            self._cover_workers[track_id] = worker
            self._cover_pool.start(worker)
        return None

    @property
    def is_importing(self) -> bool:
        return self._worker is not None

    # ---- commands ----
    def refresh(self) -> None:
        try:
            self._tracks = self._repository.list_all()
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not read the library: {exc}")
            self._tracks = []
        self._by_id = {track.id: track for track in self._tracks}
        self.library_changed.emit()

    def add_files(self, paths: Iterable[str]) -> None:
        if self._reject_if_busy():
            return
        files = [Path(p) for p in paths]
        if files:
            self._start_import(ScanWorker(files=files))

    def add_folder(self, folder: str) -> None:
        if self._reject_if_busy():
            return
        path = Path(folder)
        if not path.is_dir():
            self.error_occurred.emit(f"Folder not found: {folder}")
            return
        self._start_import(ScanWorker(folder=path))

    def remove_tracks(self, track_ids: Sequence[int]) -> None:
        try:
            self._repository.delete_many(track_ids)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not remove songs: {exc}")
            return
        self.refresh()

    def set_favorite(self, track_id: int, is_favorite: bool) -> None:
        self.set_favorites([track_id], is_favorite)

    def set_favorites(self, track_ids: Sequence[int], is_favorite: bool) -> None:
        if not track_ids:
            return
        try:
            self._repository.set_favorites(track_ids, is_favorite)
        except sqlite3.Error as exc:
            self.error_occurred.emit(f"Could not update favorite: {exc}")
            return
        self.refresh()

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.requestInterruption()
            self._worker.wait()
        self._cover_pool.waitForDone()

    # ---- import plumbing ----
    def _reject_if_busy(self) -> bool:
        if self.is_importing:
            self.error_occurred.emit("An import is already in progress.")
            return True
        return False

    def _start_import(self, worker: ScanWorker) -> None:
        self._added = 0
        self._duplicates = 0
        self._save_failures = 0
        worker.batch_ready.connect(self._on_batch)
        worker.progress.connect(self.import_progress)
        worker.scan_done.connect(self._on_scan_done)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.import_started.emit()
        worker.start()

    def _on_batch(self, batch: list[NewTrack]) -> None:
        try:
            added = self._repository.add_many(batch)
            self._added += added
            self._duplicates += len(batch) - added
        except sqlite3.Error as exc:
            self._save_failures += len(batch)
            self.error_occurred.emit(f"Could not save songs: {exc}")

    def _on_cover_loaded(self, track_id: int, data: bytes | None) -> None:
        self._cover_workers.pop(track_id, None)
        if track_id not in self._by_id:
            return
        self._cover_cache[track_id] = data
        self._cover_cache.move_to_end(track_id)
        if len(self._cover_cache) > MAX_CACHED_COVERS:
            self._cover_cache.popitem(last=False)
        self.cover_loaded.emit(track_id, data)

    def _on_scan_done(self, readable: int, unreadable: int) -> None:
        self.refresh()
        self.import_finished.emit(
            self._added, self._duplicates, unreadable, self._save_failures
        )

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
