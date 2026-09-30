from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_DLL_DIRECTORIES = []


def load_vlc_module():
    if sys.platform == "win32":
        candidates = [
            Path(os.environ["VLC_HOME"]) if os.environ.get("VLC_HOME") else None,
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "VideoLAN" / "VLC",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "VideoLAN" / "VLC",
        ]
        for directory in candidates:
            if directory is not None and (directory / "libvlc.dll").is_file():
                _DLL_DIRECTORIES.append(os.add_dll_directory(str(directory)))
                plugins = directory / "plugins"
                if plugins.is_dir():
                    os.environ.setdefault("VLC_PLUGIN_PATH", str(plugins))
                break

    try:
        vlc = importlib.import_module("vlc")
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "VLC Media Player (64-bit) is required. Install VLC and restart the app."
        ) from exc

    if not vlc.libvlc_get_version():
        raise RuntimeError(
            "VLC Media Player (64-bit) could not be loaded. Install VLC and restart the app."
        )
    return vlc