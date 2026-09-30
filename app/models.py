"""Plain data structures shared by all layers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewTrack:
    """A track that was scanned but is not stored yet (no id)."""

    path: str
    title: str
    artist: str
    album: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class Track:
    """A track stored in the library."""

    id: int
    path: str
    title: str
    artist: str
    album: str
    duration_ms: int
    is_favorite: bool = False
