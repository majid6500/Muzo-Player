"""Finding audio files on disk."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from app.config import is_supported, is_video_supported


def iter_audio_files(folder: Path) -> Iterator[Path]:
    """Yield supported audio files under folder, recursively.

    Unreadable sub-folders are skipped silently (os.walk default).
    """
    for directory, _subdirs, filenames in os.walk(folder):
        for name in filenames:
            if is_supported(name):
                yield Path(directory) / name


def iter_video_files(folder: Path) -> Iterator[Path]:
    """Yield supported video files under folder, recursively."""
    for directory, _subdirs, filenames in os.walk(folder):
        for name in filenames:
            if is_video_supported(name):
                yield Path(directory) / name
