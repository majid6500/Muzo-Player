from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.config import is_video_supported
from app.core.scanner import iter_video_files
from app.models import NewVideo

VIDEO_BATCH_SIZE = 100
PROGRESS_EVERY = 20


class VideoScanWorker(QThread):
    batch_ready = Signal(list)
    progress = Signal(int)
    scan_done = Signal(int)

    def __init__(
        self, *, files: list[Path] | None = None, folder: Path | None = None
    ) -> None:
        super().__init__()
        self._files = files or []
        self._folder = folder

    def run(self) -> None:
        batch: list[NewVideo] = []
        unreadable = processed = 0
        for path in self._candidates():
            if self.isInterruptionRequested():
                break
            processed += 1
            if not is_video_supported(path) or not path.is_file():
                unreadable += 1
            else:
                resolved = path.resolve()
                batch.append(NewVideo(str(resolved), resolved.stem))
                if len(batch) >= VIDEO_BATCH_SIZE:
                    self.batch_ready.emit(batch)
                    batch = []
            if processed % PROGRESS_EVERY == 0:
                self.progress.emit(processed)

        if batch:
            self.batch_ready.emit(batch)
        self.scan_done.emit(unreadable)

    def _candidates(self):
        if self._folder is not None:
            return iter_video_files(self._folder)
        return iter(self._files)