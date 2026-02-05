# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['sevue.pyw'],
    pathex=[],
    binaries=[('libmediapipe.dll', 'mediapipe\\tasks\\c')],
    datas=[('model', 'model'), ('icons', 'icons')],
    hiddenimports=['mediapipe', 'pyvirtualcam', 'mediapipe.python', 'mediapipe.python._framework_bindings', 'mediapipe.python._framework_bindings.image', 'cv2', 'mediapipe.tasks.c'],
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icons\\favicon.ico'],
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
