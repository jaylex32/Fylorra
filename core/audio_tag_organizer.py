"""
Fylorra - Audio Tag Organizer
Moves audio files into a folder structure based on tags (Artist/Album).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class TagOrganizeResult:
    ok: bool
    message: str
    moved: int = 0
    skipped: int = 0
    dest_root: Optional[str] = None


def _safe_name(s: str, *, max_len: int = 80) -> str:
    s = (s or "").strip()
    if not s:
        return "Unknown"
    bad = '<>:"/\\|?*'
    for ch in bad:
        s = s.replace(ch, "_")
    s = " ".join(s.split())
    return s[:max_len].rstrip(" ._")


def _read_tags(path: Path) -> tuple[str, str]:
    """
    Returns (artist, album) with fallbacks.
    """
    try:
        from mutagen import File  # type: ignore
    except Exception:
        return "Unknown Artist", "Unknown Album"

    try:
        audio = File(str(path))
    except Exception:
        audio = None

    artist = None
    album = None

    try:
        tags = getattr(audio, "tags", None) if audio else None
        if tags:
            # MP3 ID3
            if "TPE1" in tags:
                artist = str(tags["TPE1"])
            if "TALB" in tags:
                album = str(tags["TALB"])
            # FLAC/Vorbis/MP4 keys
            if not artist:
                v = tags.get("artist") or tags.get("ARTIST")
                if v:
                    artist = str(v[0] if isinstance(v, list) else v)
            if not album:
                v = tags.get("album") or tags.get("ALBUM")
                if v:
                    album = str(v[0] if isinstance(v, list) else v)
            if not artist and "©ART" in tags:
                artist = str(tags["©ART"][0])
            if not album and "©alb" in tags:
                album = str(tags["©alb"][0])
    except Exception:
        pass

    return _safe_name(artist or "Unknown Artist"), _safe_name(album or "Unknown Album")


def organize_audio_by_tags(
    target_folder: Path,
    *,
    source_subfolder: str | None = None,
    dest_subfolder: str = "Organized_Music",
    include_subfolders: bool = True,
    overwrite: bool = False,
    progress_cb=None,  # callable(current,total, path, dest) -> None
) -> TagOrganizeResult:
    """
    Moves audio files into dest_subfolder/Artist/Album/filename.
    """
    target_folder = Path(target_folder)
    base = target_folder
    if source_subfolder:
        sub = str(source_subfolder).strip().strip("\"'")
        if sub.startswith(("/", "\\")) or ":" in sub or ".." in Path(sub).parts:
            return TagOrganizeResult(ok=False, message="source_subfolder must be relative under target folder.")
        base = target_folder / sub
    if not base.exists() or not base.is_dir():
        return TagOrganizeResult(ok=False, message="Source folder not found.")

    dest_root = target_folder / dest_subfolder
    dest_root.mkdir(parents=True, exist_ok=True)

    exts = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav"}
    pattern = "**/*" if include_subfolders else "*"
    files = [p for p in base.glob(pattern) if p.is_file() and p.suffix.lower() in exts]
    files.sort(key=lambda p: str(p).lower())

    moved = 0
    skipped = 0
    total = len(files)
    for i, p in enumerate(files, start=1):
        artist, album = _read_tags(p)
        dest_dir = dest_root / artist / album
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / p.name
        if progress_cb:
            try:
                progress_cb(i, total, p, dest_path)
            except Exception:
                pass
        if dest_path.exists() and not overwrite:
            skipped += 1
            continue
        try:
            if dest_path.exists() and overwrite:
                dest_path.unlink()
            shutil.move(str(p), str(dest_path))
            moved += 1
        except Exception:
            skipped += 1

    return TagOrganizeResult(ok=True, message=f"Moved {moved} files (skipped {skipped}).", moved=moved, skipped=skipped, dest_root=str(dest_root))

