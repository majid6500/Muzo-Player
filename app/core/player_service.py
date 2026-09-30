"""Playback logic: what plays, what comes next, and how failures are handled.

Depends on AudioBackend, LibraryService and PlaybackQueue only; the UI
calls its methods and listens to its signals.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.audio_backend import AudioBackend, PlaybackState
from app.core.library_service import LibraryService
from app.core.playback_queue import PlaybackQueue, RepeatMode
from app.data.settings_repository import SettingsRepository
from app.models import Track

RESTART_THRESHOLD_MS = 3000
DEFAULT_VOLUME = 0.7


class PlayerService(QObject):
    current_track_changed = Signal(object)  # Track | None
    state_changed = Signal(object)          # PlaybackState
    position_changed = Signal(int)
    duration_changed = Signal(int)
    volume_changed = Signal(float)
    muted_changed = Signal(bool)
    modes_changed = Signal()                # shuffle / repeat
    queue_changed = Signal()
    equalizer_changed = Signal(bool, list)  # enabled, band gains in dB
    track_failed = Signal(int, str)         # track id, short reason
    error_occurred = Signal(str)            # user-facing message

    def __init__(
        self,
        backend: AudioBackend,
        library: LibraryService,
        queue: PlaybackQueue,
        settings: SettingsRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._library = library
        self._queue = queue
        self._settings = settings

        self._current: Track | None = None
        self._want_playing = False
        self._track_ended = False
        self._failed_track_id: int | None = None
        self._consecutive_failures = 0
        self._volume = DEFAULT_VOLUME
        self._last_nonzero_volume = DEFAULT_VOLUME
        self._muted = False
        self._equalizer_frequencies = backend.equalizer_frequencies
        self._equalizer_presets = backend.equalizer_presets
        self._equalizer_enabled = False
        self._equalizer_gains = [0.0] * len(self._equalizer_frequencies)

        backend.position_changed.connect(self.position_changed)
        backend.duration_changed.connect(self._on_backend_duration)
        backend.state_changed.connect(self._on_state_changed)
        backend.finished.connect(self._on_finished)
        backend.error_occurred.connect(self._on_backend_error)
        library.library_changed.connect(self._on_library_changed)

        self._queue.set_tracks([t.id for t in library.tracks()])
        self._backend.set_volume(self._volume)
        self._backend.set_equalizer(False, self._equalizer_gains)

    # ---- state ----
    @property
    def current_track(self) -> Track | None:
        return self._current

    @property
    def state(self) -> PlaybackState:
        return self._backend.state

    @property
    def position(self) -> int:
        return self._backend.position

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_muted(self) -> bool:
        return self._muted or self._volume == 0

    @property
    def shuffle_enabled(self) -> bool:
        return self._queue.shuffle_enabled

    @property
    def repeat_mode(self) -> RepeatMode:
        return self._queue.repeat_mode

    @property
    def queue_track_ids(self) -> tuple[int, ...]:
        return self._queue.track_ids

    @property
    def equalizer_frequencies(self) -> tuple[float, ...]:
        return self._equalizer_frequencies

    @property
    def equalizer_presets(self) -> dict[str, tuple[float, ...]]:
        return dict(self._equalizer_presets)

    @property
    def equalizer_enabled(self) -> bool:
        return self._equalizer_enabled

    @property
    def equalizer_gains(self) -> list[float]:
        return list(self._equalizer_gains)

    # ---- commands ----
    def play_track(self, track_id: int) -> bool:
        """Start a track chosen by the user. Returns False if it cannot start."""
        current = self._current
        if current and current.id == track_id and self._failed_track_id != track_id:
            self._want_playing = True
            self._rewind_if_ended()
            if self.state is not PlaybackState.PLAYING:
                self._backend.play()
            return True
        self._consecutive_failures = 0
        return self._start(track_id)

    def toggle_play_pause(self) -> None:
        if self.state is PlaybackState.PLAYING:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if self._current is None:
            tracks = self._library.tracks()
            if tracks:
                self.play_track(tracks[0].id)
            return
        if self._failed_track_id == self._current.id:
            self._consecutive_failures = 0
            self._start(self._current.id)
            return
        self._rewind_if_ended()
        self._want_playing = True
        self._backend.play()

    def pause(self) -> None:
        self._want_playing = False
        self._backend.pause()

    def next(self) -> None:
        if self._current is None:
            return
        next_id = self._queue.next_id(auto=False)
        if next_id is not None:
            self._consecutive_failures = 0
            self._start(next_id, sync_queue=False)

    def previous(self) -> None:
        if self._current is None:
            return
        if self._backend.position > RESTART_THRESHOLD_MS:
            self._backend.seek(0)
            return
        previous_id = self._queue.previous_id()
        if previous_id is None or previous_id == self._current.id:
            self._backend.seek(0)
            return
        self._consecutive_failures = 0
        self._start(previous_id, sync_queue=False)

    def seek(self, position_ms: int) -> None:
        self._backend.seek(position_ms)

    def set_volume(self, volume: float) -> None:
        self._volume = min(1.0, max(0.0, volume))
        if self._volume > 0:
            self._last_nonzero_volume = self._volume
            self._muted = False
        self._backend.set_volume(0.0 if self._muted else self._volume)
        self.volume_changed.emit(self._volume)
        self.muted_changed.emit(self.is_muted)

    def toggle_mute(self) -> None:
        if self.is_muted:
            if self._volume == 0:
                self._volume = self._last_nonzero_volume or DEFAULT_VOLUME
            self._muted = False
        else:
            self._muted = True
        self._backend.set_volume(0.0 if self.is_muted else self._volume)
        self.volume_changed.emit(self._volume)
        self.muted_changed.emit(self.is_muted)

    def set_equalizer(
        self, *, enabled: bool | None = None, gains: Sequence[float] | None = None
    ) -> None:
        if gains is not None:
            if len(gains) != len(self._equalizer_frequencies):
                raise ValueError(
                    f"Expected {len(self._equalizer_frequencies)} equalizer bands."
                )
            normalized = []
            for gain in gains:
                value = float(gain)
                normalized.append(min(12.0, max(-12.0, value)) if math.isfinite(value) else 0.0)
            self._equalizer_gains = normalized
        if enabled is not None:
            self._equalizer_enabled = bool(enabled)
        self._backend.set_equalizer(
            self._equalizer_enabled, self._equalizer_gains
        )
        self.equalizer_changed.emit(
            self._equalizer_enabled, list(self._equalizer_gains)
        )

    def set_shuffle(self, enabled: bool) -> None:
        self._queue.set_shuffle(enabled)
        self.modes_changed.emit()
        self.queue_changed.emit()

    def set_queue_order(self, track_ids: Sequence[int]) -> None:
        self._queue.set_order(track_ids)
        self.queue_changed.emit()

    def play_next(self, track_id: int) -> bool:
        moved = self._queue.move_after_current(track_id)
        if moved:
            self.queue_changed.emit()
        return moved

    def add_to_queue(self, track_id: int) -> bool:
        moved = self._queue.move_to_end(track_id)
        if moved:
            self.queue_changed.emit()
        return moved

    def cycle_repeat(self) -> None:
        order = [RepeatMode.OFF, RepeatMode.ALL, RepeatMode.ONE]
        following = order[(order.index(self._queue.repeat_mode) + 1) % len(order)]
        self._queue.set_repeat(following)
        self.modes_changed.emit()

    # ---- session persistence ----
    def restore_session(self) -> None:
        """Restore volume, modes and the last track (paused, not playing)."""
        try:
            self.set_volume(float(self._settings.get("volume", str(DEFAULT_VOLUME))))
        except ValueError:
            self.set_volume(DEFAULT_VOLUME)
        self._muted = self._settings.get("muted") == "1"
        self._backend.set_volume(0.0 if self.is_muted else self._volume)
        self.muted_changed.emit(self.is_muted)
        self._queue.set_shuffle(self._settings.get("shuffle") == "1")
        try:
            self._queue.set_repeat(RepeatMode(self._settings.get("repeat", "off")))
        except ValueError:
            self._queue.set_repeat(RepeatMode.OFF)
        self.modes_changed.emit()

        try:
            stored_gains = json.loads(self._settings.get("equalizer_gains", "[]") or "[]")
            if not isinstance(stored_gains, list):
                raise ValueError("Invalid equalizer settings")
            gains = [float(gain) for gain in stored_gains]
            if len(gains) != len(self._equalizer_frequencies):
                raise ValueError("Invalid equalizer band count")
        except (TypeError, ValueError):
            gains = [0.0] * len(self._equalizer_frequencies)
        self.set_equalizer(
            enabled=self._settings.get("equalizer_enabled") == "1",
            gains=gains,
        )

        last_id = self._settings.get("last_track_id")
        if last_id and last_id.isdigit():
            track = self._library.get_track(int(last_id))
            if track and Path(track.path).is_file():
                self._start(track.id, autoplay=False)

    def save_state(self) -> None:
        self._settings.set("volume", f"{self._volume:.3f}")
        self._settings.set("muted", "1" if self._muted else "0")
        self._settings.set("shuffle", "1" if self._queue.shuffle_enabled else "0")
        self._settings.set("repeat", self._queue.repeat_mode.value)
        self._settings.set("equalizer_enabled", "1" if self._equalizer_enabled else "0")
        self._settings.set("equalizer_gains", json.dumps(self._equalizer_gains))
        self._settings.set("last_track_id", str(self._current.id) if self._current else "")

    # ---- internals ----
    def _start(self, track_id: int, *, autoplay: bool = True, sync_queue: bool = True) -> bool:
        track = self._library.get_track(track_id)
        if track is None:
            return False
        self._failed_track_id = None
        self._track_ended = False
        if sync_queue:
            self._queue.set_current(track_id)
        self._current = track
        self._want_playing = autoplay

        self.current_track_changed.emit(track)
        self.position_changed.emit(0)
        self.duration_changed.emit(track.duration_ms)

        if not Path(track.path).is_file():
            self._fail(track, "the file was not found", "File not found")
            return False
        self._backend.load(track.path)
        if autoplay:
            self._backend.play()
        return True

    def _fail(self, track: Track, detail: str, short_reason: str) -> None:
        if self._failed_track_id == track.id:
            return  # backends can report the same error more than once
        self._failed_track_id = track.id
        self._backend.unload()
        self.track_failed.emit(track.id, short_reason)
        self.error_occurred.emit(f"Can't play \u201c{track.title}\u201d: {detail}.")

        if not self._want_playing:
            return
        self._consecutive_failures += 1
        if self._consecutive_failures < len(self._queue):
            QTimer.singleShot(0, self._advance_after_failure)
        else:
            self._want_playing = False  # every song failed: stop instead of looping

    def _advance_after_failure(self) -> None:
        if not self._want_playing:
            return
        next_id = self._queue.next_id(auto=False)
        if next_id is None:
            self._want_playing = False
            return
        self._start(next_id, sync_queue=False)

    def _on_backend_duration(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self.duration_changed.emit(duration_ms)

    def _on_state_changed(self, state: PlaybackState) -> None:
        if state is PlaybackState.PLAYING:
            self._consecutive_failures = 0
        self.state_changed.emit(state)

    def _on_finished(self) -> None:
        next_id = self._queue.next_id(auto=True)
        if next_id is None:
            self._want_playing = False
            self._track_ended = True
            self._backend.stop()
        else:
            self._start(next_id, sync_queue=False)

    def _rewind_if_ended(self) -> None:
        if not self._track_ended:
            return
        self._backend.seek(0)
        self._track_ended = False
        self.position_changed.emit(0)

    def _on_backend_error(self, message: str) -> None:
        if self._current is not None:
            self._fail(
                self._current,
                message or "the file is corrupted or unsupported",
                "Can't be played",
            )

    def _on_library_changed(self) -> None:
        self._queue.set_tracks([t.id for t in self._library.tracks()])
        self.queue_changed.emit()
        if self._current and self._library.get_track(self._current.id) is None:
            self._want_playing = False
            self._failed_track_id = None
            self._backend.unload()
            self._current = None
            self.current_track_changed.emit(None)
            self.position_changed.emit(0)
            self.duration_changed.emit(0)
