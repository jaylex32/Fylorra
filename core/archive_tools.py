"""
Fylorra - Archive Tools
Supports multiple archive formats with pure-Python packages where possible.

Notes:
- ZIP: built-in zipfile
- TAR.*: built-in tarfile
- 7Z: optional py7zr package
- RAR: extraction may work with rarfile if an unrar backend is available; creation is not supported.

Also supports a generic "split into parts" feature (.001, .002, ...).
"""

from __future__ import annotations

import os
import shutil
import tarfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveOpResult:
    ok: bool
    message: str
    output_path: str | None = None
    parts_dir: str | None = None


def _iter_files(folder: Path, *, include_subfolders: bool) -> list[Path]:
    folder = Path(folder)
    pattern = "**/*" if include_subfolders else "*"
    return [p for p in folder.glob(pattern) if p.is_file()]


def split_into_parts(
    file_path: Path,
    *,
    part_size_bytes: int,
    cancel_event: threading.Event | None = None,
    progress_cb=None,  # callable(cur:int,total:int,path:Path) -> None (cur=bytes, total=bytes)
) -> list[Path]:
    file_path = Path(file_path)
    if part_size_bytes <= 0:
        raise ValueError("part_size_bytes must be > 0")
    total = file_path.stat().st_size
    out_dir = file_path.parent / f"{file_path.name}.parts"
    out_dir.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    cur = 0
    idx = 1
    with file_path.open("rb") as f:
        while True:
            if cancel_event and cancel_event.is_set():
                for p in parts:
                    try:
                        p.unlink(missing_ok=True)  # py3.12
                    except Exception:
                        pass
                raise RuntimeError("Cancelled.")
            chunk = f.read(part_size_bytes)
            if not chunk:
                break
            part = out_dir / f"{file_path.name}.{idx:03d}"
            part.write_bytes(chunk)
            parts.append(part)
            cur += len(chunk)
            idx += 1
            if progress_cb:
                try:
                    progress_cb(cur, total, file_path)
                except Exception:
                    pass

    return parts


def join_parts(
    first_part: Path,
    *,
    output_path: Path | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb=None,  # callable(cur:int,total:int,name:str) -> None
) -> Path:
    first_part = Path(first_part)
    if not first_part.exists():
        raise FileNotFoundError("First part not found.")

    # Expect ...<archive>.<NNN> inside <archive>.parts folder
    base_name = first_part.name.rsplit(".", 1)[0]
    parts_dir = first_part.parent
    candidates = sorted(parts_dir.glob(base_name + ".*"))
    parts = [p for p in candidates if p.suffix[1:].isdigit()]
    if not parts:
        raise RuntimeError("No parts found.")

    total = sum(p.stat().st_size for p in parts)
    if output_path is None:
        output_path = parts_dir.parent / base_name
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cur = 0
    with output_path.open("wb") as out:
        for p in parts:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Cancelled.")
            data = p.read_bytes()
            out.write(data)
            cur += len(data)
            if progress_cb:
                try:
                    progress_cb(cur, total, p.name)
                except Exception:
                    pass

    return output_path


def _is_safe_extract_path(base_dir: Path, target_path: Path) -> bool:
    try:
        base = base_dir.resolve()
        target = target_path.resolve()
        target.relative_to(base)
        return True
    except Exception:
        return False


def _safe_member_destination(output_dir: Path, member_name: str) -> Path | None:
    normalized = str(member_name or "").replace("\\", "/").strip()
    if not normalized:
        return None
    member_path = Path(normalized)
    if member_path.is_absolute():
        return None
    dest_path = output_dir / member_path
    return dest_path if _is_safe_extract_path(output_dir, dest_path) else None


