"""LibVLC playback backend with its built-in audio equalizer."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, QTimer
from app.core.audio_backend import AudioBackend, PlaybackState, volume_to_linear
from app.core.vlc_runtime import load_vlc_module


class VlcAudioBackend(AudioBackend):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._vlc = load_vlc_module()
        self._instance = self._vlc.Instance("--no-video", "--quiet")
        if self._instance is None:
            raise RuntimeError("VLC could not initialize its audio engine.")
        self._player = self._instance.media_player_new()
        if self._player is None:
            self._instance.release()
            raise RuntimeError("VLC could not create an audio player.")

        self._media = None
        self._closed = False
        self._last_state = PlaybackState.STOPPED
        self._last_position = 0
        self._last_duration = 0
        self._frequencies = tuple(
            float(self._vlc.libvlc_audio_equalizer_get_band_frequency(index))
            for index in range(self._vlc.libvlc_audio_equalizer_get_band_count())
        )
        self._presets = self._read_presets()

        events = self._player.event_manager()
        events.event_attach(
            self._vlc.EventType.MediaPlayerEndReached, self._on_end_reached
        )
        events.event_attach(
            self._vlc.EventType.MediaPlayerEncounteredError, self._on_error
        )

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll_player)
        self._timer.start()

    @property
    def state(self) -> PlaybackState:
        return self._map_state(self._player.get_state())

    @property
    def position(self) -> int:
        position = int(self._player.get_time())
        return max(0, position)

    @property
    def equalizer_frequencies(self) -> tuple[float, ...]:
        return self._frequencies

    @property
    def equalizer_presets(self) -> dict[str, tuple[float, ...]]:
        return dict(self._presets)

    def load(self, path: str) -> None:
        media = self._instance.media_new_path(str(Path(path).resolve()))
        if media is None:
            self.error_occurred.emit("VLC could not open this file.")
            return
        self._player.set_media(media)
        self._media = media
        self._last_position = 0
        self._last_duration = 0
        self.position_changed.emit(0)

    def unload(self) -> None:
        self._player.stop()
        self._player.set_media(None)
        self._media = None
        self._last_position = 0
        self._last_duration = 0

    def play(self) -> None:
        if self._player.play() < 0:
            self.error_occurred.emit("VLC could not start playback.")

    def pause(self) -> None:
        self._player.set_pause(1)

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        self._player.set_time(max(0, int(position_ms)))

    def set_volume(self, volume: float) -> None:
        linear = volume_to_linear(volume)
        self._player.audio_set_volume(round(linear * 100))

    def set_equalizer(self, enabled: bool, gains: Sequence[float]) -> None:
        if len(gains) != len(self._frequencies):
            raise ValueError(f"Expected {len(self._frequencies)} equalizer bands.")
        if not enabled:
            if self._player.set_equalizer(None) < 0:
                raise RuntimeError("VLC could not disable the equalizer.")
            return

        equalizer = self._vlc.AudioEqualizer()
        if equalizer is None:
            raise RuntimeError("VLC could not create an equalizer.")
        try:
            for index, gain in enumerate(gains):
                equalizer.set_amp_at_index(
                    min(20.0, max(-20.0, float(gain))), index
                )
            if self._player.set_equalizer(equalizer) < 0:
                raise RuntimeError("VLC could not apply the equalizer settings.")
        finally:
            equalizer.release()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        events = self._player.event_manager()
        events.event_detach(self._vlc.EventType.MediaPlayerEndReached)
        events.event_detach(self._vlc.EventType.MediaPlayerEncounteredError)
        self._player.stop()
        self._player.set_media(None)
        self._media = None
        self._player.release()
        self._instance.release()

    def _read_presets(self) -> dict[str, tuple[float, ...]]:
        presets: dict[str, tuple[float, ...]] = {}
        count = self._vlc.libvlc_audio_equalizer_get_preset_count()
        for index in range(count):
            name = self._vlc.libvlc_audio_equalizer_get_preset_name(index)
            if not name:
                continue
            equalizer = self._vlc.libvlc_audio_equalizer_new_from_preset(index)
            if equalizer is None:
                continue
            try:
                presets[name.decode("utf-8")] = tuple(
                    float(equalizer.get_amp_at_index(band))
                    for band in range(len(self._frequencies))
                )
            finally:
                equalizer.release()
        return presets

    def _poll_player(self) -> None:
        state = self.state
        if state is not self._last_state:
            self._last_state = state
            self.state_changed.emit(state)

        position = self.position
        if position != self._last_position:
            self._last_position = position
            self.position_changed.emit(position)

        duration = int(self._player.get_length())
        if duration > 0 and duration != self._last_duration:
            self._last_duration = duration
            self.duration_changed.emit(duration)

    def _on_end_reached(self, _event) -> None:
        if not self._closed:
            self.finished.emit()

    def _on_error(self, _event) -> None:
        if not self._closed:
            self.error_occurred.emit("VLC could not decode or play this file.")

    def _map_state(self, state) -> PlaybackState:
        if state == self._vlc.State.Playing:
            return PlaybackState.PLAYING
        if state == self._vlc.State.Paused:
            return PlaybackState.PAUSED
        return PlaybackState.STOPPED