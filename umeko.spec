# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：umeko server 单文件 exe。

用法：pyinstaller umeko.spec
产物：dist/umeko-server.exe（内嵌全部源码与静态资源；
      运行时数据 server_data/ 与 .env 落在 exe 同目录）
"""

a = Analysis(
    ["run_server.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("umeko/server/static", "umeko/server/static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan.on",
        "anyio._backends._asyncio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="umeko-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon=None,
)
