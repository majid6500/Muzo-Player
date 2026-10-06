from __future__ import annotations

from PySide6.QtCore import QStandardPaths, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar,
    QLineEdit, QStackedWidget, QTabBar, QToolButton,
    QVBoxLayout, QWidget,
)
from app.config import APP_NAME, app_logo_path
from app.config import is_supported, is_video_supported, media_file_dialog_filter
from app.core.audio_backend import PlaybackState
from app.core.library_service import LibraryService
from app.core.player_service import PlayerService
from app.core.playlist_service import PlaylistService
from app.core.video_library_service import VideoLibraryService
from app.models import Track
from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_push_button, make_tool_button
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.mini_player import MiniPlayer
from app.ui.widgets.playlist_panel import PlaylistPanel
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
    add_to_playlist_requested = Signal(list)

    def __init__(
        self,
        library: LibraryService,
        video_library: VideoLibraryService,
        player: PlayerService,
        playlists: PlaylistService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._library = library
        self._video_library = video_library
        self._player = player
        self._playlists = playlists
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

        self._count_label = QLabel()
        self._count_label.setObjectName("Subtle")

        home_icon = QLabel()
        home_icon.setObjectName("HomeIcon")
        home_icon.setPixmap(icons.pixmap("home", 22, theme.value("text_dim")))
        self._brand_icon = QLabel()
        self._brand_icon.setObjectName("BrandIcon")
        self._brand_icon.setPixmap(
            QPixmap(str(app_logo_path())).scaled(
                30, 30,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        brand_name = QLabel(APP_NAME)
        brand_name.setObjectName("ScreenTitle")
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_row.addWidget(home_icon)
        brand_row.addWidget(self._brand_icon)
        brand_row.addWidget(brand_name)
        titles = QVBoxLayout()
        titles.setSpacing(5)
        titles.addLayout(brand_row)
        titles.addWidget(self._count_label)

        self._remove_button = make_push_button("Remove", "trash")
        self._playlist_button = make_push_button("Add to playlist", "music")
        self._playlist_button.setVisible(False)
        self._remove_button.setToolTip(
            "Remove selected items from the library (files are not deleted)"
        )
        self._add_button = make_push_button("Add media", "folder-plus", primary=True)
        self._add_menu = QMenu(self._add_button)
        self._add_menu.addAction("Add audio or video files...", self._choose_files)
        self._add_menu.addAction("Add media folder...", self._choose_folder)
        self._add_button.setMenu(self._add_menu)
        self._accent_button = make_tool_button("droplet", "Accent color", size=40)
        self._accent_menu = QMenu(self._accent_button)
        self._accent_menu.addAction("Choose accent color...", self._choose_accent_color)
        self._accent_menu.addAction(
            "Reset to emerald green",
            lambda: self.accent_color_selected.emit(theme.DEFAULT_ACCENT),
        )
        self._accent_button.setMenu(self._accent_menu)
        self._accent_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.refresh_theme()
        self._filter_tabs = QTabBar()
        self._filter_tabs.addTab("All songs")
        self._filter_tabs.addTab("All videos")
        self._filter_tabs.addTab("Favorites")
        self._filter_tabs.addTab("Playlists")
        self._favorite_tabs = QTabBar()
        self._favorite_tabs.setObjectName("FavoriteTypeTabs")
        self._favorite_tabs.addTab("Songs")
        self._favorite_tabs.addTab("Videos")
        self._favorite_tabs.hide()

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(self._add_button)
        header.addWidget(self._accent_button)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self._filter_tabs)
        toolbar.addStretch()
        toolbar.addWidget(self._remove_button)
        toolbar.addWidget(self._playlist_button)
        self._video_button = make_push_button("Open video", "film")
        toolbar.addWidget(self._video_button)

        self._search = QLineEdit()
        self._search.setObjectName("LibrarySearch")
        self._search.setPlaceholderText("Search title, artist, or album")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(180)
        self._search.setMaximumWidth(320)
        self._search_action = self._search.addAction(
            icons.get_icon("search", theme.value("text_dim")),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        toolbar.addWidget(self._search)
        root.addLayout(toolbar)

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
        favorites_empty_subtitle = QLabel("Star a song or video to keep it here.")
        favorites_empty_subtitle.setObjectName("Subtle")
        favorites_empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        favorites_empty_layout.addWidget(favorites_empty_title)
        favorites_empty_layout.addWidget(favorites_empty_subtitle)
        self._favorite_videos_empty = QLabel("No favorite videos yet")
        self._favorite_videos_empty.setObjectName("Subtle")
        self._favorite_videos_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self._media_page = QWidget()
        media_layout = QVBoxLayout(self._media_page)
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(10)
        self._favorites_header = QWidget()
        favorites_header = QHBoxLayout(self._favorites_header)
        favorites_header.setContentsMargins(0, 0, 0, 0)
        favorites_title = QLabel("Favorites")
        favorites_title.setObjectName("FavoritesSectionTitle")
        favorites_header.addWidget(favorites_title)
        favorites_header.addStretch()
        favorites_header.addWidget(self._favorite_tabs)
        media_layout.addWidget(self._favorites_header)
        self._media_stack = QStackedWidget()
        for page in (
            self._empty,
            self._favorites_empty,
            self._list,
            self._no_results,
            self._video_list,
            self._videos_empty,
            self._favorite_videos_empty,
        ):
            self._media_stack.addWidget(page)
        media_layout.addWidget(self._media_stack, 1)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._media_page)
        self._playlist_panel = PlaylistPanel(
            self._library, self._player, self._playlists
        )
        self._stack.addWidget(self._playlist_panel)
        root.addWidget(self._stack, 1)

        self._mini_player = MiniPlayer(self._library, self._player)
        root.addWidget(self._mini_player)

    def _connect_signals(self) -> None:
        self._remove_button.clicked.connect(self._remove_selected)
        self._playlist_button.clicked.connect(
            lambda: self.add_to_playlist_requested.emit(
                self._list.selected_track_ids()
            )
        )
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
        self._video_list.favorite_toggled.connect(self._on_video_favorite_toggled)
        self._filter_tabs.currentChanged.connect(self._reload_tracks)
        self._favorite_tabs.currentChanged.connect(self._reload_tracks)
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
        self._model.cover_requested.connect(self._request_track_cover)
        self._library.cover_loaded.connect(self._on_cover_loaded)

    # ---- library / player events ----
    def _reload_tracks(self) -> None:
        if self._filter_tabs.currentIndex() == 3:
            self._favorites_header.hide()
            self._count_label.clear()
            self._search.hide()
            self._stack.setCurrentWidget(self._playlist_panel)
            self._update_actions()
            return
        self._search.show()
        favorites_only = self._filter_tabs.currentIndex() == 2
        self._favorites_header.setVisible(favorites_only)
        self._favorite_tabs.setVisible(favorites_only)
        self._stack.setCurrentWidget(self._media_page)
        videos_selected = (
            self._filter_tabs.currentIndex() == 1
            or favorites_only and self._favorite_tabs.currentIndex() == 1
        )
        self._search.setPlaceholderText(
            "Search video titles"
            if videos_selected
            else "Search title, artist, or album"
        )
        if videos_selected:
            self._reload_videos()
            self._update_actions()
            return
        self._filter_tabs.setTabText(2, "Favorites")
        all_tracks = self._library.tracks()
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
        if not all_tracks and not favorites_only:
            self._media_stack.setCurrentWidget(self._empty)
        elif favorites_only and not tracks:
            self._media_stack.setCurrentWidget(
                self._no_results if query.strip() else self._favorites_empty
            )
        elif query.strip() and not tracks:
            self._media_stack.setCurrentWidget(self._no_results)
        else:
            self._media_stack.setCurrentWidget(self._list)
        current = self._player.current_track
        self._model.set_current_id(current.id if current else None)
        self._list.set_playing(self._player.state is PlaybackState.PLAYING)

    def _reload_videos(self) -> None:
        selected_ids = set(self._video_list.selected_track_ids())
        query = self._search.text().strip().casefold()
        all_videos = self._video_library.videos()
        favorites_only = (
            self._filter_tabs.currentIndex() == 2
            and self._favorite_tabs.currentIndex() == 1
        )
        videos = [
            video for video in all_videos
            if query in video.title.casefold()
            and (not favorites_only or video.is_favorite)
        ]
        self._filter_tabs.setTabText(1, "All videos")
        if self._filter_tabs.currentIndex() != 1 and not favorites_only:
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

        self._count_label.setText(
            f"{len(videos)} favorite videos" if favorites_only
            else f"{len(videos)} videos"
        )
        empty_widget = (
            self._favorite_videos_empty if favorites_only else self._videos_empty
        )
        self._stack.setCurrentWidget(self._media_page)
        self._media_stack.setCurrentWidget(
            self._video_list if videos else empty_widget
        )
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
        video_view_active = (
            self._filter_tabs.currentIndex() == 1
            or self._filter_tabs.currentIndex() == 2
            and self._favorite_tabs.currentIndex() == 1
        )
        if video_view_active:
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

    def _on_video_favorite_toggled(
        self, video_id: int, is_favorite: bool
    ) -> None:
        self._video_library.set_favorite(video_id, is_favorite)

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
        video_view_active = (
            self._filter_tabs.currentIndex() == 1
            or self._filter_tabs.currentIndex() == 2
            and self._favorite_tabs.currentIndex() == 1
        )
        if video_view_active:
            video_ids = self._video_list.selected_track_ids()
            if self._filter_tabs.currentIndex() == 2:
                self._video_library.set_favorites(video_ids, False)
            else:
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
        if hasattr(self, "_video_list"):
            self._video_list.viewport().update()

    def _request_track_cover(self, track_id: int) -> None:
        data = self._library.get_cover(track_id)
        if data is None:
            return
        cover = QPixmap()
        if cover.loadFromData(data):
            self._model.set_cover(track_id, cover)

    def _on_cover_loaded(self, track_id: int, data: bytes | None) -> None:
        if not data:
            return
        cover = QPixmap()
        if cover.loadFromData(data):
            self._model.set_cover(track_id, cover)

    # ---- helpers ----
    def _set_import_buttons_enabled(self, enabled: bool) -> None:
        self._add_button.setEnabled(enabled)
        self._empty.set_busy(not enabled)

    def _update_actions(self) -> None:
        if self._filter_tabs.currentIndex() == 3:
            self._remove_button.hide()
            self._playlist_button.hide()
            self._video_button.hide()
            return
        video_view_active = (
            self._filter_tabs.currentIndex() == 1
            or self._filter_tabs.currentIndex() == 2
            and self._favorite_tabs.currentIndex() == 1
        )
        if video_view_active:
            selected = bool(self._video_list.selected_track_ids())
            if self._filter_tabs.currentIndex() == 2:
                self._remove_button.setText("Remove from favorites")
                self._remove_button.setIcon(
                    icons.get_icon("star", theme.value("accent"))
                )
                self._remove_button.setToolTip(
                    "Remove selected videos from favorites"
                )
            else:
                self._remove_button.setText("Remove videos")
                self._remove_button.setIcon(icons.get_icon("trash"))
                self._remove_button.setToolTip(
                    "Remove selected videos from the library (files are not deleted)"
                )
            self._remove_button.setEnabled(selected)
            self._remove_button.setVisible(selected)
            self._playlist_button.setVisible(False)
            self._video_button.setVisible(True)
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
        selected = selection is not None and selection.hasSelection()
        self._remove_button.setEnabled(selected)
        self._remove_button.setVisible(selected)
        self._playlist_button.setEnabled(selected)
        self._playlist_button.setVisible(selected)
        self._video_button.setVisible(False)
