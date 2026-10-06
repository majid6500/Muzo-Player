from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QSlider, QToolButton, QVBoxLayout,
    QWidget,
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
        self.setFixedHeight(88)

        self._back = make_tool_button("arrow-left", "Back to library", size=40)
        self._play = make_tool_button("play", "Play", size=48, icon_size=22)
        self._play.setObjectName("OverlayPlayButton")
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
        self._volume.setObjectName("VolumeSlider")
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(104)
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

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(12)

        transport = QWidget()
        transport.setObjectName("OverlayControlGroup")
        transport_layout = QHBoxLayout(transport)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        transport_layout.setSpacing(4)
        transport_layout.addWidget(self._back)
        transport_layout.addWidget(self._play)

        timeline = QWidget()
        timeline.setObjectName("OverlayTimelineGroup")
        timeline_layout = QVBoxLayout(timeline)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(2)
        timeline_layout.addWidget(self._seek)
        time_labels = QHBoxLayout()
        time_labels.setContentsMargins(0, 0, 0, 0)
        time_labels.addWidget(self._position)
        time_labels.addStretch()
        time_labels.addWidget(self._duration)
        timeline_layout.addLayout(time_labels)

        controls = QWidget()
        controls.setObjectName("OverlayControlGroup")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        controls_layout.addWidget(self._volume)
        controls_layout.addWidget(self._subtitle)
        controls_layout.addWidget(self._exit)

        root.addWidget(transport)
        root.addWidget(self._separator())
        root.addWidget(timeline, 1)
        root.addWidget(self._separator())
        root.addWidget(controls)

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

    @staticmethod
    def _separator() -> QFrame:
        separator = QFrame()
        separator.setObjectName("OverlaySeparator")
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFixedHeight(36)
        return separator

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