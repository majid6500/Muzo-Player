from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QObject, QEventLoop, QItemSelectionModel, QPoint, Qt, Signal, QTimer,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.audio_backend import PlaybackState
from app.core.playback_queue import PlaybackQueue
from app.core.player_service import PlayerService
from app.core.video_library_service import VideoLibraryService
from app.data.database import Database
from app.data.video_repository import VideoRepository
from app.models import Track
from app.ui.main_window import MainWindow
from tests.test_playback import FakeAudioBackend, FakeSettings
from app.ui.widgets.track_list import IsCurrentRole, IsPlayingRole, TrackDelegate, VideoRole


class FakeLibrary(QObject):
    library_changed = Signal()
    import_started = Signal()
    import_progress = Signal(int)
    import_finished = Signal(int, int, int, int)
    error_occurred = Signal(str)
    cover_loaded = Signal(int, object)

    def __init__(self, tracks: list[Track]) -> None:
        super().__init__()
        self._tracks = tracks

    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def get_track(self, track_id: int) -> Track | None:
        return next((track for track in self._tracks if track.id == track_id), None)

    def get_cover(self, _track_id: int) -> None:
        return None

    def add_folder(self, _folder: str) -> None:
        pass

    def add_files(self, _paths) -> None:
        pass


class FakeVideoBackend(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(object)
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._state = PlaybackState.STOPPED
        self.toggle_count = 0
        self.stopped = False
        self.added_subtitles: list[str] = []
        self.subtitles_disabled = 0

    @property
    def state(self) -> PlaybackState:
        return self._state

    def open(self, _path: str, _window_id: int) -> bool:
        self._state = PlaybackState.PLAYING
        return True

    def set_volume(self, _volume: float) -> None:
        pass

    def add_subtitle(self, path: str) -> bool:
        self.added_subtitles.append(path)
        return True

    def disable_subtitles(self) -> bool:
        self.subtitles_disabled += 1
        return True

    def toggle_play_pause(self) -> None:
        self.toggle_count += 1
        self._state = (
            PlaybackState.PAUSED
            if self._state is PlaybackState.PLAYING
            else PlaybackState.PLAYING
        )

    def stop(self) -> None:
        self.stopped = True
        self._state = PlaybackState.STOPPED

    def seek(self, _position_ms: int) -> None:
        pass

    def shutdown(self) -> None:
        self.stop()


class VideoLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        audio_path = Path(self.temp_dir.name) / "music.mp3"
        audio_path.touch()
        video_path = Path(self.temp_dir.name) / "movie.mp4"
        video_path.touch()
        self.video_path = str(video_path)
        track = Track(1, str(audio_path), "Music", "Artist", "Album", 1000)
        self.library = FakeLibrary([track])
        self.database = Database(Path(self.temp_dir.name) / "library.db")
        self.video_library = VideoLibraryService(VideoRepository(self.database))
        self.audio_backend = FakeAudioBackend()
        self.player = PlayerService(
            self.audio_backend, self.library, PlaybackQueue(), FakeSettings()
        )
        self.addCleanup(self.database.close)
        self.addCleanup(self.video_library.shutdown)

    def _open_video(self) -> MainWindow:
        window = MainWindow(
            self.library, self.video_library, self.player, FakeSettings()
        )
        self.addCleanup(window.shutdown)
        with (
            patch(
                "app.ui.main_window.QFileDialog.getOpenFileName",
                return_value=(self.video_path, ""),
            ),
            patch("app.ui.main_window.VlcVideoBackend", FakeVideoBackend),
        ):
            window._choose_video()
        return window

    def _wait_for_video_import(self, action) -> None:
        loop = QEventLoop()
        self.video_library.import_finished.connect(loop.quit)
        action()
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        self.video_library.import_finished.disconnect(loop.quit)

    def test_home_screen_routes_video_add_open_and_remove_actions(self) -> None:
        window = MainWindow(
            self.library, self.video_library, self.player, FakeSettings()
        )
        self.addCleanup(window.shutdown)
        home = window._screens["home"]
        self.assertEqual(
            [home._filter_tabs.tabText(index) for index in range(3)],
            ["All songs", "All videos", "Favorites"],
        )
        self.assertEqual(window.width(), 1180)
        self.assertEqual(window.minimumWidth(), 980)
        video_path = Path(self.temp_dir.name) / "library-video.mp4"
        video_path.touch()
        with patch(
            "app.ui.screens.home_screen.QFileDialog.getOpenFileNames",
            return_value=([str(video_path)], ""),
        ):
            self._wait_for_video_import(home._choose_files)

        self.assertEqual(len(self.video_library.videos()), 1)
        home._filter_tabs.setCurrentIndex(1)
        video_list = home._video_list
        self.assertIsInstance(video_list.itemDelegate(), TrackDelegate)
        self.assertEqual(home._video_model.rowCount(), 1)
        self.assertEqual(home._filter_tabs.tabText(1), "All videos")
        index = home._video_model.index(0)
        self.assertTrue(index.data(VideoRole))
        video_list.selectionModel().select(
            index,
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        video_list.setCurrentIndex(index)
        self.assertTrue(home._remove_button.isEnabled())
        opened_paths: list[str] = []
        home.open_video_path_requested.connect(opened_paths.append)
        home._video_button.click()
        self.assertEqual(opened_paths, [str(video_path.resolve())])
        home.set_video_playback(str(video_path.resolve()), True)
        self.assertTrue(index.data(IsCurrentRole))
        self.assertTrue(index.data(IsPlayingRole))
        home.set_video_playback(str(video_path.resolve()), False)
        self.assertFalse(index.data(IsPlayingRole))

        home._remove_button.click()
        self.assertEqual(self.video_library.videos(), [])
        self.assertTrue(video_path.is_file())

        folder = Path(self.temp_dir.name) / "video-folder"
        folder.mkdir()
        folder_video = folder / "folder-video.mkv"
        folder_video.touch()
        with patch(
            "app.ui.screens.home_screen.QFileDialog.getExistingDirectory",
            return_value=str(folder),
        ):
            self._wait_for_video_import(home._choose_folder)

        self.assertEqual(
            [video.title for video in self.video_library.videos()],
            ["folder-video"],
        )

    def test_video_pauses_and_then_resumes_previously_playing_music(self) -> None:
        self.player.play_track(1)

        window = self._open_video()
        self._wait_for_video_import(lambda: None)

        self.assertIs(window._stack.currentWidget(), window._video_screen)
        self.assertEqual(
            [video.path for video in self.video_library.videos()],
            [str(Path(self.video_path).resolve())],
        )
        self.assertEqual(self.player.state, PlaybackState.PAUSED)
        window._toggle_playback_shortcut()
        self.assertEqual(self.player.state, PlaybackState.PAUSED)
        self.assertEqual(window._video_screen._backend.toggle_count, 1)

        window._video_screen.close_video()

        self.assertIs(window._stack.currentWidget(), window._screens["home"])
        self.assertEqual(self.player.state, PlaybackState.PLAYING)

    def test_video_does_not_resume_music_that_was_already_paused(self) -> None:
        self.player.play_track(1)
        self.player.pause()

        window = self._open_video()
        window._video_screen.close_video()

        self.assertEqual(self.player.state, PlaybackState.PAUSED)

    def test_back_from_fullscreen_video_restores_library_window(self) -> None:
        window = self._open_video()
        window.show()
        window.showFullScreen()
        self.app.processEvents()
        self.assertTrue(window.isFullScreen())

        window._video_screen.close_video()
        self.app.processEvents()

        self.assertFalse(window.isFullScreen())
        self.assertIs(window._stack.currentWidget(), window._screens["home"])

    def test_video_loads_sidecar_subtitle_and_supports_manual_off(self) -> None:
        video_path = Path(self.video_path)
        sidecar = video_path.with_suffix(".srt")
        sidecar.touch()
        manual_subtitle = Path(self.temp_dir.name) / "custom.ass"
        manual_subtitle.touch()

        window = self._open_video()
        backend = window._video_screen._backend
        self.assertEqual(backend.added_subtitles, [str(sidecar.resolve())])
        self.assertEqual(window._video_screen._status.text(), "Subtitles: movie.srt")

        with patch(
            "app.ui.screens.video_screen.QFileDialog.getOpenFileName",
            return_value=(str(manual_subtitle), ""),
        ):
            window._video_screen._choose_subtitle()
        self.assertEqual(
            backend.added_subtitles,
            [str(sidecar.resolve()), str(manual_subtitle.resolve())],
        )

        window._video_screen._disable_subtitles()
        self.assertEqual(backend.subtitles_disabled, 1)
        self.assertEqual(window._video_screen._status.text(), "Subtitles off")

    def test_immersive_mode_hides_and_restores_controls(self) -> None:
        window = self._open_video()
        window.show()
        screen = window._video_screen
        window._video_screen._enter_immersive()
        self.app.processEvents()

        self.assertTrue(screen._immersive)
        self.assertTrue(window.isFullScreen())
        self.assertTrue(screen._overlay.isVisible())
        self.assertTrue(screen._back_button.isHidden())
        self.assertTrue(screen._seek.isHidden())

        screen._hide_immersive_controls()
        self.assertFalse(screen._overlay.isVisible())
        with patch(
            "app.ui.screens.video_screen.QCursor.pos",
            return_value=QPoint(100, 100),
        ):
            screen._watch_cursor()
        self.assertTrue(screen._overlay.isVisible())

        screen._overlay._exit.click()
        self.app.processEvents()
        self.assertFalse(screen._immersive)
        self.assertFalse(window.isFullScreen())
        self.assertFalse(screen._back_button.isHidden())
        self.assertFalse(screen._seek.isHidden())

    def test_escape_exits_immersive_mode(self) -> None:
        window = self._open_video()
        window.show()
        screen = window._video_screen
        screen._enter_immersive()
        self.app.processEvents()

        QTest.keyClick(screen, Qt.Key.Key_Escape)

        self.assertFalse(screen._immersive)
        self.assertFalse(window.isFullScreen())


if __name__ == "__main__":
    unittest.main()