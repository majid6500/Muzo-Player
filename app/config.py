"""Application-wide constants and paths."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Muzo Player"
DATA_FOLDER_NAME = "MusicPlayer"

# To support another format, add its extension here. mutagen reads the tags
# and QtMultimedia (FFmpeg backend) plays it, e.g. ".flac", ".m4a".
SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".ogg"})
VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".mpeg", ".mpg", ".m4v",
})


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def is_video_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def file_dialog_filter() -> str:
    patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
    return f"Audio files ({patterns});;All files (*)"


def media_file_dialog_filter() -> str:
    audio_patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
    video_patterns = " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))
    return (
        f"Media files ({audio_patterns} {video_patterns});;"
        f"Audio files ({audio_patterns});;Video files ({video_patterns});;All files (*)"
    )


def data_directory() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / DATA_FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def database_path() -> Path:
    return data_directory() / "library.db"
