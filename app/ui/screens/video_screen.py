from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from app.core.audio_backend import PlaybackState
from app.core.vlc_video_backend import VlcVideoBackend
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_tool_button
from app.ui.widgets.seek_slider import SeekSlider
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

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        self._back_button = make_tool_button("arrow-left", "Back to library", size=40)
        self._title = QLabel("Video player")
        self._title.setObjectName("TrackTitle")
        self._fullscreen_button = QPushButton("Full screen")
        header.addWidget(self._back_button)
        header.addSpacing(6)
        header.addWidget(self._title, 1)
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
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(150)
        transport = QHBoxLayout()
        transport.addStretch()
        transport.addWidget(self._play_button)
        transport.addSpacing(20)
        transport.addWidget(QLabel("Volume"))
        transport.addWidget(self._volume)
        transport.addStretch()
        root.addLayout(transport)

        self._back_button.clicked.connect(self.close_video)
        self._fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self._play_button.clicked.connect(self.toggle_play_pause)
        self._seek.scrubbed.connect(
            lambda value: self._position.setText(format_time(value))
        )
        self._seek.committed.connect(self._backend.seek)
        self._volume.valueChanged.connect(
            lambda value: self._backend.set_volume(value / 100)
        )
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
        self._on_state_changed(self._backend.state)
        return self._has_media

    def toggle_play_pause(self) -> None:
        if self._has_media:
            self._backend.toggle_play_pause()

    def close_video(self) -> None:
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
        self._backend.shutdown()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_F:
            self._toggle_fullscreen()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self.window().isFullScreen():
            self.window().showNormal()
            self._fullscreen_button.setText("Full screen")
            event.accept()
        else:
            super().keyPressEvent(event)

    def _toggle_fullscreen(self) -> None:
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
            self._fullscreen_button.setText("Full screen")
        else:
            window.showFullScreen()
            self._fullscreen_button.setText("Exit full screen")

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._seek.is_dragging:
            self._seek.set_position(position_ms)
            self._position.setText(format_time(position_ms))

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._seek.setRange(0, max(0, duration_ms))
        self._duration.setText(format_time(duration_ms))

    def _on_state_changed(self, state: PlaybackState) -> None:
        playing = state is PlaybackState.PLAYING
        self._play_button.setIcon(
            icons.get_icon("pause" if playing else "play", theme.value("text"))
        )
        self._play_button.setToolTip("Pause" if playing else "Play")
        self.playback_state_changed.emit(state)

    @property
    def current_path(self) -> str | None:
        return self._current_path

    def _on_error(self, message: str) -> None:
        self._status.setText(message)
        self.error_occurred.emit(message)

    def _on_finished(self) -> None:
        self._position.setText(self._duration.text())