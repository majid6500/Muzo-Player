from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_DLL_DIRECTORIES = []


def _configure_bundled_vlc() -> None:
    bundle_root = Path(sys._MEIPASS) / "vlc"
    library = bundle_root / "libvlc.dll"
    plugins = bundle_root / "plugins"
    if not library.is_file() or not plugins.is_dir():
        raise RuntimeError(
            "The bundled VLC runtime is incomplete. Rebuild or reinstall Muzo Player."
        )

    _DLL_DIRECTORIES.append(os.add_dll_directory(str(bundle_root)))
    os.environ["PYTHON_VLC_LIB_PATH"] = str(library)
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(plugins)
    os.environ["VLC_PLUGIN_PATH"] = str(plugins)


def load_vlc_module():
    frozen = bool(getattr(sys, "frozen", False))
    if frozen and sys.platform == "win32":
        _configure_bundled_vlc()
    elif sys.platform == "win32":
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
        if frozen:
            raise RuntimeError(
                "The bundled VLC runtime could not be loaded. Rebuild or reinstall "
                "Muzo Player."
            ) from exc
        raise RuntimeError(
            "VLC Media Player (64-bit) is required. Install VLC and restart the app."
        ) from exc

    if not vlc.libvlc_get_version():
        if frozen:
            raise RuntimeError(
                "The bundled VLC runtime could not be initialized. Rebuild or "
                "reinstall Muzo Player."
            )
        raise RuntimeError(
            "VLC Media Player (64-bit) could not be loaded. Install VLC and restart the app."
        )
    return vlc