from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.audio_backend import PlaybackState, volume_to_linear
from app.core.vlc_runtime import load_vlc_module


class VlcVideoBackend(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(object)
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._vlc = load_vlc_module()
        self._instance = self._vlc.Instance("--quiet")
        if self._instance is None:
            raise RuntimeError("VLC could not initialize its video engine.")
        self._player = self._instance.media_player_new()
        if self._player is None:
            self._instance.release()
            raise RuntimeError("VLC could not create a video player.")

        self._media: Any = None
        self._closed = False
        self._ended = False
        self._last_state = PlaybackState.STOPPED
        self._last_position = 0
        self._last_duration = 0
        events = self._player.event_manager()
        events.event_attach(
            self._vlc.EventType.MediaPlayerEndReached, self._on_end_reached
        )
        events.event_attach(
            self._vlc.EventType.MediaPlayerEncounteredError, self._on_error
        )

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._poll_player)
        self._timer.start()

    @property
    def state(self) -> PlaybackState:
        return self._map_state(self._player.get_state())

    @property
    def position(self) -> int:
        return max(0, int(self._player.get_time()))

    def open(self, path: str, window_id: int) -> bool:
        media_path = Path(path).resolve()
        if not media_path.is_file():
            self.error_occurred.emit("Video file was not found.")
            return False

        self.stop()
        self._player.set_hwnd(int(window_id))
        media = self._instance.media_new_path(str(media_path))
        if media is None:
            self.error_occurred.emit("VLC could not open this video.")
            return False

        self._player.set_media(media)
        self._media = media
        self._ended = False
        self._last_position = 0
        self._last_duration = 0
        self.position_changed.emit(0)
        if self._player.play() < 0:
            self.error_occurred.emit("VLC could not start video playback.")
            return False
        return True

    def play(self) -> None:
        if self._ended:
            self._player.set_time(0)
            self._ended = False
        if self._player.play() < 0:
            self.error_occurred.emit("VLC could not start video playback.")

    def pause(self) -> None:
        self._player.set_pause(1)

    def toggle_play_pause(self) -> None:
        if self.state is PlaybackState.PLAYING:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()
        self._player.set_media(None)
        self._media = None
        self._ended = False
        self._last_position = 0
        self._last_duration = 0

    def seek(self, position_ms: int) -> None:
        self._player.set_time(max(0, int(position_ms)))

    def set_volume(self, volume: float) -> None:
        self._player.audio_set_volume(round(volume_to_linear(volume) * 100))

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        events = self._player.event_manager()
        events.event_detach(self._vlc.EventType.MediaPlayerEndReached)
        events.event_detach(self._vlc.EventType.MediaPlayerEncounteredError)
        self.stop()
        self._player.release()
        self._instance.release()

    def _poll_player(self) -> None:
        state = self.state
        if state is not self._last_state:
            self._last_state = state
            self.state_changed.emit(state)

        position = self.position
        if position != self._last_position:
            self._last_position = position
            self.position_changed.emit(position)

        duration = max(0, int(self._player.get_length()))
        if duration and duration != self._last_duration:
            self._last_duration = duration
            self.duration_changed.emit(duration)

    def _on_end_reached(self, _event) -> None:
        if not self._closed:
            self._ended = True
            self.finished.emit()

    def _on_error(self, _event) -> None:
        if not self._closed:
            self.error_occurred.emit("VLC could not decode or play this video.")

    def _map_state(self, state) -> PlaybackState:
        if state == self._vlc.State.Playing:
            return PlaybackState.PLAYING
        if state == self._vlc.State.Paused:
            return PlaybackState.PAUSED
        return PlaybackState.STOPPED