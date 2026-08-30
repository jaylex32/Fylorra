# -*- mode: python ; coding: utf-8 -*-
#
# Fylorra (Qt) PyInstaller spec
# Bundles optional tools (ffmpeg/ffprobe/ffplay) so end users don't need installs.
# AI models are NOT bundled (downloaded to ~/.fylorra/ai_models).

import os
import sys
from pathlib import Path


_spec_file = globals().get("__file__")
root = Path(_spec_file).resolve().parent if _spec_file else Path.cwd()
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from build_tools.fetch_ffmpeg_tools import ensure_ffmpeg_tools
icon_path = root / "assets" / "fylorra.ico"
exe_icon = [str(icon_path)] if os.name == "nt" and icon_path.exists() else None

# Stage FFmpeg tools for bundling (Windows only).
ffmpeg_datas = []
try:
    bin_dir = ensure_ffmpeg_tools()
    ffmpeg_datas = [
        (str(bin_dir / "ffmpeg.exe"), "tools/ffmpeg/bin"),
        (str(bin_dir / "ffprobe.exe"), "tools/ffmpeg/bin"),
        (str(bin_dir / "ffplay.exe"), "tools/ffmpeg/bin"),
    ]
except Exception:
    ffmpeg_datas = []

# Bundle llama-cpp DLLs so AI model loading works in one-file builds.
llama_datas = []
try:
    import llama_cpp  # type: ignore

    llama_root = Path(llama_cpp.__file__).resolve().parent
    llama_lib = llama_root / "lib"
    if llama_lib.exists():
        llama_datas = [(str(llama_lib), "llama_cpp/lib")]
except Exception:
    llama_datas = []



a = Analysis(
    ["main_qt.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[("assets", "assets"), ("core/pipeline_templates", "core/pipeline_templates")] + ffmpeg_datas + llama_datas,
    hiddenimports=["llama_cpp", "llama_cpp.llama_chat_format"],
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
    name="Fylorra",
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
    icon=exe_icon,
)
