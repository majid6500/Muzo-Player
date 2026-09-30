"""Reading tags and cover art with mutagen."""
from __future__ import annotations

import base64
import os
from pathlib import Path

import mutagen
from mutagen.flac import Picture
from mutagen.id3 import ID3

from app.models import NewTrack


def _first_tag(audio: mutagen.FileType, key: str) -> str:
    try:
        values = audio.get(key)
    except Exception:
        return ""
    if not values:
        return ""
    return str(values[0]).strip()


def read_metadata(path: Path) -> NewTrack | None:
    """Return track info, or None if the file is not readable audio."""
    try:
        audio = mutagen.File(str(path), easy=True)
    except Exception:  # mutagen raises many different errors for bad files
        return None
    if audio is None or audio.info is None:
        return None

    length_seconds = getattr(audio.info, "length", 0) or 0
    return NewTrack(
        path=os.path.abspath(path),
        title=_first_tag(audio, "title") or path.stem,
        artist=_first_tag(audio, "artist"),
        album=_first_tag(audio, "album"),
        duration_ms=int(length_seconds * 1000),
    )


def read_cover(path: Path) -> bytes | None:
    """Return embedded cover image bytes, or None."""
    try:
        audio = mutagen.File(str(path))
        tags = getattr(audio, "tags", None)
        if tags is None:
            return None
        if isinstance(tags, ID3):
            frames = tags.getall("APIC")
            return frames[0].data if frames else None
        if "metadata_block_picture" in tags:  # Ogg Vorbis
            raw = base64.b64decode(tags["metadata_block_picture"][0])
            return Picture(raw).data
    except Exception:
        return None
    return None
