from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QSlider, QToolButton, QWidget,
)

from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_tool_button
from app.ui.widgets.seek_slider import SeekSlider
from app.utils.formatting import format_time


class VideoOverlay(QWidget):
    back_requested = Signal()
    exit_requested = Signal()
    play_pause_requested = Signal()
    seek_requested = Signal(int)
    volume_requested = Signal(float)
    subtitles_requested = Signal()
    subtitles_off_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self.setObjectName("VideoOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedHeight(72)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)

        self._back = make_tool_button("arrow-left", "Back to library", size=40)
        self._play = make_tool_button("play", "Play", size=44, icon_size=22)
        self._position = QLabel("0:00")
        self._position.setObjectName("TimeLabel")
        self._position.setMinimumWidth(42)
        self._duration = QLabel("0:00")
        self._duration.setObjectName("TimeLabel")
        self._duration.setMinimumWidth(42)
        self._duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._seek = SeekSlider()
        self._seek.setRange(0, 0)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(96)
        self._subtitle = make_tool_button(
            "captions", "Subtitles", size=40, icon_size=20
        )
        self._subtitle_menu = QMenu(self._subtitle)
        self._subtitle_menu.addAction("Choose subtitle file...").triggered.connect(
            self.subtitles_requested
        )
        self._subtitle_menu.addAction("Turn subtitles off").triggered.connect(
            self.subtitles_off_requested
        )
        self._subtitle.setMenu(self._subtitle_menu)
        self._subtitle.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._exit = make_tool_button("shrink", "Exit immersive mode", size=40)

        row.addWidget(self._back)
        row.addWidget(self._play)
        row.addWidget(self._position)
        row.addWidget(self._seek, 1)
        row.addWidget(self._duration)
        row.addWidget(self._volume)
        row.addWidget(self._subtitle)
        row.addWidget(self._exit)

        self._back.clicked.connect(self.back_requested)
        self._play.clicked.connect(self.play_pause_requested)
        self._exit.clicked.connect(self.exit_requested)
        self._seek.scrubbed.connect(
            lambda value: self._position.setText(format_time(value))
        )
        self._seek.committed.connect(self.seek_requested)
        self._volume.valueChanged.connect(
            lambda value: self.volume_requested.emit(value / 100)
        )

    def set_duration(self, duration_ms: int) -> None:
        duration_ms = max(0, duration_ms)
        self._seek.setRange(0, duration_ms)
        self._duration.setText(format_time(duration_ms))

    def set_position(self, position_ms: int) -> None:
        if not self._seek.is_dragging:
            self._seek.set_position(position_ms)
            self._position.setText(format_time(position_ms))

    def set_playing(self, playing: bool) -> None:
        name = "pause" if playing else "play"
        self._play.setIcon(icons.get_icon(name, theme.value("text")))
        self._play.setToolTip("Pause" if playing else "Play")

    def set_volume(self, volume: float) -> None:
        value = round(min(1.0, max(0.0, volume)) * 100)
        if self._volume.value() != value:
            self._volume.blockSignals(True)
            self._volume.setValue(value)
            self._volume.blockSignals(False)