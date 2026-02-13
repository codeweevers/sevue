# -*- mode: python ; coding: utf-8 -*-
import os
parent_dir = os.path.abspath(os.path.join(os.getcwd(), ".."))
a = Analysis(
    ['..\\sevue.pyw'],
    pathex=[parent_dir],
    binaries=[('libmediapipe.dll', 'mediapipe\\tasks\\c')],
    datas=[('..\\data', 'data'), ('..\\icons', 'icons')],
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
