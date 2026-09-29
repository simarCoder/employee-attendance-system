# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("operon.ico", "."),
]

binaries = []
hiddenimports = []

# PyWebView has backend-specific imports that PyInstaller
# may not discover automatically.
tmp = collect_all("webview")

datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]

# ReportLab uses several dynamically imported submodules for PDF output.
tmp = collect_all("reportlab")
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]


a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HR_Management_System",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="operon.ico",
)

# Build the replacement helper as a small side-by-side executable. Windows
# cannot replace the main one-file executable while it is running.
updater_analysis = Analysis(
    ["updater_helper.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

updater_pyz = PYZ(updater_analysis.pure)

updater_exe = EXE(
    updater_pyz,
    updater_analysis.scripts,
    updater_analysis.binaries,
    updater_analysis.datas,
    [],
    name="HR_Management_System_Updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="operon.ico",
)
