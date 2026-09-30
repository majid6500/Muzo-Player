from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout, QWidget

from app.ui.theme import icons, theme
from app.ui.widgets.buttons import make_push_button


class EmptyState(QWidget):
    add_files_clicked = Signal()
    add_folder_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh_theme()

        title = QLabel("Your library is empty")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Add some songs or a whole folder to get started.")
        subtitle.setObjectName("Subtle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._files_button = make_push_button("Add files", "file-plus")
        self._folder_button = make_push_button("Add folder", "folder-plus", primary=True)
        self._files_button.clicked.connect(lambda: self.add_files_clicked.emit())
        self._folder_button.clicked.connect(lambda: self.add_folder_clicked.emit())

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        buttons.addWidget(self._files_button)
        buttons.addWidget(self._folder_button)
        buttons.addStretch()

        layout.addWidget(self._icon_label)
        layout.addSpacing(6)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addLayout(buttons)

    def set_busy(self, busy: bool) -> None:
        self._files_button.setEnabled(not busy)
        self._folder_button.setEnabled(not busy)

    def refresh_theme(self) -> None:
        pixmap = icons.pixmap("music", 144, theme.value("accent")).copy()
        pixmap.setDevicePixelRatio(2.0)
        self._icon_label.setPixmap(pixmap)
