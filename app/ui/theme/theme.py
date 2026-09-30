"""Color palette and stylesheet loading. Add a palette + call set_palette() for new themes."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor

DARK_PALETTE: dict[str, str] = {
    "bg": "#101311",
    "surface": "#171c19",
    "surface_alt": "#202723",
    "hover": "#29332d",
    "selection": "#263a31",
    "border": "#2d3932",
    "text": "#edf3ef",
    "text_dim": "#9ba9a1",
    "accent": "#08764c",
    "accent_text": "#ffffff",
    "accent_hover": "#0b8759",
    "accent_pressed": "#065f3f",
    "accent_disabled": "#294a3b",
    "accent_soft": "#1d3d2d",
    "scrollbar": "#315e45",
    "danger": "#ff6b7a",
}
DEFAULT_ACCENT = DARK_PALETTE["accent"]

_QSS_PATH = Path(__file__).with_name("styles.qss")
_active: dict[str, str] = dict(DARK_PALETTE)


def set_palette(palette: dict[str, str]) -> None:
    _active.clear()
    _active.update(palette)


def set_accent_color(value: str) -> bool:
    accent = QColor(value)
    if not accent.isValid():
        return False

    accent = accent.toRgb()
    _active["accent"] = accent.name()
    _active["accent_hover"] = accent.lighter(122).name()
    _active["accent_pressed"] = accent.darker(125).name()
    _active["accent_disabled"] = _blend(
        QColor(_active["surface_alt"]), accent, 0.56
    )
    _active["accent_soft"] = _blend(QColor(_active["bg"]), accent, 0.31)
    _active["selection"] = _blend(
        QColor(_active["surface_alt"]), accent, 0.27
    )
    _active["hover"] = _blend(QColor(_active["surface_alt"]), accent, 0.09)
    _active["scrollbar"] = _blend(QColor(_active["border"]), accent, 0.58)

    dark_text = QColor(_active["bg"])
    white_contrast = 1.05 / (_relative_luminance(accent) + 0.05)
    dark_contrast = (_relative_luminance(accent) + 0.05) / (
        _relative_luminance(dark_text) + 0.05
    )
    _active["accent_text"] = dark_text.name() if dark_contrast > white_contrast else "#ffffff"
    return True


def _blend(background: QColor, foreground: QColor, amount: float) -> str:
    channels = [
        round(background_channel * (1 - amount) + foreground_channel * amount)
        for background_channel, foreground_channel in zip(
            background.getRgb()[:3], foreground.getRgb()[:3]
        )
    ]
    return QColor(*channels).name()


def _relative_luminance(color: QColor) -> float:
    channels = color.getRgbF()[:3]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def value(name: str) -> str:
    return _active[name]


def color(name: str) -> QColor:
    return QColor(_active[name])


def load_stylesheet() -> str:
    qss = _QSS_PATH.read_text(encoding="utf-8")
    # Longest names first so "$text_dim" is not clobbered by "$text".
    for name in sorted(_active, key=len, reverse=True):
        qss = qss.replace(f"${name}", _active[name])
    return qss
