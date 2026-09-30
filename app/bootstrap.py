"""Creates every component and wires them together (the only place that does)."""
from __future__ import annotations

import sqlite3
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import config
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.core.playback_queue import PlaybackQueue
from app.core.vlc_audio_backend import VlcAudioBackend
from app.core.video_library_service import VideoLibraryService
from app.data.database import Database
from app.data.settings_repository import SettingsRepository
from app.data.track_repository import TrackRepository
from app.data.video_repository import VideoRepository
from app.ui.main_window import MainWindow
from app.ui.theme import theme


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setStyle("Fusion")

    try:
        database = Database(config.database_path())
    except (sqlite3.Error, OSError) as exc:
        QMessageBox.critical(
            None, config.APP_NAME,
            f"The library database could not be opened:\n{config.database_path()}\n\n{exc}",
        )
        return 1

    settings = SettingsRepository(database)
    stored_accent = settings.get("accent_color", theme.DEFAULT_ACCENT)
    if stored_accent:
        theme.set_accent_color(stored_accent)
    app.setStyleSheet(theme.load_stylesheet())

    try:
        backend = VlcAudioBackend()
    except RuntimeError as exc:
        database.close()
        QMessageBox.critical(None, config.APP_NAME, str(exc))
        return 1

    library = LibraryService(TrackRepository(database))
    video_library = VideoLibraryService(VideoRepository(database))
    player = PlayerService(backend, library, PlaybackQueue(), settings)
    player.restore_session()
    window = MainWindow(library, video_library, player, settings)

    def shutdown() -> None:
        library.shutdown()
        video_library.shutdown()
        player.save_state()
        window.shutdown()
        backend.shutdown()
        database.close()

    app.aboutToQuit.connect(shutdown)
    window.show()
    return app.exec()
