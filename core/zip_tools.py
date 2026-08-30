"""
Fylorra - ZIP Tools (built-in)
Safe zip/unzip helpers (no external apps required).
"""

from __future__ import annotations

import zipfile
import shutil
from dataclasses import dataclass
from pathlib import Path
import threading


@dataclass(frozen=True)
class ZipOpResult:
    ok: bool
    message: str
    output_path: str | None = None


def zip_folder(folder: Path, *, zip_path: Path, include_subfolders: bool = True, overwrite: bool = False) -> ZipOpResult:
    folder = Path(folder)
    zip_path = Path(zip_path)

    if zip_path.exists():
        if not overwrite:
            return ZipOpResult(ok=False, message=f"ZIP already exists: {zip_path.name}")
        zip_path.unlink()

    pattern = "**/*" if include_subfolders else "*"
    files = [p for p in folder.glob(pattern) if p.is_file()]
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            if p.resolve() == zip_path.resolve():
                continue
            arcname = p.relative_to(folder)
            zf.write(p, arcname=str(arcname))

    return ZipOpResult(ok=True, message="ZIP created.", output_path=str(zip_path))


def _is_safe_extract_path(base_dir: Path, target_path: Path) -> bool:
    try:
        base = base_dir.resolve()
        target = target_path.resolve()
        target.relative_to(base)
        return True
    except Exception:
        return False


def unzip_archive(archive_path: Path, *, output_dir: Path, overwrite: bool = False) -> ZipOpResult:
    archive_path = Path(archive_path)
    output_dir = Path(output_dir)
    if not archive_path.exists():
        return ZipOpResult(ok=False, message="Archive not found.")

    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            dest_path = output_dir / member.filename
            if not _is_safe_extract_path(output_dir, dest_path):
                return ZipOpResult(ok=False, message="Unsafe archive (path traversal detected).")
            if member.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
                continue
            if dest_path.exists() and not overwrite:
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, dest_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    return ZipOpResult(ok=True, message="Archive extracted.", output_path=str(output_dir))


def zip_folder_with_progress(
    folder: Path,
    *,
    zip_path: Path,
    include_subfolders: bool = True,
    overwrite: bool = False,
    progress_cb=None,  # callable(cur:int,total:int,path:Path) -> None
    cancel_event: threading.Event | None = None,
) -> ZipOpResult:
    """
    Same as zip_folder, but supports progress + cancel.
    """
    folder = Path(folder)
    zip_path = Path(zip_path)
    if zip_path.exists():
        if not overwrite:
            return ZipOpResult(ok=False, message=f"ZIP already exists: {zip_path.name}")
        zip_path.unlink()

    pattern = "**/*" if include_subfolders else "*"
    files = [p for p in folder.glob(pattern) if p.is_file()]
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(files)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, p in enumerate(files, start=1):
            if cancel_event and cancel_event.is_set():
                try:
                    zf.close()
                except Exception:
                    pass
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                except Exception:
                    pass
                return ZipOpResult(ok=False, message="Cancelled.")

            if progress_cb:
                try:
                    progress_cb(i, total, p)
                except Exception:
                    pass

            try:
                if p.resolve() == zip_path.resolve():
                    continue
            except Exception:
                pass
            arcname = p.relative_to(folder)
            zf.write(p, arcname=str(arcname))

    return ZipOpResult(ok=True, message="ZIP created.", output_path=str(zip_path))


def unzip_archive_with_progress(
    archive_path: Path,
    *,
    output_dir: Path,
    overwrite: bool = False,
    progress_cb=None,  # callable(cur:int,total:int,name:str) -> None
    cancel_event: threading.Event | None = None,
) -> ZipOpResult:
    """
    Same as unzip_archive, but supports progress + cancel.
    """
    archive_path = Path(archive_path)
    output_dir = Path(output_dir)
    if not archive_path.exists():
        return ZipOpResult(ok=False, message="Archive not found.")

    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        total = len(members)
        for i, member in enumerate(members, start=1):
            if cancel_event and cancel_event.is_set():
                return ZipOpResult(ok=False, message="Cancelled.")
            if progress_cb:
                try:
                    progress_cb(i, total, member.filename)
                except Exception:
                    pass

            dest_path = output_dir / member.filename
            if not _is_safe_extract_path(output_dir, dest_path):
                return ZipOpResult(ok=False, message="Unsafe archive (path traversal detected).")
            if dest_path.exists() and not overwrite:
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, dest_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    return ZipOpResult(ok=True, message="Archive extracted.", output_path=str(output_dir))
