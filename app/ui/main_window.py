from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from app.config import APP_NAME
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.data.settings_repository import SettingsRepository
from app.models import Track
from app.ui.screens.home_screen import HomeScreen
from app.ui.screens.play_screen import PlayScreen
from app.ui.theme import theme
from app.ui.widgets.toast import Toast
from app.utils.formatting import plural

HOME = "home"
PLAY = "play"


class MainWindow(QMainWindow):
    """Owns navigation and app-wide notifications. Add new screens to _screens."""

    def __init__(
        self, library: LibraryService, player: PlayerService,
        settings: SettingsRepository,
    ) -> None:
        super().__init__()
        self._settings = settings
        self.setWindowTitle(APP_NAME)
        self.resize(1040, 720)
        self.setMinimumSize(760, 580)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._screens = {
            HOME: HomeScreen(library, player),
            PLAY: PlayScreen(library, player),
        }
        for screen in self._screens.values():
            self._stack.addWidget(screen)

        self._toast = Toast(self)

        self._screens[HOME].open_play_requested.connect(lambda: self.navigate(PLAY))
        self._screens[HOME].accent_color_selected.connect(self._apply_accent_color)
        self._screens[PLAY].back_requested.connect(lambda: self.navigate(HOME))
        player.error_occurred.connect(lambda msg: self._toast.show_message(msg, error=True))
        player.current_track_changed.connect(self._on_current_track_changed)
        library.error_occurred.connect(lambda msg: self._toast.show_message(msg, error=True))
        library.import_finished.connect(self._on_import_finished)

        self.navigate(HOME)

    def navigate(self, name: str) -> None:
        self._stack.setCurrentWidget(self._screens[name])

    def _apply_accent_color(self, value: str) -> None:
        previous = theme.value("accent")
        if not theme.set_accent_color(value):
            return
        try:
            self._settings.set("accent_color", theme.value("accent"))
        except sqlite3.Error as exc:
            theme.set_accent_color(previous)
            self._refresh_theme()
            self._toast.show_message(f"Could not save accent color: {exc}", error=True)
            return
        self._refresh_theme()

    def _refresh_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.load_stylesheet())
        self._screens[HOME].refresh_theme()
        self._screens[PLAY].refresh_theme()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._toast.reposition()

    def _on_current_track_changed(self, track: Track | None) -> None:
        # The playing song was removed while on the Play screen.
        if track is None and self._stack.currentWidget() is self._screens[PLAY]:
            self.navigate(HOME)

    def _on_import_finished(
        self, added: int, duplicates: int, unreadable: int, save_failures: int
    ) -> None:
        parts = []
        if added:
            parts.append(f"Added {plural(added, 'song')}")
        if duplicates:
            parts.append(f"{duplicates} already in the library")
        if unreadable:
            parts.append(f"{unreadable} unreadable or unsupported")
        if save_failures:
            parts.append(f"{save_failures} could not be saved")
        if not parts:
            self._toast.show_message("No supported audio files (MP3, WAV, OGG) were found.", error=True)
            return
        self._toast.show_message(", ".join(parts) + ".", error=added == 0 or save_failures > 0)
