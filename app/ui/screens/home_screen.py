from __future__ import annotations

from PySide6.QtCore import QStandardPaths, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QHBoxLayout, QLabel, QMenu, QProgressBar,
    QLineEdit, QStackedWidget,
    QTabBar, QToolButton, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from app.config import is_supported, is_video_supported, media_file_dialog_filter
from app.core.audio_backend import PlaybackState
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.core.video_library_service import VideoLibraryService
from app.models import Track
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_push_button, make_tool_button
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.mini_player import MiniPlayer
from app.ui.widgets.track_list import (
    TrackListModel, TrackListView, TrackRole, VideoTrackListModel,
)
from app.utils.formatting import plural


def matches_track_query(track: Track, query: str) -> bool:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return True
    searchable_text = " ".join((track.title, track.artist, track.album)).casefold()
    return normalized_query in searchable_text


class HomeScreen(QWidget):
    """The library: song list, import buttons and a mini player."""

    open_play_requested = Signal()
    open_video_requested = Signal()
    open_video_path_requested = Signal(str)
    accent_color_selected = Signal(str)

    def __init__(
        self,
        library: LibraryService,
        video_library: VideoLibraryService,
        player: PlayerService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._library = library
        self._video_library = video_library
        self._player = player
        self._active_imports = 0
        self._model = TrackListModel(self)
        self._video_model = VideoTrackListModel(self)
        self._playing_video_path: str | None = None
        self._video_is_playing = False
        self._last_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)

        self._build_ui()
        self._connect_signals()
        self._reload_tracks()
        current = player.current_track
        self._model.set_current_id(current.id if current else None)
        self._list.set_playing(player.state is PlaybackState.PLAYING)

    # ---- construction ----
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("Library")
        title.setObjectName("ScreenTitle")
        self._count_label = QLabel()
        self._count_label.setObjectName("Subtle")
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(title)
        titles.addWidget(self._count_label)

        self._remove_button = make_push_button("Remove", "trash")
        self._remove_button.setToolTip("Remove selected songs from the library (files are not deleted)")
        self._files_button = make_push_button("Add files", "file-plus")
        self._folder_button = make_push_button("Add folder", "folder-plus", primary=True)
        self._accent_button = make_tool_button("droplet", "Accent color", size=40)
        self._accent_menu = QMenu(self._accent_button)
        choose_color_action = self._accent_menu.addAction("Choose accent color...")
        reset_color_action = self._accent_menu.addAction("Reset to emerald green")
        self._accent_button.setMenu(self._accent_menu)
        self._accent_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.refresh_theme()
        self._filter_tabs = QTabBar()
        self._filter_tabs.addTab("All songs")
        self._filter_tabs.addTab("All videos")
        self._filter_tabs.addTab("Favorites")

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(titles)
        header.addSpacing(18)
        header.addWidget(self._filter_tabs)
        header.addStretch()
        header.addWidget(self._remove_button)
        header.addWidget(self._files_button)
        header.addWidget(self._folder_button)
        self._video_button = make_push_button("Open video", "film")
        header.addWidget(self._video_button)
        header.addWidget(self._accent_button)
        root.addLayout(header)

        self._search = QLineEdit()
        self._search.setObjectName("LibrarySearch")
        self._search.setPlaceholderText("Search title, artist, or album")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(220)
        self._search.setMaximumWidth(360)
        self._search_action = self._search.addAction(
            icons.get_icon("search", theme.value("text_dim")),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        search_row = QHBoxLayout()
        search_row.addWidget(self._search)
        search_row.addStretch()
        root.addLayout(search_row)

        self._progress_box = QWidget()
        progress_layout = QVBoxLayout(self._progress_box)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("Subtle")
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 0)
        progress_bar.setTextVisible(False)
        progress_layout.addWidget(self._progress_label)
        progress_layout.addWidget(progress_bar)
        self._progress_box.hide()
        root.addWidget(self._progress_box)

        self._empty = EmptyState()
        self._favorites_empty = QWidget()
        favorites_empty_layout = QVBoxLayout(self._favorites_empty)
        favorites_empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        favorites_empty_layout.setSpacing(8)
        favorites_empty_title = QLabel("No favorites yet")
        favorites_empty_title.setObjectName("EmptyTitle")
        favorites_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        favorites_empty_subtitle = QLabel("Star a song to keep it here.")
        favorites_empty_subtitle.setObjectName("Subtle")
        favorites_empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        favorites_empty_layout.addWidget(favorites_empty_title)
        favorites_empty_layout.addWidget(favorites_empty_subtitle)
        self._no_results = QLabel("No matching songs")
        self._no_results.setObjectName("Subtle")
        self._no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._videos_empty = QLabel("No videos yet")
        self._videos_empty.setObjectName("Subtle")
        self._videos_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_list = TrackListView()
        self._video_list.setObjectName("VideosList")
        self._video_list.setModel(self._video_model)
        self._video_list.remove_requested.connect(self._remove_selected)
        self._list = TrackListView()
        self._list.setModel(self._model)
        self._video_list.selectionModel().selectionChanged.connect(
            lambda *_: self._update_actions()
        )
        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty)
        self._stack.addWidget(self._favorites_empty)
        self._stack.addWidget(self._list)
        self._stack.addWidget(self._no_results)
        self._stack.addWidget(self._video_list)
        self._stack.addWidget(self._videos_empty)
        root.addWidget(self._stack, 1)

        self._mini_player = MiniPlayer(self._player)
        root.addWidget(self._mini_player)

    def _connect_signals(self) -> None:
        self._files_button.clicked.connect(self._choose_files)
        self._folder_button.clicked.connect(self._choose_folder)
        self._accent_menu.actions()[0].triggered.connect(self._choose_accent_color)
        self._accent_menu.actions()[1].triggered.connect(
            lambda: self.accent_color_selected.emit(theme.DEFAULT_ACCENT)
        )
        self._remove_button.clicked.connect(self._remove_selected)
        self._empty.add_files_clicked.connect(self._choose_files)
        self._empty.add_folder_clicked.connect(self._choose_folder)
        self._mini_player.open_requested.connect(self.open_play_requested)
        self._video_button.clicked.connect(self._on_open_video_clicked)

        self._list.track_activated.connect(self._on_track_activated)
        self._list.play_next_requested.connect(self._player.play_next)
        self._list.queue_add_requested.connect(self._player.add_to_queue)
        self._list.remove_requested.connect(self._remove_selected)
        self._list.favorite_toggled.connect(self._on_favorite_toggled)
        self._video_list.track_activated.connect(self._on_video_activated)
        self._filter_tabs.currentChanged.connect(self._reload_tracks)
        self._search.textChanged.connect(self._reload_tracks)
        self._list.selectionModel().selectionChanged.connect(lambda *_: self._update_actions())
        self._model.modelReset.connect(self._update_actions)

        self._library.library_changed.connect(self._reload_tracks)
        self._library.import_started.connect(self._on_import_started)
        self._library.import_progress.connect(self._on_import_progress)
        self._library.import_finished.connect(self._on_import_finished)
        self._video_library.videos_changed.connect(self._reload_videos)
        self._video_library.import_started.connect(self._on_video_import_started)
        self._video_library.import_progress.connect(self._on_import_progress)
        self._video_library.import_finished.connect(self._on_video_import_finished)
        self._video_library.error_occurred.connect(
            lambda message: self._progress_label.setText(message)
        )
        self._reload_videos()

        self._player.current_track_changed.connect(self._on_current_track_changed)
        self._player.state_changed.connect(self._on_playback_state_changed)
        self._player.track_failed.connect(self._model.mark_unavailable)

    # ---- library / player events ----
    def _reload_tracks(self) -> None:
        if self._filter_tabs.currentIndex() == 1:
            self._reload_videos()
            self._update_actions()
            return
        all_tracks = self._library.tracks()
        favorites_only = self._filter_tabs.currentIndex() == 2
        query = self._search.text()
        tracks = [
            track for track in all_tracks
            if (not favorites_only or track.is_favorite)
            and matches_track_query(track, query)
        ]
        scrollbar = self._list.verticalScrollBar()
        scroll_position = scrollbar.value()
        self._model.set_tracks(tracks)
        QTimer.singleShot(0, lambda: scrollbar.setValue(scroll_position))

        if query.strip():
            self._count_label.setText(
                plural(len(tracks), "result") if tracks else "No matches"
            )
        elif favorites_only:
            self._count_label.setText(
                plural(len(tracks), "favorite") if tracks else "No favorites yet"
            )
        else:
            self._count_label.setText(
                plural(len(tracks), "song") if tracks else "No songs yet"
            )
        if not all_tracks:
            self._stack.setCurrentWidget(self._empty)
        elif favorites_only and not tracks:
            self._stack.setCurrentWidget(
                self._no_results if query.strip() else self._favorites_empty
            )
        elif query.strip() and not tracks:
            self._stack.setCurrentWidget(self._no_results)
        else:
            self._stack.setCurrentWidget(self._list)
        current = self._player.current_track
        self._model.set_current_id(current.id if current else None)
        self._list.set_playing(self._player.state is PlaybackState.PLAYING)

    def _reload_videos(self) -> None:
        selected_ids = set(self._video_list.selected_track_ids())
        query = self._search.text().strip().casefold()
        all_videos = self._video_library.videos()
        videos = [
            video for video in all_videos
            if query in video.title.casefold()
        ]
        self._filter_tabs.setTabText(1, "All videos")
        if self._filter_tabs.currentIndex() != 1:
            return
        self._video_model.set_videos(videos)
        self._sync_video_playback()
        for row, video in enumerate(videos):
            if video.id in selected_ids:
                index = self._video_model.index(row)
                self._video_list.selectionModel().select(
                    index,
                    self._video_list.selectionModel().SelectionFlag.Select
                    | self._video_list.selectionModel().SelectionFlag.Rows,
                )

        self._count_label.setText(f"{len(videos)} videos")
        self._stack.setCurrentWidget(self._video_list if videos else self._videos_empty)
        self._update_actions()

    def set_video_playback(self, path: str | None, is_playing: bool) -> None:
        self._playing_video_path = path
        self._video_is_playing = is_playing
        self._sync_video_playback()

    def _sync_video_playback(self) -> None:
        current_video = next(
            (
                video for video in self._video_library.videos()
                if video.path == self._playing_video_path
            ),
            None,
        )
        self._video_model.set_current_id(
            current_video.id if current_video is not None else None
        )
        is_playing = self._video_is_playing and current_video is not None
        self._video_model.set_playing(is_playing)
        self._video_list.set_playing(is_playing)

    def _on_video_activated(self, video_id: int) -> None:
        video = self._video_library.get_video(video_id)
        if video is not None:
            self.open_video_path_requested.emit(video.path)

    def _on_open_video_clicked(self) -> None:
        if self._filter_tabs.currentIndex() == 1:
            selected_ids = self._video_list.selected_track_ids()
            current_index = self._video_list.currentIndex()
            if current_index.isValid():
                selected_ids.insert(0, current_index.data(TrackRole).id)
            if selected_ids:
                self._on_video_activated(selected_ids[0])
                return
        self.open_video_requested.emit()

    def _on_current_track_changed(self, track: Track | None) -> None:
        self._model.set_current_id(track.id if track else None)
        self._list.set_playing(self._player.state is PlaybackState.PLAYING)

    def _on_playback_state_changed(self, state: PlaybackState) -> None:
        self._list.set_playing(state is PlaybackState.PLAYING)

    def _on_import_started(self) -> None:
        self._active_imports += 1
        self._progress_label.setText("Scanning for audio files\u2026")
        self._progress_box.show()
        self._set_import_buttons_enabled(False)

    def _on_import_progress(self, processed: int) -> None:
        self._progress_label.setText(f"Reading songs\u2026 {processed} files processed")

    def _on_import_finished(self, *_counts: int) -> None:
        self._finish_import_ui()

    def _on_video_import_started(self) -> None:
        self._active_imports += 1
        self._progress_label.setText("Scanning for video files...")
        self._progress_box.show()
        self._set_import_buttons_enabled(False)

    def _on_video_import_finished(self, added: int, duplicates: int, unreadable: int) -> None:
        self._finish_import_ui()
        self._progress_label.setText(
            f"Video import complete: {added} added, {duplicates} already in library, "
            f"{unreadable} unsupported or unreadable."
        )

    def _finish_import_ui(self) -> None:
        self._active_imports = max(0, self._active_imports - 1)
        if self._active_imports == 0:
            self._progress_box.hide()
            self._set_import_buttons_enabled(True)

    # ---- user actions ----
    def _on_track_activated(self, track_id: int) -> None:
        if self._player.play_track(track_id):
            self.open_play_requested.emit()

    def _on_favorite_toggled(self, track_id: int, is_favorite: bool) -> None:
        self._library.set_favorite(track_id, is_favorite)

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add media files", self._last_dir, media_file_dialog_filter()
        )
        if paths:
            self._last_dir = paths[0].rsplit("/", 1)[0]
            audio_paths = [path for path in paths if is_supported(path)]
            video_paths = [path for path in paths if is_video_supported(path)]
            if audio_paths:
                self._library.add_files(audio_paths)
            if video_paths:
                self._video_library.add_files(video_paths)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Add a folder of media", self._last_dir
        )
        if folder:
            self._last_dir = folder
            self._library.add_folder(folder)
            self._video_library.add_folder(folder)

    def _remove_selected(self) -> None:
        if self._filter_tabs.currentIndex() == 1:
            video_ids = self._video_list.selected_track_ids()
            self._video_library.remove_many(video_ids)
            return
        track_ids = self._list.selected_track_ids()
        if track_ids:
            if self._filter_tabs.currentIndex() == 2:
                self._library.set_favorites(track_ids, False)
            else:
                self._library.remove_tracks(track_ids)

    def _choose_accent_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(theme.value("accent")), self, "Choose accent color"
        )
        if selected.isValid():
            self.accent_color_selected.emit(selected.name())

    def refresh_theme(self) -> None:
        accent = theme.value("accent")
        self._accent_button.setIcon(icons.get_icon("droplet", accent))
        self._accent_button.setToolTip(f"Accent color: {accent}")
        if hasattr(self, "_search"):
            self._search_action.setIcon(
                icons.get_icon("search", theme.value("text_dim"))
            )
        if hasattr(self, "_empty"):
            self._empty.refresh_theme()
        if hasattr(self, "_mini_player"):
            self._mini_player.refresh_theme()
        if hasattr(self, "_list"):
            self._list.viewport().update()

    # ---- helpers ----
    def _set_import_buttons_enabled(self, enabled: bool) -> None:
        self._files_button.setEnabled(enabled)
        self._folder_button.setEnabled(enabled)
        self._empty.set_busy(not enabled)

    def _update_actions(self) -> None:
        if self._filter_tabs.currentIndex() == 1:
            selected = bool(self._video_list.selected_track_ids())
            self._remove_button.setText("Remove videos")
            self._remove_button.setIcon(icons.get_icon("trash"))
            self._remove_button.setToolTip(
                "Remove selected videos from the library (files are not deleted)"
            )
            self._remove_button.setEnabled(selected)
            return
        selection = self._list.selectionModel()
        favorites_only = self._filter_tabs.currentIndex() == 2
        if favorites_only:
            self._remove_button.setText("Remove from favorites")
            self._remove_button.setIcon(icons.get_icon("star", theme.value("accent")))
            self._remove_button.setToolTip("Remove selected songs from favorites")
        else:
            self._remove_button.setText("Remove")
            self._remove_button.setIcon(icons.get_icon("trash"))
            self._remove_button.setToolTip(
                "Remove selected songs from the library (files are not deleted)"
            )
        self._remove_button.setEnabled(selection is not None and selection.hasSelection())
