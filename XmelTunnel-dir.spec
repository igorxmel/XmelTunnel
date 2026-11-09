# -*- mode: python ; coding: utf-8 -*-
# Folder build for the installer: no self-extraction at start, fewer antivirus false positives.
# Use build.py: it writes build/version_info.txt first.
EXCLUDES = ['tkinter', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtQml', 'PyQt6.QtQuick',
            'PyQt6.QtMultimedia', 'PyQt6.QtPdf', 'PyQt6.Qt3DCore', 'PyQt6.QtBluetooth', 'PyQt6.QtSql']

a = Analysis(['xmeltunnel/__main__.py'], pathex=['.'],
             datas=[('assets/flags', 'assets/flags'), ('assets/icon.png', 'assets')],
             hiddenimports=['PyQt6.QtSvg'], excludes=EXCLUDES, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='XmelTunnel', debug=False, strip=False, upx=False,
          console=False, icon='assets/icon.ico', version='build/version_info.txt')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='XmelTunnel')
