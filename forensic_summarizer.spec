# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_dynamic_libs,
    collect_data_files,
    collect_submodules,
)

block_cipher = None

# Use current working directory as project root
project_root = Path(".").resolve()
backend_dir = project_root / "backend"
prompts_dir = backend_dir / "prompts"

# ---------- data files ----------
# Explicitly add each prompt file so they are definitely bundled
# They will end up inside the bundle under backend/prompts/
datas = [
    (str(prompts_dir / "pj.txt"), "backend/prompts"),
    (str(prompts_dir / "vc.txt"), "backend/prompts"),
    (str(prompts_dir / "pv.txt"), "backend/prompts"),
    (str(prompts_dir / "reclass.txt"), "backend/prompts"),
    (str(prompts_dir / "ujd.txt"), "backend/prompts"),
    (str(prompts_dir / "tll.txt"), "backend/prompts"),
    (str(prompts_dir / "unknown.txt"), "backend/prompts"),
    (str(prompts_dir / "final_report.txt"), "backend/prompts"),
]

# llama-cpp-python (module name: llama_cpp) data files (if any)
datas += collect_data_files("llama_cpp")

# ---------- native libs ----------
# This collects llama_cpp native libraries (.dylib/.so/.bundle)
binaries = collect_dynamic_libs("llama_cpp")

# ---------- hidden imports ----------
hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("llama_cpp")
)

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# UPX is not recommended for notarization on macOS; disable it there.
use_upx = False if sys.platform == "darwin" else True

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='forensic_summarizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=use_upx,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=use_upx,
    name='forensic_summarizer',
)

app = BUNDLE(
    coll,
    name='forensic_summarizer.app',
    icon=None,
    bundle_identifier='com.yourdomain.forensic_summarizer',
)
