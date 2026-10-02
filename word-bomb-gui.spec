# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: GUI (main.py). Run from repo root: pyinstaller word-bomb-gui.spec

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    "keyboard",
    "keyboard._winkeyboard",
    "pytesseract",
    "mss",
    "mss.windows",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL._tkinter_finder",
    "requests",
    "certifi",
    # Windows built-in OCR (pywinrt): the projection modules are imported lazily
    # by winrt itself, so list them all.
    *collect_submodules("winrt"),
]

# Offline word lists (+ licence notice).
datas = [
    ("data/enable1.txt.gz", "data"),
    ("data/arabic-words.txt.gz", "data"),
    ("data/ARABIC-WORDS-NOTICE.md", "data"),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="WordBombGUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
