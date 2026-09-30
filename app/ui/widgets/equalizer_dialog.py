from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
    QSlider, QVBoxLayout,
)

from app.core.player_service import PlayerService


class EqualizerDialog(QDialog):
    def __init__(self, player: PlayerService, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Equalizer")
        self.setMinimumWidth(720)
        self._player = player
        self._presets = player.equalizer_presets
        self._syncing = False
        self._sliders: list[QSlider] = []
        self._gain_labels: list[QLabel] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)

        self._enabled = QCheckBox("Enable equalizer")
        self._enabled.setChecked(player.equalizer_enabled)
        self._preset = QComboBox()
        self._preset.addItem("Custom")
        self._preset.addItems(list(self._presets))
        self._preset.setMinimumWidth(190)
        self._select_current_preset(player.equalizer_gains)

        reset_button = QPushButton("Reset")
        reset_button.setToolTip("Reset all bands to flat")
        top = QHBoxLayout()
        top.addWidget(self._enabled)
        top.addStretch()
        top.addWidget(QLabel("Preset"))
        top.addWidget(self._preset)
        top.addWidget(reset_button)
        root.addLayout(top)

        bands = QHBoxLayout()
        bands.setSpacing(12)
        for index, (frequency, gain) in enumerate(
            zip(player.equalizer_frequencies, player.equalizer_gains)
        ):
            column = QVBoxLayout()
            column.setSpacing(8)
            gain_label = QLabel(self._format_gain(gain))
            gain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(-120, 120)
            slider.setValue(round(gain * 10))
            slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
            slider.setTickInterval(40)
            slider.setMinimumHeight(220)
            slider.setFixedWidth(38)
            slider.setToolTip(f"{self._format_frequency(frequency)} band")
            frequency_label = QLabel(self._format_frequency(frequency))
            frequency_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(gain_label)
            column.addWidget(slider, 1, Qt.AlignmentFlag.AlignHCenter)
            column.addWidget(frequency_label)
            bands.addLayout(column, 1)
            self._sliders.append(slider)
            self._gain_labels.append(gain_label)
            slider.valueChanged.connect(
                lambda value, band=index: self._on_gain_changed(band, value)
            )
        root.addLayout(bands, 1)

        close_button = QPushButton("Close")
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)
        root.addLayout(close_row)

        self._enabled.toggled.connect(
            lambda enabled: self._player.set_equalizer(enabled=enabled)
        )
        self._preset.currentIndexChanged.connect(self._on_preset_changed)
        reset_button.clicked.connect(lambda: self._preset.setCurrentText("Flat"))
        close_button.clicked.connect(self.accept)

    def _on_gain_changed(self, band: int, value: int) -> None:
        self._gain_labels[band].setText(self._format_gain(value / 10))
        if self._syncing:
            return
        if self._preset.currentIndex() != 0:
            self._preset.setCurrentIndex(0)
        gains = [slider.value() / 10 for slider in self._sliders]
        self._player.set_equalizer(gains=gains)

    def _on_preset_changed(self, index: int) -> None:
        if self._syncing or index == 0:
            return
        gains = self._presets.get(self._preset.itemText(index))
        if gains is None:
            return

        self._syncing = True
        for slider, gain in zip(self._sliders, gains):
            slider.setValue(round(gain * 10))
        signals_were_blocked = self._enabled.blockSignals(True)
        self._enabled.setChecked(True)
        self._enabled.blockSignals(signals_were_blocked)
        self._syncing = False
        self._player.set_equalizer(enabled=True, gains=gains)

    def _select_current_preset(self, gains: list[float]) -> None:
        selected = 0
        for index, preset_gains in enumerate(self._presets.values(), start=1):
            if len(gains) == len(preset_gains) and all(
                abs(current - preset) < 0.05
                for current, preset in zip(gains, preset_gains)
            ):
                selected = index
                break
        self._preset.setCurrentIndex(selected)

    @staticmethod
    def _format_gain(gain: float) -> str:
        return f"{gain:+.1f} dB"

    @staticmethod
    def _format_frequency(frequency: float) -> str:
        if frequency >= 1000:
            return f"{frequency / 1000:g} kHz"
        return f"{frequency:g} Hz"