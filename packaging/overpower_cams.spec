# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: folder build (onedir), no console, no UPX, with version info.
# Usage (from the project root):
#   .venv\Scripts\pyinstaller packaging/overpower_cams.spec --noconfirm
import os

RAIZ = os.path.dirname(SPECPATH)  # SPECPATH = the packaging/ folder

a = Analysis(
    [os.path.join(RAIZ, 'packaging', 'run_app.py')],
    pathex=[RAIZ],
    binaries=[],
    datas=[(os.path.join(RAIZ, 'assets', 'Borde.png'), 'assets'),
           (os.path.join(RAIZ, 'overpower_cams', 'data', 'innate_passives.json'), 'overpower_cams/data')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Qt and other modules the app does not use: smaller build, fewer antivirus false positives.
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.Qt3DCore', 'PySide6.QtPdf',
              'tkinter', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,       # onedir: binaries live in the folder, not inside the .exe
    name='DotaPlayerCams',
    debug=False,
    strip=False,
    upx=False,                   # no UPX: compressed executables trigger the most antivirus false positives
    console=False,
    version=os.path.join(RAIZ, 'packaging', 'version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='DotaPlayerCams',
)
