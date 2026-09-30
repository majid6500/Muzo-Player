from __future__ import annotations


def format_time(milliseconds: int) -> str:
    """Format a duration as m:ss or h:mm:ss."""
    total_seconds = max(0, int(milliseconds)) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"
