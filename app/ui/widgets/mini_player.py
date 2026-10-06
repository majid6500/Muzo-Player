from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from app.core.audio_backend import PlaybackState
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.models import Track
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_tool_button
from app.ui.widgets.elided_label import ElidedLabel
from app.utils.formatting import format_time


class MiniPlayer(QFrame):
    """Compact 'now playing' bar on the Home screen. Click it to open Play."""

    open_requested = Signal()

    def __init__(
        self, library: LibraryService, player: PlayerService, parent=None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MiniPlayer")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Open now playing")
        self._library = library
        self._player = player
        self._cover: QPixmap | None = None
        self._duration_ms = 0

        self._cover_label = QLabel()
        self._cover_label.setObjectName("MiniCover")
        self._cover_label.setFixedSize(52, 52)
        self._cover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title = ElidedLabel()
        self._artist = ElidedLabel()
        self._artist.setObjectName("Subtle")
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(self._title)
        texts.addWidget(self._artist)
        self._progress = QProgressBar()
        self._progress.setObjectName("MiniProgress")
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(8)
        details.addLayout(texts)
        details.addWidget(self._progress)

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
        layout.setContentsMargins(16, 10, 14, 10)
        layout.setSpacing(14)
        layout.addWidget(self._cover_label)
        layout.addLayout(details, 1)
        layout.addWidget(self._previous_button)
        layout.addWidget(self._button)
        layout.addWidget(self._next_button)

        player.current_track_changed.connect(self._on_track_changed)
        player.state_changed.connect(self._on_state_changed)
        player.position_changed.connect(self._on_position_changed)
        player.duration_changed.connect(self._on_duration_changed)
        library.cover_loaded.connect(self._on_cover_loaded)
        self._on_track_changed(player.current_track)
        self._on_state_changed(player.state)
        self._on_position_changed(player.position)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.open_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.open_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_track_changed(self, track: Track | None) -> None:
        self.setVisible(track is not None)
        self._cover = None
        if track is not None:
            self._title.setText(track.title)
            self._artist.setText(" \u00b7 ".join(
                filter(None, [track.artist or "Unknown artist", track.album])
            ))
            self._duration_ms = max(0, track.duration_ms)
            self._progress.setRange(0, max(1, self._duration_ms))
            self._progress.setValue(0)
            self._progress.setToolTip(
                f"0:00 / {format_time(self._duration_ms)}"
            )
            cover_data = self._library.get_cover(track.id)
            if cover_data:
                self._set_cover(cover_data)
        else:
            self._title.setText("Nothing playing")
            self._artist.clear()
            self._duration_ms = 0
            self._progress.setRange(0, 1)
            self._progress.setValue(0)
            self._progress.setToolTip("")
        self._render_cover()

    def _on_position_changed(self, position_ms: int) -> None:
        duration = self._duration_ms
        self._progress.setRange(0, max(1, duration))
        self._progress.setValue(min(max(0, position_ms), max(1, duration)))
        self._progress.setToolTip(
            f"{format_time(position_ms)} / {format_time(duration)}"
            if duration else ""
        )

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = max(0, duration_ms)
        duration = self._duration_ms
        self._progress.setRange(0, max(1, duration))
        self._progress.setValue(min(self._player.position, max(1, duration)))
        self._progress.setToolTip(
            f"{format_time(self._player.position)} / {format_time(duration)}"
            if duration else ""
        )

    def _on_cover_loaded(self, track_id: int, data: bytes | None) -> None:
        track = self._player.current_track
        if track is None or track.id != track_id or not data:
            return
        self._set_cover(data)

    def _set_cover(self, data: bytes) -> None:
        cover = QPixmap()
        if cover.loadFromData(data):
            self._cover = cover
            self._render_cover()

    def _render_cover(self) -> None:
        size = self._cover_label.size()
        result = QPixmap(size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size.width(), size.height(), 8, 8)
        painter.setClipPath(path)
        if self._cover is not None:
            scaled = self._cover.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(
                (size.width() - scaled.width()) // 2,
                (size.height() - scaled.height()) // 2,
                scaled,
            )
        else:
            painter.fillRect(0, 0, size.width(), size.height(), theme.color("accent_soft"))
            icon_size = 28
            painter.drawPixmap(
                (size.width() - icon_size) // 2,
                (size.height() - icon_size) // 2,
                icons.pixmap("music", icon_size, theme.value("accent_hover")),
            )
        painter.end()
        self._cover_label.setPixmap(result)

    def _on_state_changed(self, state: PlaybackState) -> None:
        name = "pause" if state is PlaybackState.PLAYING else "play"
        self._button.setIcon(icons.get_icon(name, theme.value("accent_text")))

    def refresh_theme(self) -> None:
        self._on_state_changed(self._player.state)
        self._render_cover()
