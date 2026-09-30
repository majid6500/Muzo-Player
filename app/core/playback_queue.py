"""Play order with shuffle and repeat rules. Pure Python, no Qt."""
from __future__ import annotations

import random
from enum import Enum
from typing import Sequence


class RepeatMode(Enum):
    OFF = "off"
    ALL = "all"
    ONE = "one"


class PlaybackQueue:
    """Holds track ids in play order and a pointer to the current one."""

    def __init__(self) -> None:
        self._ids: list[int] = []
        self._order: list[int] = []
        self._position = -1
        self._shuffle = False
        self._repeat = RepeatMode.OFF

    def __len__(self) -> int:
        return len(self._order)

    @property
    def current_id(self) -> int | None:
        if 0 <= self._position < len(self._order):
            return self._order[self._position]
        return None

    @property
    def shuffle_enabled(self) -> bool:
        return self._shuffle

    @property
    def repeat_mode(self) -> RepeatMode:
        return self._repeat

    def set_tracks(self, track_ids: Sequence[int]) -> None:
        current = self.current_id
        new_ids = list(track_ids)
        if self._shuffle:
            available = set(new_ids)
            previous = set(self._ids)
            order = [track_id for track_id in self._order if track_id in available]
            added = [track_id for track_id in new_ids if track_id not in previous]
            random.shuffle(added)
            order.extend(added)
            self._order = order
            self._position = order.index(current) if current in order else -1
        else:
            self._order = new_ids
            self._position = new_ids.index(current) if current in new_ids else -1
        self._ids = new_ids

    def set_shuffle(self, enabled: bool) -> None:
        if enabled != self._shuffle:
            self._shuffle = enabled
            self._rebuild(self.current_id)

    def set_repeat(self, mode: RepeatMode) -> None:
        self._repeat = mode

    def set_current(self, track_id: int) -> bool:
        try:
            self._position = self._order.index(track_id)
        except ValueError:
            return False
        return True

    def next_id(self, *, auto: bool) -> int | None:
        """Advance and return the next id, or None at the end of the queue.

        auto=True means the previous song ended by itself (repeat-one applies).
        """
        if not self._order:
            return None
        if auto and self._repeat is RepeatMode.ONE:
            return self.current_id
        following = self._position + 1
        if following < len(self._order):
            self._position = following
            return self.current_id
        if self._repeat is RepeatMode.OFF:
            return None
        self._rebuild(None)  # wrap around (reshuffles when shuffle is on)
        self._position = 0
        return self.current_id

    def previous_id(self) -> int | None:
        if not self._order:
            return None
        if self._position > 0:
            self._position -= 1
        elif self._repeat is not RepeatMode.OFF:
            self._position = len(self._order) - 1
        return self.current_id

    def _rebuild(self, keep_id: int | None) -> None:
        order = list(self._ids)
        if self._shuffle:
            random.shuffle(order)
            if keep_id in order:
                order.remove(keep_id)
                order.insert(0, keep_id)
        self._order = order
        self._position = order.index(keep_id) if keep_id in order else -1
