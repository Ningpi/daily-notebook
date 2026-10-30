# -*- mode: python ; coding: utf-8 -*-
# 每日记事本 PyInstaller 打包配置（在 Windows 上执行）
import sys

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('assets/icon.ico', 'assets'), ('assets/icons', 'assets/icons')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'PIL', 'scipy', 'unittest', 'pydoc_data'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='每日记事本',
    debug=False,
    strip=False,
    upx=False,
    console=False,             # 窗口程序，不弹黑框
    icon='assets/icon.ico',
    version='version_info.txt',
)
