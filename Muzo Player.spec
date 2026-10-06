# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

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
    binaries=[],
    datas=[
        ("Muzo Player.ico", "."),
        ("app/assets/logo.png", "app/assets"),
        ("app/ui/theme/styles.qss", "app/ui/theme"),
    ],
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
