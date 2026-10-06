"""Song list: model, delegate (custom painting) and view."""
from __future__ import annotations

import os
from typing import Sequence

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QBrush, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QListView, QMenu, QStyle, QStyledItemDelegate,
)

from app.models import Track, Video
from app.ui.theme import icons, theme
from app.utils.formatting import format_time

TrackRole = Qt.ItemDataRole.UserRole + 1
IsCurrentRole = Qt.ItemDataRole.UserRole + 2
UnavailableRole = Qt.ItemDataRole.UserRole + 3  # reason text, "" when playable
FavoriteRole = Qt.ItemDataRole.UserRole + 4
IsPlayingRole = Qt.ItemDataRole.UserRole + 5
AnimationPhaseRole = Qt.ItemDataRole.UserRole + 6
VideoRole = Qt.ItemDataRole.UserRole + 7
CoverRole = Qt.ItemDataRole.UserRole + 8


class TrackListModel(QAbstractListModel):
    cover_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._row_by_id: dict[int, int] = {}
        self._covers: dict[int, QPixmap] = {}
        self._requested_covers: set[int] = set()
        self._current_id: int | None = None
        self._is_playing = False
        self._animation_phase = 0
        self._unavailable: dict[int, str] = {}  # lazy cache of file checks

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tracks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._tracks):
            return None
        track = self._tracks[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return track.title
        if role == TrackRole:
            return track
        if role == CoverRole:
            if track.id not in self._requested_covers:
                self._requested_covers.add(track.id)
                self.cover_requested.emit(track.id)
            return self._covers.get(track.id)
        if role == IsCurrentRole:
            return track.id == self._current_id
        if role == UnavailableRole:
            return self._unavailable_reason(track)
        if role == FavoriteRole:
            return track.is_favorite
        if role == IsPlayingRole:
            return track.id == self._current_id and self._is_playing
        if role == AnimationPhaseRole:
            return self._animation_phase
        if role == VideoRole:
            return False
        if role == Qt.ItemDataRole.ToolTipRole:
            return "Remove from favorites" if track.is_favorite else "Add to favorites"
        return None

    def set_tracks(self, tracks: Sequence[Track]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self._row_by_id = {track.id: row for row, track in enumerate(self._tracks)}
        track_ids = set(self._row_by_id)
        self._covers = {
            track_id: cover
            for track_id, cover in self._covers.items()
            if track_id in track_ids
        }
        self._requested_covers.intersection_update(track_ids)
        self._unavailable = {}
        self.endResetModel()

    def set_cover(self, track_id: int, cover: QPixmap) -> None:
        if track_id not in self._row_by_id:
            return
        self._covers[track_id] = cover
        index = self.index(self._row_by_id[track_id])
        self.dataChanged.emit(index, index, [CoverRole])

    def set_current_id(self, track_id: int | None) -> None:
        previous, self._current_id = self._current_id, track_id
        for changed in (previous, track_id):
            self._notify_row(changed)

    def set_playing(self, is_playing: bool) -> None:
        if is_playing == self._is_playing:
            return
        self._is_playing = is_playing
        self._animation_phase = 0
        self._notify_row(self._current_id)

    def advance_animation(self) -> None:
        self._animation_phase = (self._animation_phase + 1) % 4
        self._notify_row(self._current_id)

    def mark_unavailable(self, track_id: int, reason: str) -> None:
        self._unavailable[track_id] = reason
        self._notify_row(track_id)

    def _notify_row(self, track_id: int | None) -> None:
        row = self._row_by_id.get(track_id) if track_id is not None else None
        if row is not None:
            index = self.index(row)
            self.dataChanged.emit(index, index)

    def _unavailable_reason(self, track: Track) -> str:
        reason = self._unavailable.get(track.id)
        if reason is None:
            reason = "" if os.path.isfile(track.path) else "File not found"
            self._unavailable[track.id] = reason
        return reason


class VideoTrackListModel(TrackListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._video_ids: set[int] = set()

    def set_videos(self, videos: Sequence[Video]) -> None:
        self._video_ids = {video.id for video in videos}
        self.set_tracks([
            Track(
                video.id, video.path, video.title, "Video", "", 0,
                is_favorite=video.is_favorite,
            )
            for video in videos
        ])

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if role == VideoRole:
            if not index.isValid() or not 0 <= index.row() < len(self._tracks):
                return None
            return self._tracks[index.row()].id in self._video_ids
        return super().data(index, role)


class TrackDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 72

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        track: Track | None = index.data(TrackRole)
        if track is None:
            return
        is_current = bool(index.data(IsCurrentRole))
        is_playing = bool(index.data(IsPlayingRole))
        is_video = bool(index.data(VideoRole))
        animation_phase = int(index.data(AnimationPhaseRole) or 0)
        unavailable: str = index.data(UnavailableRole) or ""
        is_favorite = bool(index.data(FavoriteRole))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        row = QRectF(option.rect).adjusted(4, 2, -4, -2)
        self._paint_background(painter, option, row, is_current)

        thumbnail_size = 44
        thumbnail_rect = QRect(
            int(row.left()) + 12,
            int(row.center().y()) - thumbnail_size // 2,
            thumbnail_size,
            thumbnail_size,
        )
        self._paint_thumbnail(
            painter,
            thumbnail_rect,
            index.data(CoverRole),
            is_video,
            unavailable,
        )

        # Text
        left = thumbnail_rect.right() + 14
        favorite_rect = self.favorite_rect(option.rect)
        has_active_indicator = is_playing and not is_video
        duration_width = 104 if has_active_indicator else 64
        duration_right = favorite_rect.left() - 10
        duration_rect = QRect(duration_right - duration_width, int(row.top()), duration_width,
                      int(row.height()))
        text_width = max(0, duration_rect.left() - 10 - left)
        top = int(row.top())

        title_font = QFont(option.font)
        title_font.setPixelSize(14)
        title_font.setWeight(QFont.Weight.DemiBold if is_current else QFont.Weight.Normal)
        sub_font = QFont(option.font)
        sub_font.setPixelSize(12)

        title_rect = QRect(left, top + 14, text_width, 20)
        sub_rect = QRect(left, top + 36, text_width, 18)
        align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        painter.setFont(title_font)
        painter.setPen(theme.color("text" if not unavailable else "text_dim"))
        painter.drawText(title_rect, align, painter.fontMetrics().elidedText(
            track.title, Qt.TextElideMode.ElideRight, text_width))

        painter.setFont(sub_font)
        if unavailable:
            painter.setPen(theme.color("danger"))
            subtitle = unavailable
        else:
            painter.setPen(theme.color("text_dim"))
            subtitle = " \u00b7 ".join(
                filter(None, [track.artist or "Unknown artist", track.album])
            )
        painter.drawText(sub_rect, align, painter.fontMetrics().elidedText(
            subtitle, Qt.TextElideMode.ElideRight, text_width))

        # Duration
        if track.duration_ms:
            painter.setFont(sub_font)
            painter.setPen(theme.color("text_dim"))
            time_rect = (
                self.duration_text_rect(duration_rect)
                if has_active_indicator else duration_rect
            )
            if has_active_indicator:
                indicator_rect = self.active_indicator_rect(time_rect)
                self._paint_equalizer(painter, indicator_rect, animation_phase)
            painter.drawText(
                time_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_time(track.duration_ms),
            )

        painter.drawPixmap(
            favorite_rect,
            icons.pixmap(
                "star-filled" if is_favorite else "star",
                64,
                theme.value("accent") if is_favorite else theme.value("text_dim"),
            ),
        )
        painter.restore()

    @staticmethod
    def _paint_thumbnail(
        painter: QPainter,
        rect: QRect,
        cover: QPixmap | None,
        is_video: bool,
        unavailable: str,
    ) -> None:
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), 7, 7)
        painter.setClipPath(clip)

        if cover is not None and not cover.isNull():
            scaled = cover.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            source = QRect(
                (scaled.width() - rect.width()) // 2,
                (scaled.height() - rect.height()) // 2,
                rect.width(),
                rect.height(),
            )
            painter.drawPixmap(rect, scaled, source)
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, theme.color("surface_alt"))
            gradient.setColorAt(1.0, theme.color("accent_soft"))
            painter.fillRect(rect, QBrush(gradient))
            icon = "film" if is_video else "music"
            color = theme.value("danger") if unavailable else theme.value("text_dim")
            icon_size = 24
            painter.drawPixmap(
                QRect(
                    rect.center().x() - icon_size // 2,
                    rect.center().y() - icon_size // 2,
                    icon_size,
                    icon_size,
                ),
                icons.pixmap(icon, 64, color),
            )

        painter.restore()

    @staticmethod
    def duration_text_rect(duration_rect: QRect) -> QRect:
        width = 64
        return QRect(
            duration_rect.right() - width + 1,
            duration_rect.top(),
            width,
            duration_rect.height(),
        )

    @staticmethod
    def active_indicator_rect(time_rect: QRect) -> QRect:
        width = 16
        height = 22
        return QRect(
            time_rect.left() - 22,
            time_rect.center().y() - (height - 1) // 2,
            width,
            height,
        )

    @staticmethod
    def _paint_equalizer(painter: QPainter, rect: QRect, phase: int) -> None:
        heights = ((7, 15, 10), (13, 8, 16), (16, 10, 6), (9, 16, 12))[phase]
        bar_width = 3
        gap = 3
        total_width = bar_width * len(heights) + gap * (len(heights) - 1)
        left = rect.center().x() - total_width // 2
        baseline = rect.bottom() - 2
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.color("accent_hover"))
        for index, height in enumerate(heights):
            painter.drawRoundedRect(
                QRect(left + index * (bar_width + gap), baseline - height + 1,
                      bar_width, height),
                1,
                1,
            )
        painter.restore()

    @staticmethod
    def favorite_rect(rect: QRect) -> QRect:
        row = QRectF(rect).adjusted(4, 2, -4, -2)
        size = 18
        return QRect(
            int(row.right()) - 16 - size,
            int(row.center().y()) - size // 2,
            size,
            size,
        )

    @staticmethod
    def _paint_background(painter: QPainter, option, row: QRectF, is_current: bool) -> None:
        path = QPainterPath()
        path.addRoundedRect(row, 10, 10)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillPath(path, theme.color("selection"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillPath(path, theme.color("hover"))
        if is_current:
            tint = theme.color("accent")
            tint.setAlpha(48)
            painter.fillPath(path, tint)


class TrackListView(QListView):
    track_activated = Signal(int)   # track id
    play_next_requested = Signal(int)
    queue_add_requested = Signal(int)
    remove_requested = Signal()
    favorite_toggled = Signal(int, bool)  # track id, favorite state

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(TrackDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.Shape.NoFrame)
        self._favorite_pressed: QModelIndex | None = None
        self._animations_visible = False
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(120)
        self._animation_timer.timeout.connect(self._advance_animation)
        self.clicked.connect(self._on_clicked)

    def set_playing(self, is_playing: bool) -> None:
        self.model().set_playing(is_playing)
        self._sync_animation_timer()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._animations_visible = True
        self._sync_animation_timer()

    def hideEvent(self, event) -> None:
        self._animations_visible = False
        self._animation_timer.stop()
        super().hideEvent(event)

    def selected_track_ids(self) -> list[int]:
        selection = self.selectionModel()
        if selection is None:
            return []
        return [index.data(TrackRole).id for index in selection.selectedIndexes()]

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentIndex().isValid():
            self._emit_activated(self.currentIndex())
        elif key == Qt.Key.Key_Delete and self.selected_track_ids():
            self.remove_requested.emit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and TrackDelegate.favorite_rect(self.visualRect(index)).contains(
                event.position().toPoint()
            ):
                self._favorite_pressed = index
                event.accept()
                return
        self._favorite_pressed = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        index = self._favorite_pressed
        self._favorite_pressed = None
        if index is not None and event.button() == Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            if index.isValid() and TrackDelegate.favorite_rect(self.visualRect(index)).contains(point):
                track: Track | None = index.data(TrackRole)
                if track is not None:
                    self.favorite_toggled.emit(track.id, not track.is_favorite)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        if index not in self.selectionModel().selectedIndexes():
            self.setCurrentIndex(index)
        menu = QMenu(self)
        if index.data(VideoRole):
            open_action = menu.addAction("Open video")
            track: Track | None = index.data(TrackRole)
            favorite_action = menu.addAction(
                "Remove from favorites" if track and track.is_favorite
                else "Add to favorites"
            )
            remove_action = menu.addAction("Remove from library")
            chosen = menu.exec(event.globalPos())
            if chosen is open_action:
                self._emit_activated(index)
            elif chosen is favorite_action and track is not None:
                self.favorite_toggled.emit(track.id, not track.is_favorite)
            elif chosen is remove_action:
                self.remove_requested.emit()
            return
        play_action = menu.addAction("Play")
        track: Track | None = index.data(TrackRole)
        play_next_action = menu.addAction("Play next")
        queue_add_action = menu.addAction("Move to end of queue")
        favorite_action = menu.addAction(
            "Remove from favorites" if track and track.is_favorite else "Add to favorites"
        )
        remove_action = menu.addAction("Remove from library")
        chosen = menu.exec(event.globalPos())
        if chosen is play_action:
            self._emit_activated(index)
        elif chosen is play_next_action and track is not None:
            self.play_next_requested.emit(track.id)
        elif chosen is queue_add_action and track is not None:
            self.queue_add_requested.emit(track.id)
        elif chosen is favorite_action and track is not None:
            self.favorite_toggled.emit(track.id, not track.is_favorite)
        elif chosen is remove_action:
            self.remove_requested.emit()

    def _on_clicked(self, index: QModelIndex) -> None:
        multi_select = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        if QGuiApplication.keyboardModifiers() & multi_select:
            return  # user is building a selection, don't start playback
        self._emit_activated(index)

    def _emit_activated(self, index: QModelIndex) -> None:
        track: Track | None = index.data(TrackRole)
        if track is not None:
            self.track_activated.emit(track.id)

    def _sync_animation_timer(self) -> None:
        model: TrackListModel = self.model()
        has_current_row = model._current_id in model._row_by_id
        if self._animations_visible and model._is_playing and has_current_row:
            self._animation_timer.start()
        else:
            self._animation_timer.stop()

    def _advance_animation(self) -> None:
        model: TrackListModel = self.model()
        model.advance_animation()
        row = model._row_by_id.get(model._current_id)
        if row is not None:
            self.viewport().update(self.visualRect(model.index(row)))
