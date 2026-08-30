"""
Fylorra - Tool Manager
Central place to locate optional external binaries (e.g. LibreOffice, ffmpeg).

Goal: make integrations "seamless" for end users by supporting:
- bundled binaries shipped with the app installer
- user-configured paths
- system PATH / common install locations
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ToolPaths:
    soffice: Optional[str] = None
    ffmpeg: Optional[str] = None
    ffprobe: Optional[str] = None
    ffplay: Optional[str] = None


def _app_root() -> Path:
    # PyInstaller: sys._MEIPASS points to extracted bundle dir.
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS).resolve()
    # Source/dev: repo root is parent of 'core'.
    return Path(__file__).resolve().parents[1]


class ToolManager:
    def __init__(self):
        self._cfg_path = Path.home() / ".fylorra" / "tools.json"
        self._cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self._paths = self._load()

    def _load(self) -> ToolPaths:
        try:
            data = json.loads(self._cfg_path.read_text(encoding="utf-8"))
            return ToolPaths(
                soffice=str(data.get("soffice")) if data.get("soffice") else None,
                ffmpeg=str(data.get("ffmpeg")) if data.get("ffmpeg") else None,
                ffprobe=str(data.get("ffprobe")) if data.get("ffprobe") else None,
                ffplay=str(data.get("ffplay")) if data.get("ffplay") else None,
            )
        except Exception:
            return ToolPaths()

    def save(
        self,
        *,
        soffice: Optional[str] = None,
        ffmpeg: Optional[str] = None,
        ffprobe: Optional[str] = None,
        ffplay: Optional[str] = None,
    ) -> None:
        self._paths = ToolPaths(
            soffice=soffice or None,
            ffmpeg=ffmpeg or None,
            ffprobe=ffprobe or None,
            ffplay=ffplay or None,
        )
        self._cfg_path.write_text(json.dumps(self._paths.__dict__, indent=2), encoding="utf-8")

    def set_soffice(self, path: Optional[str]) -> None:
        """Update only the LibreOffice soffice path, keeping other tool paths intact."""
        self.save(soffice=path, ffmpeg=self._paths.ffmpeg, ffprobe=self._paths.ffprobe, ffplay=self._paths.ffplay)

    def clear_soffice(self) -> None:
        self.set_soffice(None)

    def set_ffmpeg(self, path: Optional[str]) -> None:
        """Update only the ffmpeg path, keeping other tool paths intact."""
        self.save(soffice=self._paths.soffice, ffmpeg=path, ffprobe=self._paths.ffprobe, ffplay=self._paths.ffplay)

    def set_ffprobe(self, path: Optional[str]) -> None:
        """Update only the ffprobe path, keeping other tool paths intact."""
        self.save(soffice=self._paths.soffice, ffmpeg=self._paths.ffmpeg, ffprobe=path, ffplay=self._paths.ffplay)

    def set_ffplay(self, path: Optional[str]) -> None:
        """Update only the ffplay path, keeping other tool paths intact."""
        self.save(soffice=self._paths.soffice, ffmpeg=self._paths.ffmpeg, ffprobe=self._paths.ffprobe, ffplay=path)

    def soffice_path(self) -> Optional[str]:
        # 0) Environment override
        env = os.environ.get("FYLORRA_SOFFICE")
        if env and Path(env).exists():
            return env

        # 1) User-configured path
        if self._paths.soffice and Path(self._paths.soffice).exists():
            return self._paths.soffice

        # 2) Bundled inside app
        root = _app_root()
        bundled_candidates = [
            root / "tools" / "libreoffice" / "program" / "soffice.exe",
            root / "tools" / "LibreOffice" / "program" / "soffice.exe",
            root / "libreoffice" / "program" / "soffice.exe",
        ]
        for c in bundled_candidates:
            if c.exists():
                return str(c)

        # 3) PATH
        p = shutil.which("soffice")
        if p:
            return p

        # 4) Common Windows install paths
        candidates = [
            os.environ.get("ProgramFiles", "") + r"\LibreOffice\program\soffice.exe",
            os.environ.get("ProgramFiles(x86)", "") + r"\LibreOffice\program\soffice.exe",
        ]
        for c in candidates:
            if c and Path(c).exists():
                return c

        return None

    def ffmpeg_path(self) -> Optional[str]:
        env = os.environ.get("FYLORRA_FFMPEG")
        if env and Path(env).exists():
            return env

        if self._paths.ffmpeg and Path(self._paths.ffmpeg).exists():
            return self._paths.ffmpeg

        root = _app_root()
        bundled_candidates = [
            root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
            root / "tools" / "ffmpeg.exe",
        ]
        for c in bundled_candidates:
            if c.exists():
                return str(c)

        p = shutil.which("ffmpeg")
        if p:
            return p

        return None

    def ffprobe_path(self) -> Optional[str]:
        env = os.environ.get("FYLORRA_FFPROBE")
        if env and Path(env).exists():
            return env
        if self._paths.ffprobe and Path(self._paths.ffprobe).exists():
            return self._paths.ffprobe
        p = shutil.which("ffprobe")
        if p:
            return p
        return None

    def ffplay_path(self) -> Optional[str]:
        env = os.environ.get("FYLORRA_FFPLAY")
        if env and Path(env).exists():
            return env
        if self._paths.ffplay and Path(self._paths.ffplay).exists():
            return self._paths.ffplay
        p = shutil.which("ffplay")
        if p:
            return p
        return None



def libreoffice_download_url() -> str:
    # Official page that routes to the right platform download.
    return "https://www.libreoffice.org/download/download-libreoffice/"
