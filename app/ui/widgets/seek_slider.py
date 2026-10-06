from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QSlider, QStyle


class SeekSlider(QSlider):
    """Horizontal slider that jumps to the clicked position.

    scrubbed: emitted while the user presses/drags.
    committed: emitted once when the user releases.
    Programmatic updates go through set_position() and are ignored mid-drag.
    """

    scrubbed = Signal(int)
    committed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("SeekSlider")
        self._dragging = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def set_position(self, value: int) -> None:
        if not self._dragging:
            self.setValue(value)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            self._update_from(event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._update_from(event)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.committed.emit(self.value())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def _update_from(self, event: QMouseEvent) -> None:
        x = min(max(int(event.position().x()), 0), self.width())
        value = QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), x, max(1, self.width())
        )
        self.setValue(value)
        self.scrubbed.emit(value)
