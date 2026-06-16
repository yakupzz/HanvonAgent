# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — HanvonAgent tray app

a = Analysis(
    ['HanvonAgent/main.py'],
    pathex=['D:\\Projeler\\F710'],
    binaries=[],
    datas=[
        ('HanvonAgent/hanvon.ico', 'HanvonAgent'),
    ],
    hiddenimports=[
        'PySide6',
        'dotenv',
        'sqlalchemy',
        'pydantic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HanvonAgent',
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
    icon='HanvonAgent/hanvon.ico',
)
