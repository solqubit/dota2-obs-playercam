# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: folder build (onedir), no console, no UPX, with version info.
# Usage (from the project root):
#   .venv\Scripts\pyinstaller packaging/overpower_cams.spec --noconfirm
import os
import sys

import PySide6

RAIZ = os.path.dirname(SPECPATH)  # SPECPATH = the packaging/ folder

# Resolve native dependencies only from this Python/Qt installation and Windows.
# A developer's PATH may contain other applications' DLLs: e.g. Poppler's icuuc.dll
# has the same name as Windows ICU but incompatible exports, breaking Qt at startup.
# This changes only the build process environment, never the user's saved PATH.
windows = os.environ.get('SystemRoot', r'C:\Windows')
os.environ['PATH'] = os.pathsep.join([
    os.path.join(windows, 'System32'), windows,
    sys.base_prefix, os.path.join(sys.base_prefix, 'DLLs'),
    os.path.dirname(PySide6.__file__),
])

a = Analysis(
    [os.path.join(RAIZ, 'packaging', 'run_app.py')],
    pathex=[RAIZ],
    binaries=[],
    datas=[(os.path.join(RAIZ, 'assets', 'Borde.png'), 'assets'),
           (os.path.join(RAIZ, 'assets', 'Mascara camara.png'), 'assets'),
           (os.path.join(RAIZ, 'assets', 'Marco sin camara.png'), 'assets'),
           (os.path.join(RAIZ, 'overpower_cams', 'data', 'innate_abilities.json'), 'overpower_cams/data')],
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
