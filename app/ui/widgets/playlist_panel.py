from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QInputDialog, QSplitter, QVBoxLayout, QWidget,
)

from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.core.playlist_service import PlaylistService
from app.models import Playlist, Track


class _PlaylistTrackList(QListWidget):
    order_changed = Signal()

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.order_changed.emit()


class PlaylistPanel(QWidget):
    def __init__(
        self,
        library: LibraryService,
        player: PlayerService,
        playlists: PlaylistService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._player = player
        self._playlists = playlists
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Playlists")
        title.setObjectName("TrackTitle")
        header.addWidget(title)
        header.addStretch()
        self._count = QLabel()
        self._count.setObjectName("Subtle")
        header.addWidget(self._count)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        playlist_column = QWidget()
        playlist_layout = QVBoxLayout(playlist_column)
        playlist_layout.setContentsMargins(0, 0, 8, 0)
        playlist_layout.setSpacing(8)
        self._playlist_list = QListWidget()
        self._playlist_list.setObjectName("PlaylistList")
        self._playlist_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        playlist_layout.addWidget(self._playlist_list, 1)

        playlist_actions = QHBoxLayout()
        self._new_button = QPushButton("New")
        self._rename_button = QPushButton("Rename")
        self._delete_button = QPushButton("Delete")
        playlist_actions.addWidget(self._new_button)
        playlist_actions.addWidget(self._rename_button)
        playlist_actions.addWidget(self._delete_button)
        playlist_layout.addLayout(playlist_actions)
        splitter.addWidget(playlist_column)

        tracks_column = QWidget()
        tracks_layout = QVBoxLayout(tracks_column)
        tracks_layout.setContentsMargins(8, 0, 0, 0)
        tracks_layout.setSpacing(8)
        self._tracks_title = QLabel("Select a playlist")
        self._tracks_title.setObjectName("Subtle")
        tracks_layout.addWidget(self._tracks_title)
        self._track_list = _PlaylistTrackList()
        self._track_list.setObjectName("PlaylistTracks")
        self._track_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._track_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._track_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._track_list.setDragDropOverwriteMode(False)
        self._track_list.setDropIndicatorShown(True)
        tracks_layout.addWidget(self._track_list, 1)

        track_actions = QHBoxLayout()
        track_actions.addStretch()
        self._remove_track_button = QPushButton("Remove from playlist")
        self._play_selected_button = QPushButton("Play selected")
        self._play_button = QPushButton("Play playlist")
        self._play_button.setProperty("variant", "primary")
        track_actions.addWidget(self._remove_track_button)
        track_actions.addWidget(self._play_selected_button)
        track_actions.addWidget(self._play_button)
        tracks_layout.addLayout(track_actions)
        splitter.addWidget(tracks_column)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        self._playlist_list.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_tracks()
        )
        self._track_list.itemDoubleClicked.connect(
            lambda _item: self._play_selected()
        )
        self._track_list.itemSelectionChanged.connect(self._update_actions)
        self._track_list.order_changed.connect(self._save_track_order)
        self._new_button.clicked.connect(self._create_playlist)
        self._rename_button.clicked.connect(self._rename_playlist)
        self._delete_button.clicked.connect(self._delete_playlist)
        self._remove_track_button.clicked.connect(self._remove_selected_track)
        self._play_selected_button.clicked.connect(self._play_selected)
        self._play_button.clicked.connect(self._play_playlist)
        self._playlists.playlists_changed.connect(self._refresh_playlists)
        self._library.library_changed.connect(self._refresh_tracks)
        self._refresh_playlists()

    def focus_playlists(self) -> None:
        self._playlist_list.setFocus()

    def _selected_playlist(self) -> Playlist | None:
        item = self._playlist_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _refresh_playlists(self) -> None:
        selected = self._selected_playlist()
        self._loading = True
        self._playlist_list.clear()
        selected_row = -1
        for playlist in self._playlists.playlists():
            item = QListWidgetItem(playlist.name)
            item.setData(Qt.ItemDataRole.UserRole, playlist)
            self._playlist_list.addItem(item)
            if selected is not None and playlist.id == selected.id:
                selected_row = self._playlist_list.count() - 1
        if self._playlist_list.count():
            self._playlist_list.setCurrentRow(
                selected_row if selected_row >= 0 else 0
            )
        self._loading = False
        self._refresh_tracks()

    def _refresh_tracks(self, *_args) -> None:
        playlist = self._selected_playlist()
        self._loading = True
        self._track_list.clear()
        if playlist is None:
            self._tracks_title.setText("Create a playlist to get started")
        else:
            self._tracks_title.setText(playlist.name)
            tracks_by_id = {track.id: track for track in self._library.tracks()}
            for track_id in self._playlists.track_ids(playlist.id):
                track = tracks_by_id.get(track_id)
                if track is not None:
                    self._track_list.addItem(self._track_item(track))
        self._loading = False
        self._count.setText(
            f"{self._playlist_list.count()} playlists · "
            f"{self._track_list.count()} songs"
        )
        self._update_actions()

    @staticmethod
    def _track_item(track: Track) -> QListWidgetItem:
        artist = track.artist or "Unknown artist"
        item = QListWidgetItem(f"{track.title}  ·  {artist}")
        item.setData(Qt.ItemDataRole.UserRole, track.id)
        item.setToolTip(track.album or track.title)
        return item

    def _create_playlist(self) -> None:
        name, accepted = QInputDialog.getText(self, "New playlist", "Playlist name:")
        if accepted:
            playlist = self._playlists.create(name)
            if playlist is not None:
                self._select_playlist(playlist.id)

    def _rename_playlist(self) -> None:
        playlist = self._selected_playlist()
        if playlist is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename playlist", "Playlist name:", text=playlist.name
        )
        if accepted:
            self._playlists.rename(playlist.id, name)

    def _delete_playlist(self) -> None:
        playlist = self._selected_playlist()
        if playlist is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete playlist",
            f"Delete “{playlist.name}”? The songs will remain in your library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._playlists.delete(playlist.id)

    def _select_playlist(self, playlist_id: int) -> None:
        for row in range(self._playlist_list.count()):
            item = self._playlist_list.item(row)
            playlist: Playlist = item.data(Qt.ItemDataRole.UserRole)
            if playlist.id == playlist_id:
                self._playlist_list.setCurrentItem(item)
                return

    def _remove_selected_track(self) -> None:
        playlist = self._selected_playlist()
        item = self._track_list.currentItem()
        if playlist is not None and item is not None:
            self._playlists.remove_track(
                playlist.id, item.data(Qt.ItemDataRole.UserRole)
            )

    def _save_track_order(self) -> None:
        if self._loading:
            return
        playlist = self._selected_playlist()
        if playlist is not None:
            track_ids = [
                self._track_list.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self._track_list.count())
            ]
            self._playlists.set_track_order(playlist.id, track_ids)

    def _play_selected(self) -> None:
        item = self._track_list.currentItem()
        if item is not None:
            self._player.play_track(item.data(Qt.ItemDataRole.UserRole))

    def _play_playlist(self) -> None:
        playlist = self._selected_playlist()
        if playlist is not None:
            self._player.play_tracks(self._playlists.track_ids(playlist.id))

    def _update_actions(self) -> None:
        has_playlist = self._selected_playlist() is not None
        has_track = self._track_list.currentItem() is not None
        has_tracks = self._track_list.count() > 0
        self._rename_button.setEnabled(has_playlist)
        self._delete_button.setEnabled(has_playlist)
        self._remove_track_button.setEnabled(has_playlist and has_track)
        self._play_selected_button.setEnabled(has_track)
        self._play_button.setEnabled(has_playlist and has_tracks)
