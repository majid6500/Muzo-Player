# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

project_root = Path(SPECPATH)
vlc_version = (project_root / "vlc-runtime-version.txt").read_text(
    encoding="ascii"
).strip()
vlc_runtime = project_root / ".vlc-runtime" / vlc_version
required_vlc_files = (
    vlc_runtime / "libvlc.dll",
    vlc_runtime / "libvlccore.dll",
    vlc_runtime / "plugins",
)
if not all(path.exists() for path in required_vlc_files):
    raise FileNotFoundError(
        f"VLC {vlc_version} runtime not found at {vlc_runtime}. "
        "Run build_portable.ps1 to download the official 64-bit runtime."
    )

vlc_binaries = []
vlc_datas = []
for path in vlc_runtime.rglob("*"):
    if not path.is_file() or path.suffix.lower() == ".exe":
        continue
    destination = (Path("vlc") / path.relative_to(vlc_runtime).parent).as_posix()
    item = (str(path), destination)
    if path.suffix.lower() == ".dll":
        vlc_binaries.append(item)
    else:
        vlc_datas.append(item)

version = (1, 0, 0, 0)
version_text = ".".join(str(part) for part in version[:3])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=version,
        prodvers=version,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "Muzo Player"),
                        StringStruct("FileDescription", "Muzo Player"),
                        StringStruct("FileVersion", version_text),
                        StringStruct("InternalName", "Muzo Player"),
                        StringStruct("OriginalFilename", "Muzo Player.exe"),
                        StringStruct("ProductName", "Muzo Player"),
                        StringStruct("ProductVersion", version_text),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=vlc_binaries,
    datas=[
        ("Muzo Player.ico", "."),
        ("app/assets/logo.png", "app/assets"),
        ("app/ui/theme/styles.qss", "app/ui/theme"),
    ] + vlc_datas,
    hiddenimports=["vlc"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Muzo Player",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["Muzo Player.ico"],
    version=version_info,
)
