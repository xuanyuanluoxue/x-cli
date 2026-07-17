# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the public Windows x64 portable executable."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).parent
WEB_DATA = collect_data_files("core.web")
PLUGIN_MODULES = collect_submodules("plugins")

a = Analysis(
    [str(PROJECT_ROOT / "x.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=WEB_DATA,
    hiddenimports=PLUGIN_MODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="x-windows-x86_64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
