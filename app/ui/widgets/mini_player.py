from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.core.audio_backend import PlaybackState
from app.core.player_service import PlayerService
from app.models import Track
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_tool_button
from app.ui.widgets.elided_label import ElidedLabel


class MiniPlayer(QFrame):
    """Compact 'now playing' bar on the Home screen. Click it to open Play."""

    open_requested = Signal()

    def __init__(self, player: PlayerService, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MiniPlayer")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._player = player

        self._title = ElidedLabel()
        self._artist = ElidedLabel()
        self._artist.setObjectName("Subtle")
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(self._title)
        texts.addWidget(self._artist)

        self._previous_button = make_tool_button("skip-back", "Previous", size=40, icon_size=20)
        self._button = make_tool_button(
            "play", "Play / Pause", size=40, icon_size=20,
            color=theme.value("accent_text"),
        )
        self._button.setObjectName("MiniPlayButton")
        self._next_button = make_tool_button("skip-forward", "Next", size=40, icon_size=20)
        self._previous_button.clicked.connect(self._player.previous)
        self._button.clicked.connect(self._player.toggle_play_pause)
        self._next_button.clicked.connect(self._player.next)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 14, 10)
        layout.addLayout(texts, 1)
        layout.addWidget(self._previous_button)
        layout.addWidget(self._button)
        layout.addWidget(self._next_button)

        player.current_track_changed.connect(self._on_track_changed)
        player.state_changed.connect(self._on_state_changed)
        self._on_track_changed(player.current_track)
        self._on_state_changed(player.state)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit()

    def _on_track_changed(self, track: Track | None) -> None:
        self.setVisible(track is not None)
        if track is not None:
            self._title.setText(track.title)
            self._artist.setText(track.artist or "Unknown artist")

    def _on_state_changed(self, state: PlaybackState) -> None:
        name = "pause" if state is PlaybackState.PLAYING else "play"
        self._button.setIcon(icons.get_icon(name, theme.value("accent_text")))

    def refresh_theme(self) -> None:
        self._on_state_changed(self._player.state)
