"""Background thread that reads metadata so the UI never freezes."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.config import is_supported
from app.core.metadata import read_metadata
from app.core.scanner import iter_audio_files
from app.models import NewTrack

BATCH_SIZE = 50
PROGRESS_EVERY = 20


class ScanWorker(QThread):
    batch_ready = Signal(list)       # list[NewTrack]
    progress = Signal(int)           # files processed so far
    scan_done = Signal(int, int)     # readable, unreadable

    def __init__(self, *, files: list[Path] | None = None, folder: Path | None = None) -> None:
        super().__init__()
        self._files = files or []
        self._folder = folder

    def run(self) -> None:
        batch: list[NewTrack] = []
        readable = unreadable = processed = 0

        for path in self._candidates():
            if self.isInterruptionRequested():
                break
            processed += 1
            track = read_metadata(path) if is_supported(path) else None
            if track is None:
                unreadable += 1
            else:
                readable += 1
                batch.append(track)
                if len(batch) >= BATCH_SIZE:
                    self.batch_ready.emit(batch)
                    batch = []
            if processed % PROGRESS_EVERY == 0:
                self.progress.emit(processed)

        if batch:
            self.batch_ready.emit(batch)
        self.scan_done.emit(readable, unreadable)

    def _candidates(self):
        if self._folder is not None:
            return iter_audio_files(self._folder)
        return iter(self._files)
