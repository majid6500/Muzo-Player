"""Background extraction of embedded track artwork."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from app.core.metadata import read_cover


class CoverWorker(QRunnable):
    def __init__(self, track_id: int, path: Path) -> None:
        super().__init__()
        self._track_id = track_id
        self._path = path
        self._signals = _CoverSignals()

    @property
    def loaded(self):
        return self._signals.loaded

    def run(self) -> None:
        self._signals.loaded.emit(self._track_id, read_cover(self._path))


class _CoverSignals(QObject):
    loaded = Signal(int, object)