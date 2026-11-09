# -*- mode: python ; coding: utf-8 -*-
# Build: .venv\Scripts\pyinstaller XmelTunnel.spec  ->  dist\XmelTunnel.exe
a = Analysis(
    ['xmeltunnel/__main__.py'],
    pathex=['.'],
    datas=[('assets/flags', 'assets/flags'), ('assets/icon.png', 'assets')],
    hiddenimports=['PyQt6.QtSvg'],
    excludes=['tkinter', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtQml', 'PyQt6.QtQuick',
              'PyQt6.QtMultimedia', 'PyQt6.QtPdf', 'PyQt6.Qt3DCore', 'PyQt6.QtBluetooth', 'PyQt6.QtSql'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='XmelTunnel', debug=False, strip=False, upx=False,
          console=False, icon='assets/icon.ico')
