from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QFileDialog, QInputDialog,
    QLineEdit, QMainWindow, QMenu, QPlainTextEdit, QStackedWidget, QTextEdit,
)

from app.config import APP_NAME, app_icon_path
from app.core.audio_backend import PlaybackState
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.core.playlist_service import PlaylistService
from app.core.video_library_service import VideoLibraryService
from app.core.vlc_video_backend import VlcVideoBackend
from app.data.settings_repository import SettingsRepository
from app.models import Track
from app.ui.screens.home_screen import HomeScreen
from app.ui.screens.play_screen import PlayScreen
from app.ui.screens.video_screen import VideoScreen
from app.ui.theme import theme
from app.ui.theme.window_chrome import apply_native_titlebar_theme
from app.ui.widgets.toast import Toast
from app.utils.formatting import plural

HOME = "home"
PLAY = "play"


class MainWindow(QMainWindow):
    """Owns navigation and app-wide notifications. Add new screens to _screens."""

    def __init__(
        self, library: LibraryService, video_library: VideoLibraryService,
        player: PlayerService, settings: SettingsRepository,
        playlists: PlaylistService,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._player = player
        self._playlists = playlists
        self._video_library = video_library
        self._video_screen: VideoScreen | None = None
        self._current_video_path: str | None = None
        self._resume_audio_after_video = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.resize(1180, 720)
        self.setMinimumSize(980, 580)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._screens = {
            HOME: HomeScreen(library, video_library, player, playlists),
            PLAY: PlayScreen(library, player),
        }
        for screen in self._screens.values():
            self._stack.addWidget(screen)

        self._toast = Toast(self)

        self._playback_shortcuts = [
            QShortcut(QKeySequence(Qt.Key.Key_Space), self),
            QShortcut(QKeySequence(Qt.Key.Key_Minus), self),
        ]
        for shortcut in self._playback_shortcuts:
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self._toggle_playback_shortcut)

        self._screens[HOME].open_play_requested.connect(lambda: self.navigate(PLAY))
        self._screens[HOME].open_video_requested.connect(self._choose_video)
        self._screens[HOME].open_video_path_requested.connect(self._open_video_path)
        self._screens[HOME].accent_color_selected.connect(self._apply_accent_color)
        self._screens[HOME].add_to_playlist_requested.connect(
            self._choose_playlist_for_tracks
        )
        self._screens[PLAY].back_requested.connect(lambda: self.navigate(HOME))
        player.error_occurred.connect(lambda msg: self._toast.show_message(msg, error=True))
        player.current_track_changed.connect(self._on_current_track_changed)
        library.error_occurred.connect(lambda msg: self._toast.show_message(msg, error=True))
        playlists.error_occurred.connect(
            lambda message: self._toast.show_message(message, error=True)
        )
        library.import_finished.connect(self._on_import_finished)
        video_library.error_occurred.connect(
            lambda message: self._toast.show_message(message, error=True)
        )
        video_library.import_finished.connect(self._on_video_import_finished)

        self.navigate(HOME)

    def _choose_playlist_for_tracks(self, track_ids: list[int]) -> None:
        if not track_ids:
            return
        available = self._playlists.playlists()
        menu = QMenu(self)
        for playlist in available:
            action = menu.addAction(playlist.name)
            action.triggered.connect(
                lambda _checked=False, playlist_id=playlist.id: (
                    self._add_tracks_to_playlist(playlist_id, track_ids)
                )
            )
        if available:
            menu.addSeparator()
        create_action = menu.addAction("New playlist...")
        create_action.triggered.connect(
            lambda: self._create_playlist_for_tracks(track_ids)
        )
        menu.exec(QCursor.pos())

    def _create_playlist_for_tracks(self, track_ids: list[int]) -> None:
        name, accepted = QInputDialog.getText(
            self, "New playlist", "Playlist name:"
        )
        if not accepted:
            return
        playlist = self._playlists.create(name)
        if playlist is not None:
            self._add_tracks_to_playlist(playlist.id, track_ids)

    def _add_tracks_to_playlist(
        self, playlist_id: int, track_ids: list[int]
    ) -> None:
        added = self._playlists.add_tracks(playlist_id, track_ids)
        if added is None:
            return
        playlist = next(
            (item for item in self._playlists.playlists() if item.id == playlist_id),
            None,
        )
        if added and playlist is not None:
            self._toast.show_message(
                f"Added {plural(added, 'song')} to “{playlist.name}”."
            )
        elif playlist is not None:
            self._toast.show_message("Those songs are already in this playlist.")

    def navigate(self, name: str) -> None:
        self._stack.setCurrentWidget(self._screens[name])

    def _toggle_playback_shortcut(self) -> None:
        if self._video_screen is not None and self._stack.currentWidget() is self._video_screen:
            self._video_screen.toggle_play_pause()
            return
        focus = QApplication.focusWidget()
        text_controls = (QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit)
        if isinstance(focus, text_controls):
            return
        self._player.toggle_play_pause()

    def _choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open video",
            "",
            "Video files (*.mp4 *.mkv *.avi *.mov *.wmv *.webm *.mpeg *.mpg *.m4v);;All files (*)",
        )
        if not path:
            return

        self._open_video_path(path)

    def _open_video_path(self, path: str) -> None:
        self._video_library.add_files([path])
        if self._video_screen is None:
            try:
                self._video_screen = VideoScreen(VlcVideoBackend(), self)
            except RuntimeError as exc:
                self._toast.show_message(str(exc), error=True)
                return
            self._video_screen.back_requested.connect(self._close_video)
            self._video_screen.error_occurred.connect(
                lambda message: self._toast.show_message(message, error=True)
            )
            self._video_screen.playback_state_changed.connect(
                self._on_video_playback_state_changed
            )
            self._stack.addWidget(self._video_screen)

        self._resume_audio_after_video |= self._player.state is PlaybackState.PLAYING
        if self._player.state is PlaybackState.PLAYING:
            self._player.pause()
        self._stack.setCurrentWidget(self._video_screen)
        if not self._video_screen.open_file(path):
            self._video_screen.close_video()
        else:
            self._current_video_path = self._video_screen.current_path
            self._screens[HOME].set_video_playback(self._current_video_path, True)

    def _close_video(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        self._stack.setCurrentWidget(self._screens[HOME])
        self._screens[HOME].set_video_playback(self._current_video_path, False)
        if self._resume_audio_after_video:
            self._player.play()
        self._resume_audio_after_video = False

    def _on_video_playback_state_changed(self, state: PlaybackState) -> None:
        if self._video_screen is not None:
            self._screens[HOME].set_video_playback(
                self._video_screen.current_path,
                state is PlaybackState.PLAYING,
            )

    def shutdown(self) -> None:
        if self._video_screen is not None:
            self._video_screen.shutdown()

    def _on_video_import_finished(
        self, added: int, duplicates: int, unreadable: int
    ) -> None:
        self._toast.show_message(
            f"Videos: {added} added, {duplicates} already in library, "
            f"{unreadable} unsupported or unreadable.",
            error=unreadable > 0 and added == 0,
        )

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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_native_titlebar_theme(self)

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
