# Muzo Player

**Muzo Player 1.0.0** is a Windows desktop music and video player built with
PySide6, LibVLC, and SQLite.

## Features

- Import and search supported audio and video files or scan folders.
- Play music with queue, shuffle, repeat, volume, and equalizer controls.
- Create, rename, reorder, and delete playlists.
- Keep separate music and video favorites.
- Watch videos in the player, including immersive fullscreen controls and
  subtitle selection.
- Choose an accent color and resume the saved music playback session.
- Store the library, playlists, favorites, and settings locally.

Supported import extensions:

- Audio: `.mp3`, `.wav`, `.ogg`
- Video: `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.webm`, `.mpeg`, `.mpg`,
  `.m4v`

## Run from source

Requirements: Windows 10/11 (64-bit), Python 3.11 or newer, and 64-bit VLC
Media Player. VLC supplies the audio/video engine and equalizer. In development,
install 64-bit VLC or set `VLC_HOME` to the folder containing `libvlc.dll`.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Portable Windows build

The single-file PyInstaller build includes the official 64-bit VLC runtime and
plugins. The build uses a matching local VLC runtime when available; otherwise,
it downloads the version pinned in `vlc-runtime-version.txt` from VideoLAN's
official download service. The runtime is cached in `.vlc-runtime`. End users
do not need VLC installed separately.

```powershell
python -m pip install -r requirements-build.txt
.\build_portable.ps1
```

The output is `dist\Muzo Player.exe`. The bundled VLC files are embedded in that
executable and extracted to PyInstaller's temporary `_MEIPASS\vlc` directory
at launch. The build is local and is not uploaded by the build script. For a
release, publish it separately as a GitHub release asset when ready.

## Data location

The SQLite database is stored at
`%APPDATA%\MusicPlayer\library.db`. Removing or replacing the application
executable does not remove this database.

## Development checks

Run the test suite from the project root:

```powershell
python -m unittest discover -s tests
```

## Project layout

```text
app/core       playback, library, video, and playlist services
app/data       SQLite database and repositories
app/workers    background media scanning
app/ui         screens, widgets, theme, and application chrome
tests          unit and UI lifecycle tests
main.py        application entry point
```
