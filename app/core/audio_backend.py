"""Audio engine interface and its QtMultimedia implementation.

Everything above this file talks only to AudioBackend. To add an equalizer
later, write another backend (e.g. miniaudio/VLC based) with the same
methods and signals and swap it in bootstrap.py.
"""
from __future__ import annotations

from enum import Enum
from typing import Sequence

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


def volume_to_linear(volume: float) -> float:
    """Map the 0-1 volume slider directly to linear output gain."""
    return min(1.0, max(0.0, float(volume)))


class PlaybackState(Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


class AudioBackend(QObject):
    """Interface: subclasses implement the methods and emit the signals."""

    position_changed = Signal(int)   # milliseconds
    duration_changed = Signal(int)   # milliseconds
    state_changed = Signal(object)   # PlaybackState
    finished = Signal()              # current media played to its end
    error_occurred = Signal(str)

    @property
    def state(self) -> PlaybackState:
        raise NotImplementedError

    @property
    def position(self) -> int:
        raise NotImplementedError

    def load(self, path: str) -> None:
        raise NotImplementedError

    def unload(self) -> None:
        raise NotImplementedError

    def play(self) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def seek(self, position_ms: int) -> None:
        raise NotImplementedError

    def set_volume(self, volume: float) -> None:
        """volume is 0.0-1.0 on a perceptual scale."""
        raise NotImplementedError

    @property
    def equalizer_frequencies(self) -> tuple[float, ...]:
        return ()

    @property
    def equalizer_presets(self) -> dict[str, tuple[float, ...]]:
        return {}

    def set_equalizer(self, enabled: bool, gains: Sequence[float]) -> None:
        if enabled:
            raise RuntimeError("This audio backend does not support an equalizer.")


_STATE_MAP = {
    QMediaPlayer.PlaybackState.StoppedState: PlaybackState.STOPPED,
    QMediaPlayer.PlaybackState.PlayingState: PlaybackState.PLAYING,
    QMediaPlayer.PlaybackState.PausedState: PlaybackState.PAUSED,
}


class QtAudioBackend(AudioBackend):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)

        self._player.positionChanged.connect(
            lambda position: self.position_changed.emit(int(position))
        )

        self._player.durationChanged.connect(
            lambda duration: self.duration_changed.emit(int(duration))
        )
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_error)

    @property
    def state(self) -> PlaybackState:
        return _STATE_MAP[self._player.playbackState()]

    @property
    def position(self) -> int:
        return int(self._player.position())

    def load(self, path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(path))

    def unload(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(max(0, int(position_ms)))

    def set_volume(self, volume: float) -> None:
        self._output.setVolume(volume_to_linear(volume))

    def _on_state_changed(self, qt_state: QMediaPlayer.PlaybackState) -> None:
        self.state_changed.emit(_STATE_MAP[qt_state])

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finished.emit()

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.error_occurred.emit(message)
