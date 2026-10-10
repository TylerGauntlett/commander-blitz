# -*- mode: python ; coding: utf-8 -*-
"""The frozen server, as one directory.

``onedir`` rather than ``onefile``: a onefile build unpacks itself to a temp
directory on every launch, which on a Steam Deck is a second or two of extra
splash for nothing. The directory ships inside the content package as
``server/``, beside ``client/`` and ``data/``.

No card data inside: the data ships beside the binary so a content update
that changes a card never has to rebuild Python. What is collected is the
package itself (every module -- the agents and strategies are looked up by
name, so an import scan would miss them), uvicorn's own lazily-imported
pieces, and certifi's certificate bundle.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

a = Analysis(
    ["entry.py"],
    pathex=["../../src"],
    binaries=[],
    datas=collect_data_files("certifi"),
    hiddenimports=[
        *collect_submodules("automtg"),
        *collect_submodules("uvicorn"),
        "certifi",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Training only; ~800MB and nothing serving a game imports it.
        "torch",
        "torchvision",
        # Not used, and each would drag a GUI toolkit or a plotting stack in.
        "tkinter",
        "matplotlib",
        "PIL",
        "IPython",
        "pytest",
        "numpy.testing",
    ],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="commanderblitz-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # A console program: stdout is the READY line, stderr is the log.
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="commanderblitz-server",
)
