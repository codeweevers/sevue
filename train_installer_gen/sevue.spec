# -*- mode: python ; coding: utf-8 -*-
import pathlib
import sys
parent_dir = pathlib.Path(__name__).resolve().parent
EXT = {
    "win32": "dll",
    "linux": "so",
    "darwin": "dylib",  # optional
}[sys.platform]
lib_file = parent_dir / f"libmediapipe.{EXT}"
a = Analysis(
    [parent_dir.parent / "sevue.pyw"],
    pathex=[parent_dir.parent],
    binaries=[(str(lib_file), "mediapipe/tasks/c")],
    datas=[('../data', 'data'), ('../icons', 'icons')],
    hiddenimports=['mediapipe', 'pyvirtualcam', 'cv2', 'mediapipe.tasks.c', 'controllers', 'models', 'views', 'workers'],
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
    [],
    exclude_binaries=True,
    name='Sevue',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['..\\icons\\favicon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Sevue',
)