def create_archive(
    source_folder: Path,
    *,
    archive_path: Path,
    fmt: str,
    include_subfolders: bool = True,
    overwrite: bool = False,
    progress_cb=None,  # callable(cur:int,total:int,path:Path) -> None
    cancel_event: threading.Event | None = None,
    part_size_bytes: int | None = None,
) -> ArchiveOpResult:
    source_folder = Path(source_folder)
    archive_path = Path(archive_path)
    fmt = (fmt or "zip").strip().lower()

    if archive_path.exists():
        if not overwrite:
            return ArchiveOpResult(ok=False, message=f"Archive already exists: {archive_path.name}")
        try:
            archive_path.unlink()
        except Exception:
            pass

    files = _iter_files(source_folder, include_subfolders=include_subfolders)
    total = len(files)

    def emit(i: int, p: Path):
        if progress_cb:
            try:
                progress_cb(i, total, p)
            except Exception:
                pass

    if fmt == "zip":
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i, p in enumerate(files, start=1):
                if cancel_event and cancel_event.is_set():
                    try:
                        zf.close()
                    except Exception:
                        pass
                    try:
                        archive_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return ArchiveOpResult(ok=False, message="Cancelled.")
                emit(i, p)
                arcname = p.relative_to(source_folder)
                zf.write(p, arcname=str(arcname))
    elif fmt.startswith("tar"):
        # tar, tar.gz, tar.xz, tar.bz2
        mode = "w"
        if fmt == "tar.gz":
            mode = "w:gz"
        elif fmt == "tar.xz":
            mode = "w:xz"
        elif fmt == "tar.bz2":
            mode = "w:bz2"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, mode) as tf:
            for i, p in enumerate(files, start=1):
                if cancel_event and cancel_event.is_set():
                    try:
                        tf.close()
                    except Exception:
                        pass
                    try:
                        archive_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return ArchiveOpResult(ok=False, message="Cancelled.")
                emit(i, p)
                arcname = p.relative_to(source_folder)
                tf.add(p, arcname=str(arcname), recursive=False)
    elif fmt == "7z":
        try:
            import py7zr  # type: ignore
        except Exception:
            return ArchiveOpResult(ok=False, message="7z requires the 'py7zr' package.")
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(archive_path, "w") as zf:
            for i, p in enumerate(files, start=1):
                if cancel_event and cancel_event.is_set():
                    try:
                        zf.close()
                    except Exception:
                        pass
                    try:
                        archive_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return ArchiveOpResult(ok=False, message="Cancelled.")
                emit(i, p)
                arcname = str(p.relative_to(source_folder)).replace(os.sep, "/")
                zf.write(p, arcname)
    elif fmt == "rar":
        return ArchiveOpResult(ok=False, message="RAR creation is not supported without external tools (WinRAR/rar.exe).")
    else:
        return ArchiveOpResult(ok=False, message=f"Unsupported archive format: {fmt}")

    parts_dir = None
    if part_size_bytes and part_size_bytes > 0:
        try:
            split_into_parts(archive_path, part_size_bytes=part_size_bytes, cancel_event=cancel_event)
            parts_dir = str(archive_path.parent / f"{archive_path.name}.parts")
            try:
                archive_path.unlink(missing_ok=True)
            except Exception:
                pass
            return ArchiveOpResult(ok=True, message="Archive created and split into parts.", output_path=str(archive_path), parts_dir=parts_dir)
        except Exception as e:
            return ArchiveOpResult(ok=False, message=str(e))

    return ArchiveOpResult(ok=True, message="Archive created.", output_path=str(archive_path))


