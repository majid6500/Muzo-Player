from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMenu, QPushButton, QSlider,
    QToolButton, QVBoxLayout, QWidget,
)

from app.core.audio_backend import PlaybackState
from app.core.vlc_video_backend import VlcVideoBackend
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_tool_button
from app.ui.widgets.seek_slider import SeekSlider
from app.ui.widgets.video_overlay import VideoOverlay
from app.utils.formatting import format_time


class VideoScreen(QWidget):
    back_requested = Signal()
    error_occurred = Signal(str)
    playback_state_changed = Signal(object)

    def __init__(self, backend: VlcVideoBackend, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._backend = backend
        self._has_media = False
        self._current_path: str | None = None
        self._immersive = False
        self._fullscreen_before_immersive = False
        self._last_cursor_position = QCursor.pos()

        self._root_layout = QVBoxLayout(self)
        root = self._root_layout
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        self._back_button = make_tool_button("arrow-left", "Back to library", size=40)
        self._title = QLabel("Video player")
        self._title.setObjectName("TrackTitle")
        self._fullscreen_button = QPushButton("Full screen")
        self._subtitle_button = make_tool_button("captions", "Subtitles", size=40)
        self._subtitle_menu = QMenu(self._subtitle_button)
        self._choose_subtitle_action = self._subtitle_menu.addAction(
            "Choose subtitle file..."
        )
        self._subtitle_off_action = self._subtitle_menu.addAction(
            "Turn subtitles off"
        )
        self._subtitle_button.setMenu(self._subtitle_menu)
        self._subtitle_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        header.addWidget(self._back_button)
        header.addSpacing(6)
        header.addWidget(self._title, 1)
        header.addWidget(self._subtitle_button)
        header.addWidget(self._fullscreen_button)
        root.addLayout(header)

        self._surface = QWidget()
        self._surface.setObjectName("VideoSurface")
        self._surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._surface.setMinimumSize(480, 270)
        root.addWidget(self._surface, 1)

        self._status = QLabel()
        self._status.setObjectName("Subtle")
        root.addWidget(self._status)

        self._position = QLabel("0:00")
        self._position.setObjectName("TimeLabel")
        self._position.setMinimumWidth(44)
        self._duration = QLabel("0:00")
        self._duration.setObjectName("TimeLabel")
        self._duration.setMinimumWidth(44)
        self._duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._seek = SeekSlider()
        self._seek.setRange(0, 0)
        self._seek.setEnabled(False)
        seek_row = QHBoxLayout()
        seek_row.setSpacing(10)
        seek_row.addWidget(self._position)
        seek_row.addWidget(self._seek, 1)
        seek_row.addWidget(self._duration)
        root.addLayout(seek_row)

        self._play_button = make_tool_button("play", "Play", size=44)
        self._play_button.setEnabled(False)
        self._immersive_button = make_tool_button(
            "expand", "Immersive fullscreen", size=40, icon_size=19
        )
        self._immersive_button.setEnabled(False)
        self._subtitle_button.setEnabled(False)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(150)
        self._volume_label = QLabel("Volume")
        transport = QHBoxLayout()
        transport.addStretch()
        transport.addWidget(self._play_button)
        transport.addWidget(self._immersive_button)
        transport.addSpacing(20)
        transport.addWidget(self._volume_label)
        transport.addWidget(self._volume)
        transport.addStretch()
        root.addLayout(transport)

        self._overlay = VideoOverlay(self.window())
        self._overlay.hide()
        self._overlay_hide_timer = QTimer(self)
        self._overlay_hide_timer.setSingleShot(True)
        self._overlay_hide_timer.setInterval(2400)
        self._overlay_hide_timer.timeout.connect(self._hide_immersive_controls)
        self._cursor_watch_timer = QTimer(self)
        self._cursor_watch_timer.setInterval(120)
        self._cursor_watch_timer.timeout.connect(self._watch_cursor)

        self._back_button.clicked.connect(self.close_video)
        self._fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self._immersive_button.clicked.connect(self._enter_immersive)
        self._choose_subtitle_action.triggered.connect(self._choose_subtitle)
        self._subtitle_off_action.triggered.connect(self._disable_subtitles)
        self._play_button.clicked.connect(self.toggle_play_pause)
        self._seek.scrubbed.connect(
            lambda value: self._position.setText(format_time(value))
        )
        self._seek.committed.connect(self._backend.seek)
        self._volume.valueChanged.connect(
            lambda value: self._backend.set_volume(value / 100)
        )
        self._overlay.back_requested.connect(self.close_video)
        self._overlay.exit_requested.connect(self._exit_immersive)
        self._overlay.play_pause_requested.connect(self.toggle_play_pause)
        self._overlay.seek_requested.connect(self._backend.seek)
        self._overlay.volume_requested.connect(self._backend.set_volume)
        self._overlay.subtitles_requested.connect(self._choose_subtitle)
        self._overlay.subtitles_off_requested.connect(self._disable_subtitles)
        self._backend.position_changed.connect(self._on_position_changed)
        self._backend.duration_changed.connect(self._on_duration_changed)
        self._backend.state_changed.connect(self._on_state_changed)
        self._backend.error_occurred.connect(self._on_error)
        self._backend.finished.connect(self._on_finished)
        self._backend.set_volume(0.7)

    def open_file(self, path: str) -> bool:
        self._status.clear()
        self._current_path = str(Path(path).resolve())
        self._title.setText(Path(self._current_path).name)
        self._position.setText("0:00")
        self._duration.setText("0:00")
        self._seek.setRange(0, 0)
        self._has_media = self._backend.open(
            self._current_path, int(self._surface.winId())
        )
        self._seek.setEnabled(self._has_media)
        self._play_button.setEnabled(self._has_media)
        self._immersive_button.setEnabled(self._has_media)
        self._subtitle_button.setEnabled(self._has_media)
        self._on_state_changed(self._backend.state)
        self._overlay.set_volume(self._volume.value() / 100)
        if self._has_media:
            subtitle_path = self._find_matching_subtitle(self._current_path)
            if subtitle_path is not None and self._backend.add_subtitle(str(subtitle_path)):
                self._status.setText(f"Subtitles: {subtitle_path.name}")
        return self._has_media

    def toggle_play_pause(self) -> None:
        if self._has_media:
            self._backend.toggle_play_pause()

    def close_video(self) -> None:
        if self._immersive:
            self._exit_immersive()
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
            self._fullscreen_button.setText("Full screen")
        if self._has_media:
            self._backend.stop()
            self._has_media = False
        self.back_requested.emit()

    def stop(self) -> None:
        self._backend.stop()
        self._has_media = False

    def shutdown(self) -> None:
        self._overlay_hide_timer.stop()
        self._cursor_watch_timer.stop()
        self._overlay.hide()
        self._backend.shutdown()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_F and not self._immersive:
            self._toggle_fullscreen()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self._immersive:
            self._exit_immersive()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self.window().isFullScreen():
            self.window().showNormal()
            self._fullscreen_button.setText("Full screen")
            event.accept()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._immersive:
            self._show_immersive_controls()
        super().mouseMoveEvent(event)

    def _toggle_fullscreen(self) -> None:
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
            self._fullscreen_button.setText("Full screen")
        else:
            window.showFullScreen()
            self._fullscreen_button.setText("Exit full screen")

    def _enter_immersive(self) -> None:
        if self._immersive or not self._has_media:
            return
        window = self.window()
        self._fullscreen_before_immersive = window.isFullScreen()
        self._immersive = True
        self._set_standard_controls_visible(False)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        window.showFullScreen()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._surface.setCursor(Qt.CursorShape.BlankCursor)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._last_cursor_position = QCursor.pos()
        self._cursor_watch_timer.start()
        self._show_immersive_controls()

    def _exit_immersive(self) -> None:
        if not self._immersive:
            return
        self._immersive = False
        self._overlay_hide_timer.stop()
        self._cursor_watch_timer.stop()
        self._overlay.hide()
        self._surface.unsetCursor()
        self.unsetCursor()
        self._set_standard_controls_visible(True)
        self._root_layout.setContentsMargins(24, 20, 24, 20)
        if not self._fullscreen_before_immersive and self.window().isFullScreen():
            self.window().showNormal()
        self._fullscreen_button.setText(
            "Exit full screen" if self.window().isFullScreen() else "Full screen"
        )

    def _set_standard_controls_visible(self, visible: bool) -> None:
        for widget in (
            self._back_button,
            self._title,
            self._fullscreen_button,
            self._subtitle_button,
            self._status,
            self._position,
            self._duration,
            self._seek,
            self._play_button,
            self._immersive_button,
            self._volume_label,
            self._volume,
        ):
            widget.setVisible(visible)

    def _position_overlay(self) -> None:
        window = self.window()
        width = min(880, max(560, window.width() - 40))
        height = self._overlay.height()
        self._overlay.setFixedWidth(width)
        origin = window.mapToGlobal(QPoint(0, 0))
        self._overlay.move(
            origin.x() + (window.width() - width) // 2,
            origin.y() + window.height() - height - 28,
        )

    def _show_immersive_controls(self) -> None:
        if not self._immersive:
            return
        self._surface.unsetCursor()
        self.unsetCursor()
        self._position_overlay()
        self._overlay.show()
        self._overlay.raise_()
        self._overlay_hide_timer.start()

    def _hide_immersive_controls(self) -> None:
        if not self._immersive:
            return
        self._overlay.hide()
        self._surface.setCursor(Qt.CursorShape.BlankCursor)
        self.setCursor(Qt.CursorShape.BlankCursor)

    def _watch_cursor(self) -> None:
        position = QCursor.pos()
        if position != self._last_cursor_position:
            self._last_cursor_position = position
            self._show_immersive_controls()

    def _on_position_changed(self, position_ms: int) -> None:
        self._overlay.set_position(position_ms)
        if not self._seek.is_dragging:
            self._seek.set_position(position_ms)
            self._position.setText(format_time(position_ms))

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._seek.setRange(0, max(0, duration_ms))
        self._duration.setText(format_time(duration_ms))
        self._overlay.set_duration(duration_ms)

    def _on_state_changed(self, state: PlaybackState) -> None:
        playing = state is PlaybackState.PLAYING
        self._play_button.setIcon(
            icons.get_icon("pause" if playing else "play", theme.value("text"))
        )
        self._play_button.setToolTip("Pause" if playing else "Play")
        self._immersive_button.setEnabled(self._has_media)
        self._overlay.set_playing(playing)
        self.playback_state_changed.emit(state)

    @property
    def current_path(self) -> str | None:
        return self._current_path

    def _on_error(self, message: str) -> None:
        self._status.setText(message)
        self.error_occurred.emit(message)

    def _choose_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose subtitle file",
            str(Path(self._current_path).parent) if self._current_path else "",
            "Subtitle files (*.srt *.ass *.ssa *.vtt *.sub);;All files (*)",
        )
        if path and self._backend.add_subtitle(path):
            self._status.setText(f"Subtitles: {Path(path).name}")

    def _disable_subtitles(self) -> None:
        if self._backend.disable_subtitles():
            self._status.setText("Subtitles off")

    @staticmethod
    def _find_matching_subtitle(video_path: str) -> Path | None:
        path = Path(video_path)
        for suffix in (".srt", ".ass", ".ssa", ".vtt", ".sub"):
            candidate = path.with_suffix(suffix)
            if candidate.is_file():
                return candidate
        return None

    def _on_finished(self) -> None:
        self._position.setText(self._duration.text())