from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QPushButton, QToolButton

from app.ui.theme import icons, theme


def make_tool_button(
    icon_name: str,
    tooltip: str,
    *,
    size: int = 44,
    icon_size: int = 22,
    color: str | None = None,
) -> QToolButton:
    button = QToolButton()
    button.setIcon(icons.get_icon(icon_name, color))
    button.setIconSize(QSize(icon_size, icon_size))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setFixedSize(size, size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button


def make_push_button(
    text: str, icon_name: str, *, primary: bool = False
) -> QPushButton:
    button = QPushButton(text)
    button.setIcon(icons.get_icon(icon_name, theme.value("accent_text") if primary else None))
    button.setIconSize(QSize(18, 18))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAccessibleName(text)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if primary:
        button.setProperty("variant", "primary")
    return button
