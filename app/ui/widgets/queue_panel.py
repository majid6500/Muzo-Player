from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
    QWidget,
)

from app.core.library_service import LibraryService
from app.core.player_service import PlayerService


class _QueueListWidget(QListWidget):
    order_changed = Signal()

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.order_changed.emit()


class QueuePanel(QWidget):
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
        title = QLabel("Play queue")
        title.setObjectName("TrackTitle")
        header.addWidget(title)
        header.addStretch()
        self._count = QLabel()
        self._count.setObjectName("Subtle")
        header.addWidget(self._count)
        root.addLayout(header)

        self._queue_list = _QueueListWidget()
        self._queue_list.setObjectName("QueueList")
        self._queue_list.setMouseTracking(True)
        self._queue_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._queue_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._queue_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._queue_list.setDragDropOverwriteMode(False)
        self._queue_list.setDropIndicatorShown(True)
        root.addWidget(self._queue_list, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self._play_button = QPushButton("Play selected")
        self._play_button.setEnabled(False)
        actions.addWidget(self._play_button)
        root.addLayout(actions)

        self._queue_list.itemSelectionChanged.connect(
            lambda: self._play_button.setEnabled(
                self._queue_list.currentItem() is not None
            )
        )
        self._queue_list.itemDoubleClicked.connect(lambda _item: self._play_selected())
        self._queue_list.order_changed.connect(self._apply_order)
        self._play_button.clicked.connect(self._play_selected)
        self._player.queue_changed.connect(self._refresh)
        self._player.current_track_changed.connect(lambda _track: self._refresh())
        self._refresh()

    def _refresh(self) -> None:
        selected_item = self._queue_list.currentItem()
        selected_id = (
            selected_item.data(Qt.ItemDataRole.UserRole) if selected_item else None
        )
        current_track = self._player.current_track
        current_row = selected_row = -1
        self._queue_list.clear()
        track_ids = self._player.queue_track_ids

        for track_id in track_ids:
            track = self._library.get_track(track_id)
            if track is None:
                continue
            artist = track.artist or "Unknown artist"
            prefix = (
                "Now playing | "
                if current_track and track_id == current_track.id
                else ""
            )
            item = QListWidgetItem(f"{prefix}{track.title}  ·  {artist}")
            item.setData(Qt.ItemDataRole.UserRole, track_id)
            self._queue_list.addItem(item)
            row = self._queue_list.count() - 1
            if current_track and track_id == current_track.id:
                current_row = row
            if track_id == selected_id:
                selected_row = row

        self._count.setText(f"{len(track_ids)} tracks")
        self._queue_list.setCurrentRow(
            selected_row if selected_row >= 0 else current_row
        )
        self._play_button.setEnabled(self._queue_list.currentItem() is not None)

    def _apply_order(self) -> None:
        track_ids = [
            self._queue_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._queue_list.count())
        ]
        self._player.set_queue_order(track_ids)

    def _play_selected(self) -> None:
        item = self._queue_list.currentItem()
        if item is not None:
            track_id = item.data(Qt.ItemDataRole.UserRole)
            self._apply_order()
            self._player.play_track(track_id)