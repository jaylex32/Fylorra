"""
Build helper: download and stage FFmpeg tools for bundling.

We bundle ffmpeg + ffprobe + ffplay into the PyInstaller app so end users
don't need to install anything.

Source (Windows): gyan.dev "release essentials" zip.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def ensure_ffmpeg_tools(*, cache_dir: Path | None = None) -> Path:
    """
    Returns the staged bin directory containing:
      - ffmpeg.exe
      - ffprobe.exe
      - ffplay.exe

    For Windows only. Uses a small cache under build/ by default.
    """
    if os.name != "nt":
        raise RuntimeError("FFmpeg bundling helper is implemented for Windows only.")

    root = Path(__file__).resolve().parents[1]
    cache_dir = cache_dir or (root / "build" / "ffmpeg_tools_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = cache_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    want = {
        "ffmpeg.exe": bin_dir / "ffmpeg.exe",
        "ffprobe.exe": bin_dir / "ffprobe.exe",
        "ffplay.exe": bin_dir / "ffplay.exe",
    }
    if all(p.exists() for p in want.values()):
        return bin_dir

    import requests

    zip_path = cache_dir / "ffmpeg-release-essentials.zip"
    with requests.get(FFMPEG_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)

    # Extract only the required executables.
    extracted: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        for name in names:
            low = name.lower().replace("\\", "/")
            if low.endswith("/bin/ffmpeg.exe") or low.endswith("/bin/ffprobe.exe") or low.endswith("/bin/ffplay.exe"):
                out = z.extract(name, cache_dir)
                out_path = Path(out)
                extracted[out_path.name.lower()] = out_path

    for exe in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
        src = extracted.get(exe.lower())
        if not src or not src.exists():
            raise RuntimeError(f"Failed to extract {exe} from FFmpeg bundle.")
        dst = want[exe]
        dst.write_bytes(src.read_bytes())

    return bin_dir

