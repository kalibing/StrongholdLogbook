# -*- mode: python ; coding: utf-8 -*-
# 打包「本机助手」单文件 exe：pyinstaller agent/ArknightsAchvAgent.spec
# 源码：agent/achv_agent.py；产物默认落在 dist/，正式分发用 scripts/build-agent.ps1

a = Analysis(
    ['achv_agent.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='ArknightsAchvAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
