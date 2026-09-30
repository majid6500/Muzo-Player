from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from app.core.library_service import LibraryService
from app.core.player_service import PlayerService


class _FavoritesListWidget(QListWidget):
    track_activated = Signal(int)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item is not None:
                self.track_activated.emit(item.data(Qt.ItemDataRole.UserRole))
                event.accept()
                return
        super().keyPressEvent(event)


class FavoritesPanel(QWidget):
    count_changed = Signal(int)

    def __init__(
        self, library: LibraryService, player: PlayerService, parent=None
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._player = player

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Favorites")
        title.setObjectName("TrackTitle")
        header.addWidget(title)
        header.addStretch()
        self._count = QLabel()
        self._count.setObjectName("Subtle")
        header.addWidget(self._count)
        root.addLayout(header)

        self._content = QStackedWidget()
        self._list = _FavoritesListWidget()
        self._list.setObjectName("FavoriteList")
        self._list.setMouseTracking(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._empty = QLabel("No favorites yet")
        self._empty.setObjectName("Subtle")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content.addWidget(self._list)
        self._content.addWidget(self._empty)
        root.addWidget(self._content, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self._play_button = QPushButton("Play selected")
        self._play_button.setEnabled(False)
        actions.addWidget(self._play_button)
        root.addLayout(actions)

        self._list.itemSelectionChanged.connect(
            lambda: self._play_button.setEnabled(self._list.currentItem() is not None)
        )
        self._list.track_activated.connect(self._play_track)
        self._list.itemDoubleClicked.connect(self._play_selected)
        self._play_button.clicked.connect(self._play_selected)
        self._library.library_changed.connect(self._refresh)
        self._player.current_track_changed.connect(lambda _track: self._refresh())
        self._refresh()

    @property
    def favorites_count(self) -> int:
        return self._list.count()

    def focus_list(self) -> None:
        if self._list.count() and self._list.currentItem() is None:
            current = self._player.current_track
            current_row = self._find_row(current.id) if current is not None else -1
            self._list.setCurrentRow(current_row if current_row >= 0 else 0)
        self._list.setFocus()

    def _refresh(self, *_args) -> None:
        previous_item = self._list.currentItem()
        selected_id = (
            previous_item.data(Qt.ItemDataRole.UserRole) if previous_item else None
        )
        current = self._player.current_track
        favorites = [track for track in self._library.tracks() if track.is_favorite]
        self._list.clear()

        current_row = selected_row = -1
        for track in favorites:
            artist = track.artist or "Unknown artist"
            prefix = "Now playing | " if current and track.id == current.id else ""
            item = QListWidgetItem(f"{prefix}{track.title}  ·  {artist}")
            item.setData(Qt.ItemDataRole.UserRole, track.id)
            self._list.addItem(item)
            row = self._list.count() - 1
            if current and track.id == current.id:
                current_row = row
            if track.id == selected_id:
                selected_row = row

        self._count.setText(f"{len(favorites)} favorites")
        self.count_changed.emit(len(favorites))
        self._content.setCurrentWidget(self._list if favorites else self._empty)
        preferred_row = selected_row if selected_row >= 0 else current_row
        if preferred_row >= 0:
            self._list.setCurrentRow(preferred_row)
        elif self._list.count():
            self._list.setCurrentRow(0)
        self._play_button.setEnabled(self._list.currentItem() is not None)

    def _find_row(self, track_id: int) -> int:
        for row in range(self._list.count()):
            if self._list.item(row).data(Qt.ItemDataRole.UserRole) == track_id:
                return row
        return -1

    def _play_selected(self, *_args) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._play_track(item.data(Qt.ItemDataRole.UserRole))

    def _play_track(self, track_id: int) -> None:
        self._player.play_track(track_id)