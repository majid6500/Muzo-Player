from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

BOTTOM_OFFSET = 104


class Toast(QLabel):
    """Non-blocking message that fades out on its own."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, *, error: bool = False, duration_ms: int = 4500) -> None:
        self.setProperty("error", "true" if error else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(text)
        self.show()
        self.reposition()
        self.raise_()
        self._timer.start(duration_ms)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None or not self.isVisible():
            return
        max_width = max(240, min(560, parent.width() - 48))
        text_width = self.fontMetrics().horizontalAdvance(self.text()) + 60
        width = min(max_width, text_width)
        self.setFixedWidth(width)
        self.setFixedHeight(max(46, self.heightForWidth(width)))
        self.move(
            (parent.width() - self.width()) // 2,
            parent.height() - self.height() - BOTTOM_OFFSET,
        )
