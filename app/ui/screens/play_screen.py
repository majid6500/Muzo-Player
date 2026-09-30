from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QBrush, QLinearGradient, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QSlider, QStackedWidget, QTabBar, QToolButton,
    QVBoxLayout, QWidget, QWidgetAction,
)

from app.core.audio_backend import PlaybackState
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.core.playback_queue import RepeatMode
from app.models import Track
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_tool_button
from app.ui.widgets.elided_label import ElidedLabel
from app.ui.widgets.equalizer_dialog import EqualizerDialog
from app.ui.widgets.favorites_panel import FavoritesPanel
from app.ui.widgets.queue_panel import QueuePanel
from app.ui.widgets.seek_slider import SeekSlider
from app.utils.formatting import format_time

ART_RADIUS = 20
CONTENT_MAX_WIDTH = 640


class PlayScreen(QWidget):
    """Playback screen: artwork, title, seek bar and transport controls."""

    back_requested = Signal()

    def __init__(self, library: LibraryService, player: PlayerService, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._library = library
        self._player = player
        self._cover: QPixmap | None = None
        self._art_size = 320

        self._build_ui()
        self._connect_signals()
        self._render_art()
        self._sync_from_player()

    # ---- construction ----
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 28)
        root.setSpacing(0)

        self._back_button = make_tool_button("arrow-left", "Back to library", size=40)
        top = QHBoxLayout()
        top.addWidget(self._back_button)
        top.addSpacing(8)
        self._view_tabs = QTabBar()
        self._view_tabs.addTab("Now playing")
        self._view_tabs.addTab("Queue")
        self._view_tabs.addTab("Favorites")
        top.addWidget(self._view_tabs)
        top.addStretch()
        self._equalizer_button = make_tool_button("sliders", "Equalizer", size=40)
        self._equalizer_button.setVisible(bool(self._player.equalizer_frequencies))
        top.addWidget(self._equalizer_button)
        root.addLayout(top)
        self._content_stack = QStackedWidget()
        self._playback_page = QWidget()
        self._playback_layout = QVBoxLayout(self._playback_page)
        self._playback_layout.setContentsMargins(0, 0, 0, 0)
        self._playback_layout.setSpacing(0)
        self._queue_panel = QueuePanel(self._library, self._player)
        self._favorites_panel = FavoritesPanel(self._library, self._player)
        self._content_stack.addWidget(self._playback_page)
        self._content_stack.addWidget(self._queue_panel)
        self._content_stack.addWidget(self._favorites_panel)
        root.addWidget(self._content_stack, 1)
        self._update_queue_tab()

        self._art = QLabel()
        self._art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._playback_layout.addStretch(1)
        self._playback_layout.addWidget(self._art, 0, Qt.AlignmentFlag.AlignHCenter)
        self._playback_layout.addSpacing(28)

        self._title = ElidedLabel("Nothing playing")
        self._title.setObjectName("TrackTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artist = ElidedLabel()
        self._artist.setObjectName("TrackArtist")
        self._artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._playback_layout.addWidget(self._title)
        self._playback_layout.addSpacing(4)
        self._playback_layout.addWidget(self._artist)
        self._playback_layout.addSpacing(24)

        self._position_label = QLabel("0:00")
        self._position_label.setObjectName("TimeLabel")
        self._position_label.setMinimumWidth(44)
        self._duration_label = QLabel("0:00")
        self._duration_label.setObjectName("TimeLabel")
        self._duration_label.setMinimumWidth(44)
        self._duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._seek = SeekSlider()
        self._seek.setRange(0, 0)
        seek_row = QHBoxLayout()
        seek_row.setSpacing(12)
        seek_row.addWidget(self._position_label)
        seek_row.addWidget(self._seek, 1)
        seek_row.addWidget(self._duration_label)
        seek_container = QWidget()
        seek_container.setMaximumWidth(CONTENT_MAX_WIDTH)
        seek_container.setLayout(seek_row)
        seek_row.setContentsMargins(0, 0, 0, 0)
        self._playback_layout.addWidget(seek_container, 0, Qt.AlignmentFlag.AlignHCenter)
        self._playback_layout.addSpacing(16)

        self._shuffle_button = make_tool_button("shuffle", "Shuffle")
        self._previous_button = make_tool_button("skip-back", "Previous", icon_size=24)
        self._play_button = make_tool_button(
            "play", "Play", size=64, icon_size=30, color=theme.value("accent_text")
        )
        self._play_button.setObjectName("PlayButton")
        self._next_button = make_tool_button("skip-forward", "Next", icon_size=24)
        self._repeat_button = make_tool_button("repeat", "Repeat: off")
        self._volume_button = make_tool_button(
            "volume", "Mute", size=44, icon_size=20, color=theme.value("text_dim")
        )
        self._volume_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.MenuButtonPopup
        )
        self._volume_menu = QMenu(self._volume_button)
        volume_panel = QWidget(self._volume_menu)
        volume_layout = QVBoxLayout(volume_panel)
        volume_layout.setContentsMargins(10, 10, 10, 10)
        volume_layout.setSpacing(8)
        self._volume_percent = QLabel()
        self._volume_percent.setObjectName("Subtle")
        self._volume_percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._volume_slider = QSlider(Qt.Orientation.Vertical)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setFixedHeight(126)
        self._volume_slider.setValue(round(self._player.volume * 100))
        volume_layout.addWidget(self._volume_percent)
        volume_layout.addWidget(
            self._volume_slider, 0, Qt.AlignmentFlag.AlignHCenter
        )
        volume_action = QWidgetAction(self._volume_menu)
        volume_action.setDefaultWidget(volume_panel)
        self._volume_menu.addAction(volume_action)
        self._volume_button.setMenu(self._volume_menu)
        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.addStretch()
        for button in (self._shuffle_button, self._previous_button, self._play_button,
                       self._next_button, self._repeat_button, self._volume_button):
            controls.addWidget(button)
        controls.addStretch()
        self._playback_layout.addLayout(controls)
        self._playback_layout.addStretch(1)

    def _connect_signals(self) -> None:
        player = self._player
        self._back_button.clicked.connect(lambda: self.back_requested.emit())
        self._equalizer_button.clicked.connect(self._open_equalizer)
        self._play_button.clicked.connect(lambda: player.toggle_play_pause())
        self._previous_button.clicked.connect(lambda: player.previous())
        self._next_button.clicked.connect(lambda: player.next())
        self._shuffle_button.clicked.connect(lambda: player.set_shuffle(not player.shuffle_enabled))
        self._repeat_button.clicked.connect(lambda: player.cycle_repeat())
        self._view_tabs.currentChanged.connect(self._on_view_changed)
        self._favorites_panel.count_changed.connect(self._update_favorites_tab)
        self._update_favorites_tab(self._favorites_panel.favorites_count)

        self._seek.scrubbed.connect(lambda ms: self._position_label.setText(format_time(ms)))
        self._seek.committed.connect(player.seek)
        self._volume_button.clicked.connect(player.toggle_mute)
        self._volume_slider.valueChanged.connect(
            lambda value: player.set_volume(value / 100)
        )

        player.current_track_changed.connect(self._on_track_changed)
        player.state_changed.connect(self._on_state_changed)
        player.position_changed.connect(self._on_position_changed)
        player.duration_changed.connect(self._on_duration_changed)
        player.volume_changed.connect(self._on_volume_changed)
        player.muted_changed.connect(self._on_mute_changed)
        player.modes_changed.connect(self._update_mode_buttons)
        player.queue_changed.connect(self._update_queue_tab)
        self._library.cover_loaded.connect(self._on_cover_loaded)

    def _sync_from_player(self) -> None:
        self._on_track_changed(self._player.current_track)
        self._on_state_changed(self._player.state)
        self._on_position_changed(self._player.position)
        self._on_volume_changed(self._player.volume)
        self._on_mute_changed(self._player.is_muted)
        self._update_mode_buttons()

    def _open_equalizer(self) -> None:
        EqualizerDialog(self._player, self).exec()

    def _update_queue_tab(self) -> None:
        if hasattr(self, "_view_tabs"):
            count = len(self._player.queue_track_ids)
            self._view_tabs.setTabText(1, f"Queue ({count})")

    def _update_favorites_tab(self, count: int) -> None:
        self._view_tabs.setTabText(2, f"Favorites ({count})")

    def _on_view_changed(self, index: int) -> None:
        self._content_stack.setCurrentIndex(index)
        if index == 2:
            self._favorites_panel.focus_list()

    def refresh_theme(self) -> None:
        self._on_state_changed(self._player.state)
        self._on_mute_changed(self._player.is_muted)
        self._update_mode_buttons()
        self._render_art()

    # ---- player events ----
    def _on_track_changed(self, track: Track | None) -> None:
        has_track = track is not None
        for widget in (self._previous_button, self._play_button, self._next_button, self._seek):
            widget.setEnabled(has_track)

        if track is None:
            self._title.setText("Nothing playing")
            self._artist.setText("")
            self._cover = None
        else:
            self._title.setText(track.title)
            self._artist.setText(" \u00b7 ".join(filter(None, [track.artist or "Unknown artist", track.album])))
            self._cover = self._load_cover(track)
        self._apply_duration(track.duration_ms if track else 0)
        self._seek.set_position(0)
        self._position_label.setText("0:00")
        self._render_art()

    def _on_state_changed(self, state: PlaybackState) -> None:
        playing = state is PlaybackState.PLAYING
        self._play_button.setIcon(
            icons.get_icon("pause" if playing else "play", theme.value("accent_text"))
        )
        self._play_button.setToolTip("Pause" if playing else "Play")

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._seek.is_dragging:
            self._seek.set_position(position_ms)
            self._position_label.setText(format_time(position_ms))

    def _on_duration_changed(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self._apply_duration(duration_ms)

    def _on_volume_changed(self, volume: float) -> None:
        value = round(volume * 100)
        if self._volume_slider.value() != value:
            self._volume_slider.blockSignals(True)
            self._volume_slider.setValue(value)
            self._volume_slider.blockSignals(False)
        self._volume_percent.setText(f"{value}%")

    def _on_mute_changed(self, muted: bool) -> None:
        icon_name = "volume-muted" if muted else "volume"
        self._volume_button.setIcon(icons.get_icon(icon_name, theme.value("text_dim")))
        action = "Unmute" if muted else "Mute"
        self._volume_button.setToolTip(f"{action}; volume options on arrow")

    def _update_mode_buttons(self) -> None:
        shuffle_on = self._player.shuffle_enabled
        accent = theme.value("accent_hover")
        self._shuffle_button.setIcon(icons.get_icon("shuffle", accent if shuffle_on else None))
        self._shuffle_button.setToolTip("Shuffle: on" if shuffle_on else "Shuffle: off")

        mode = self._player.repeat_mode
        icon_name = "repeat-one" if mode is RepeatMode.ONE else "repeat"
        self._repeat_button.setIcon(
            icons.get_icon(icon_name, None if mode is RepeatMode.OFF else accent)
        )
        self._repeat_button.setToolTip(f"Repeat: {mode.value}")

    # ---- helpers ----
    def _apply_duration(self, duration_ms: int) -> None:
        self._seek.setRange(0, duration_ms)
        self._duration_label.setText(format_time(duration_ms))

    def _load_cover(self, track: Track) -> QPixmap | None:
        return self._pixmap_from_data(self._library.get_cover(track.id))

    @staticmethod
    def _pixmap_from_data(data: bytes | None) -> QPixmap | None:
        if not data:
            return None
        pixmap = QPixmap()
        return pixmap if pixmap.loadFromData(data) else None

    def _on_cover_loaded(self, track_id: int, data: bytes | None) -> None:
        track = self._player.current_track
        if track is None or track.id != track_id:
            return
        self._cover = self._pixmap_from_data(data)
        self._render_art()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        size = max(160, min(self.width() - 96, self.height() - 400, 440))
        if size != self._art_size:
            self._art_size = size
            self._render_art()

    def _render_art(self) -> None:
        """Draw the rounded cover (or a placeholder) at the current size."""
        size = self._art_size
        dpr = self.devicePixelRatioF()
        px = int(size * dpr)

        result = QPixmap(px, px)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, px, px, ART_RADIUS * dpr, ART_RADIUS * dpr)
        painter.setClipPath(clip)

        if self._cover is not None:
            scaled = self._cover.scaled(
                px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap((px - scaled.width()) // 2, (px - scaled.height()) // 2, scaled)
        else:
            gradient = QLinearGradient(0, 0, px, px)
            gradient.setColorAt(0.0, theme.color("surface_alt"))
            gradient.setColorAt(1.0, theme.color("accent_soft"))
            painter.fillRect(0, 0, px, px, QBrush(gradient))
            icon_px = px // 3
            painter.drawPixmap(
                (px - icon_px) // 2, (px - icon_px) // 2,
                icons.pixmap("music", icon_px, theme.value("text_dim")),
            )
        painter.end()

        result.setDevicePixelRatio(dpr)
        self._art.setFixedSize(size, size)
        self._art.setPixmap(result)