def extract_archive(
    archive_path: Path,
    *,
    output_dir: Path,
    overwrite: bool = False,
    progress_cb=None,  # callable(cur:int,total:int,name:str) -> None
    cancel_event: threading.Event | None = None,
) -> ArchiveOpResult:
    archive_path = Path(archive_path)
    output_dir = Path(output_dir)
    if not archive_path.exists():
        return ArchiveOpResult(ok=False, message="Archive not found.")

    # Auto-join parts if user points to a .001 file in a ".parts" folder
    if archive_path.suffix[1:].isdigit() and archive_path.parent.name.endswith(".parts"):
        try:
            joined = join_parts(archive_path, cancel_event=cancel_event)
            archive_path = joined
        except Exception as e:
            return ArchiveOpResult(ok=False, message=str(e))

    output_dir.mkdir(parents=True, exist_ok=True)
    name = archive_path.name.lower()
    fmt = "zip"
    if name.endswith(".7z"):
        fmt = "7z"
    elif name.endswith(".tar.gz"):
        fmt = "tar.gz"
    elif name.endswith(".tar.xz"):
        fmt = "tar.xz"
    elif name.endswith(".tar.bz2"):
        fmt = "tar.bz2"
    elif name.endswith(".tar"):
        fmt = "tar"
    elif name.endswith(".rar"):
        fmt = "rar"

    if fmt == "zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for i, member in enumerate(members, start=1):
                if cancel_event and cancel_event.is_set():
                    return ArchiveOpResult(ok=False, message="Cancelled.")
                if progress_cb:
                    try:
                        progress_cb(i, total, member.filename)
                    except Exception:
                        pass
                dest_path = output_dir / member.filename
                if not _is_safe_extract_path(output_dir, dest_path):
                    return ArchiveOpResult(ok=False, message="Unsafe archive (path traversal detected).")
                if member.is_dir():
                    dest_path.mkdir(parents=True, exist_ok=True)
                    continue
                if dest_path.exists() and not overwrite:
                    continue
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, dest_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        return ArchiveOpResult(ok=True, message="Archive extracted.", output_path=str(output_dir))

    if fmt.startswith("tar"):
        mode = "r:*"
        with tarfile.open(archive_path, mode) as tf:
            members = tf.getmembers()
            total = len(members)
            for i, member in enumerate(members, start=1):
                if cancel_event and cancel_event.is_set():
                    return ArchiveOpResult(ok=False, message="Cancelled.")
                if progress_cb:
                    try:
                        progress_cb(i, total, member.name)
                    except Exception:
                        pass
                if member.issym() or member.islnk() or member.isdev():
                    return ArchiveOpResult(ok=False, message="Unsafe archive (links/devices are not extracted).")
                dest_path = _safe_member_destination(output_dir, member.name)
                if dest_path is None:
                    return ArchiveOpResult(ok=False, message="Unsafe archive (path traversal detected).")
                if member.isdir():
                    if not dest_path.exists():
                        dest_path.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                if dest_path.exists() and not overwrite:
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with src, dest_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        return ArchiveOpResult(ok=True, message="Archive extracted.", output_path=str(output_dir))

    if fmt == "7z":
        try:
            import py7zr  # type: ignore
        except Exception:
            return ArchiveOpResult(ok=False, message="7z requires the 'py7zr' package.")
        with py7zr.SevenZipFile(archive_path, "r") as zf:
            names = zf.getnames()
            total = len(names)
            for i, n in enumerate(names, start=1):
                if cancel_event and cancel_event.is_set():
                    return ArchiveOpResult(ok=False, message="Cancelled.")
                dest_path = _safe_member_destination(output_dir, n)
                if dest_path is None:
                    return ArchiveOpResult(ok=False, message="Unsafe archive (path traversal detected).")
                if dest_path.exists() and not overwrite:
                    return ArchiveOpResult(ok=False, message=f"Destination exists: {dest_path.name}")
                if progress_cb:
                    try:
                        progress_cb(i, total, n)
                    except Exception:
                        pass
            zf.extractall(path=output_dir)
        return ArchiveOpResult(ok=True, message="Archive extracted.", output_path=str(output_dir))

    if fmt == "rar":
        # rarfile is optional and may require unrar backend.
        try:
            import rarfile  # type: ignore
        except Exception:
            return ArchiveOpResult(ok=False, message="RAR extraction requires the 'rarfile' package (and an unrar backend).")
        try:
            with rarfile.RarFile(archive_path) as rf:
                names = rf.namelist()
                total = len(names)
                for i, n in enumerate(names, start=1):
                    if cancel_event and cancel_event.is_set():
                        return ArchiveOpResult(ok=False, message="Cancelled.")
                    dest_path = _safe_member_destination(output_dir, n)
                    if dest_path is None:
                        return ArchiveOpResult(ok=False, message="Unsafe archive (path traversal detected).")
                    if dest_path.exists() and not overwrite:
                        continue
                    if progress_cb:
                        try:
                            progress_cb(i, total, n)
                        except Exception:
                            pass
                    info = rf.getinfo(n)
                    if getattr(info, "isdir", lambda: False)():
                        dest_path.mkdir(parents=True, exist_ok=True)
                        continue
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with rf.open(info) as src, dest_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            return ArchiveOpResult(ok=True, message="Archive extracted.", output_path=str(output_dir))
        except Exception as e:
            return ArchiveOpResult(ok=False, message=str(e))

    return ArchiveOpResult(ok=False, message="Unsupported archive type.")
