# Music Player

Modern dark music player for Windows (PySide6 + SQLite + mutagen).

## Setup (Windows, Python 3.11+)

Install 64-bit VLC Media Player before launching the app. VLC is used for audio playback and equalizer processing.

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python main.py

Library is stored in `%APPDATA%\MusicPlayer\library.db`.

## Layout

    app/core     playback + library logic (no widgets)
    app/data     SQLite (schema migrations, repositories)
    app/workers  background folder scanning
    app/ui       screens, widgets, theme (QSS + icons)
    app/bootstrap.py  the only place components are wired together
