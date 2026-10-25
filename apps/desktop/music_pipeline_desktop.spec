# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

root = Path(SPECPATH).resolve()  # SPECPATH is provided by PyInstaller

block_cipher = None

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root), str(root.parent.parent)],
    binaries=[],
    datas=[
        (str(root / "resources" / "style.qss"), "resources"),
        (str(root / "resources" / "desktop.ui"), "resources"),
        (str(root.parent.parent / "tools" / "setup.ps1"), "tools"),
        (str(root.parent.parent / "tools" / "setup.sh"), "tools"),
    ],
    hiddenimports=["core", "core.queue_manager", "core.research"],
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
    [],
    exclude_binaries=True,
    name="MusicPipeline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MusicPipeline",
)
