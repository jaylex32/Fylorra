"""
Fylorra - Tag Tools
Reliable metadata/cover-art transfer using mutagen (pure Python).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CoverArt:
    data: bytes
    mime: str = "image/jpeg"
    description: str = "Cover (front)"


def _guess_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"


def extract_cover_art(input_path: Path) -> Optional[CoverArt]:
    """
    Best-effort extraction from common containers:
    - MP3: ID3 APIC
    - FLAC: pictures
    - M4A/MP4: 'covr'
    """
    try:
        from mutagen import File  # type: ignore
    except Exception:
        return None

    input_path = Path(input_path)
    try:
        audio = File(str(input_path))
    except Exception:
        return None
    if not audio:
        return None

    ext = input_path.suffix.lower()

    # MP3 (ID3)
    if ext == ".mp3":
        try:
            tags = getattr(audio, "tags", None)
            if not tags:
                return None
            for key in tags.keys():
                if str(key).startswith("APIC"):
                    apic = tags.get(key)
                    if apic and getattr(apic, "data", None):
                        data = apic.data
                        mime = getattr(apic, "mime", None) or _guess_mime(data)
                        desc = getattr(apic, "desc", None) or "Cover (front)"
                        return CoverArt(data=data, mime=mime, description=desc)
        except Exception:
            return None

    # FLAC
    if ext == ".flac":
        try:
            pics = getattr(audio, "pictures", None) or []
            if pics:
                pic = pics[0]
                data = pic.data
                mime = getattr(pic, "mime", None) or _guess_mime(data)
                desc = getattr(pic, "desc", None) or "Cover (front)"
                return CoverArt(data=data, mime=mime, description=desc)
        except Exception:
            return None

    # MP4/M4A
    if ext in {".m4a", ".mp4", ".m4b"}:
        try:
            covr = audio.tags.get("covr") if getattr(audio, "tags", None) else None
            if covr:
                data = bytes(covr[0])
                return CoverArt(data=data, mime=_guess_mime(data), description="Cover (front)")
        except Exception:
            return None

    return None


def ensure_mp3_cover_art(output_mp3: Path, cover: CoverArt) -> bool:
    """
    Add cover art to an MP3 if it doesn't already have one.
    Returns True if cover is present/added successfully.
    """
    try:
        from mutagen.id3 import APIC, ID3, ID3NoHeaderError  # type: ignore
    except Exception:
        return False

    output_mp3 = Path(output_mp3)
    try:
        try:
            tags = ID3(str(output_mp3))
        except ID3NoHeaderError:
            tags = ID3()

        # If already has APIC, do nothing
        for k in tags.keys():
            if str(k).startswith("APIC"):
                return True

        tags.add(
            APIC(
                encoding=3,
                mime=cover.mime,
                type=3,  # front cover
                desc=cover.description,
                data=cover.data,
            )
        )
        tags.save(str(output_mp3))
        return True
    except Exception:
        return False

