from __future__ import annotations

import ctypes
import sys
import warnings

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.theme import theme


def apply_native_titlebar_theme(window: QWidget) -> bool:
    """Apply the current palette to a native Windows title bar."""
    if sys.platform != "win32" or getattr(window, "_titlebar_theme_attempted", False):
        return False
    app = QApplication.instance()
    if app is None or app.platformName() == "offscreen":
        return False
    window._titlebar_theme_attempted = True

    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        )
        set_attribute.restype = ctypes.c_long
    except (AttributeError, OSError) as exc:
        warnings.warn(f"Could not load Windows title bar theming: {exc}")
        return False

    hwnd = ctypes.c_void_p(int(window.winId()))
    attributes = (
        (35, colorref(theme.value("bg"))),
        (36, colorref(theme.value("text"))),
    )
    succeeded = True
    for attribute, color in attributes:
        value = ctypes.c_uint(color)
        result = set_attribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )
        if result < 0:
            succeeded = False
            warnings.warn(
                f"Windows rejected title bar color attribute {attribute} "
                f"(HRESULT 0x{result & 0xffffffff:08X})."
            )
    window._titlebar_theme_applied = succeeded
    return succeeded


def colorref(value: str) -> int:
    color = QColor(value)
    return color.red() | (color.green() << 8) | (color.blue() << 16)
