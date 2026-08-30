"""
Fylorra - FFmpeg Manager
Prefer a Python-managed ffmpeg binary for "clean" installs.

Strategy:
1) If FYLORRA_FFMPEG is set and exists, use it.
2) If ffmpeg is on PATH, use it.
3) Use imageio-ffmpeg to provide a local ffmpeg binary.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def get_ffmpeg_exe() -> Optional[str]:
    # Prefer Fylorra tool config (tools.json) if present.
    try:
        from core.tool_manager import ToolManager

        p = ToolManager().ffmpeg_path()
        if p and Path(p).exists():
            return p
    except Exception:
        pass

    env = os.environ.get("FYLORRA_FFMPEG")
    if env and Path(env).exists():
        return env

    p = shutil.which("ffmpeg")
    if p:
        return p

    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if exe and Path(exe).exists() else None
    except Exception:
        return None


def get_ffprobe_exe() -> Optional[str]:
    """
    Best-effort lookup for ffprobe (used for duration/progress reporting).
    Tries:
    - FYLORRA_FFPROBE env var
    - ffprobe on PATH
    - sibling ffprobe next to resolved ffmpeg
    """
    # Prefer Fylorra tool config (tools.json) if present.
    try:
        from core.tool_manager import ToolManager

        p = ToolManager().ffprobe_path()
        if p and Path(p).exists():
            return p
    except Exception:
        pass

    env = os.environ.get("FYLORRA_FFPROBE")
    if env and Path(env).exists():
        return env

    p = shutil.which("ffprobe")
    if p:
        return p

    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return None
    try:
        ffmpeg_path = Path(ffmpeg)
        sib = ffmpeg_path.with_name("ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe")
        return str(sib) if sib.exists() else None
    except Exception:
        return None


def get_ffplay_exe() -> Optional[str]:
    """
    Best-effort lookup for ffplay (used for preview playback).
    Tries:
    - FYLORRA_FFPLAY env var
    - ffplay on PATH
    - sibling ffplay next to resolved ffmpeg
    """
    env = os.environ.get("FYLORRA_FFPLAY")
    if env and Path(env).exists():
        return env

    # Prefer Fylorra tool config (tools.json) if present.
    try:
        from core.tool_manager import ToolManager

        p = ToolManager().ffplay_path()
        if p and Path(p).exists():
            return p
    except Exception:
        pass

    p = shutil.which("ffplay")
    if p:
        return p

    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return None
    try:
        ffmpeg_path = Path(ffmpeg)
        sib = ffmpeg_path.with_name("ffplay.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffplay")
        return str(sib) if sib.exists() else None
    except Exception:
        return None


_ENCODER_CACHE: set[str] | None = None


def get_ffmpeg_encoders() -> set[str]:
    """
    Returns a set of encoder names supported by the ffmpeg binary (best-effort).
    Cached for the process lifetime.
    """
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return set(_ENCODER_CACHE)

    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        _ENCODER_CACHE = set()
        return set()

    try:
        proc = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-encoders"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        out = proc.stdout or ""
    except Exception:
        _ENCODER_CACHE = set()
        return set()

    enc: set[str] = set()
    for line in out.splitlines():
        # Typical: " V....D h264_nvenc           NVIDIA NVENC H.264 encoder"
        parts = line.strip().split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            name = parts[1].strip()
            if name:
                enc.add(name)
    _ENCODER_CACHE = enc
    return set(enc)


def ffmpeg_has_encoder(name: str) -> bool:
    return str(name).strip() in get_ffmpeg_encoders()
