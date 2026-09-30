# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：`pyinstaller vidporter.spec` 产出 dist/vidporter-gui.exe。

onefile 单文件；静态网页资源随包内置；yt_dlp 的提取器靠静态扫描 +
社区 hook 收集。控制台窗口保留，便于查看日志与 Ctrl+C 退出。
"""

a = Analysis(
    [r"src\vidporter\gui_main.py"],
    pathex=[r"src"],
    binaries=[],
    datas=[(r"src\vidporter\web\static", r"vidporter\web\static")],
    hiddenimports=["yt_dlp"],
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
    a.binaries,
    a.datas,
    [],
    name="vidporter-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
