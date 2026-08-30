"""
Fylorra - File Operations (safe primitives)
Provides reusable, safe, target-folder-scoped file operations that the AI can compose.
"""

from __future__ import annotations

import shutil
import time
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class FileOpResult:
    ok: bool
    message: str
    affected: int = 0
    details: dict[str, Any] | None = None


def _is_under(root: Path, p: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _normalize_ext(ext: str) -> str:
    ext = (ext or "").strip().lower()
    if not ext:
        return ""
    return ext if ext.startswith(".") else "." + ext


def select_files(
    folder: Path,
    *,
    include_subfolders: bool = True,
    include_hidden: bool = False,
    selector: dict[str, Any] | None = None,
    max_files: int = 5000,
) -> list[Path]:
    """
    Select files within folder using simple, safe filters.

    selector keys (all optional):
    - extensions: [".mp3", ".flac"] or ["mp3","flac"]
    - glob: "*.mp3" or "**/*.mp3" (if include_subfolders)
    - name_contains: "invoice"
    """
    folder = Path(folder)
    selector = selector or {}

    extensions = selector.get("extensions") or []
    if isinstance(extensions, str):
        extensions = [extensions]
    extensions_set = {_normalize_ext(e) for e in extensions if _normalize_ext(e)}

    glob_pat = selector.get("glob")
    glob_pat = str(glob_pat).strip() if glob_pat else None
    name_contains = selector.get("name_contains")
    name_contains = str(name_contains).lower().strip() if name_contains else None

    out: list[Path] = []

    # If the caller provides a custom glob, use pathlib's globbing (features like **/*.ext).
    # Otherwise, use os.walk for better performance on Windows.
    if glob_pat:
        pattern = glob_pat if include_subfolders else glob_pat.replace("**/", "")
        for p in folder.glob(pattern):
            if len(out) >= int(max_files):
                break
            if not p.is_file():
                continue
            if not include_hidden and p.name.startswith("."):
                continue
            if extensions_set and p.suffix.lower() not in extensions_set:
                continue
            if name_contains and name_contains not in p.name.lower():
                continue
            out.append(p)
    else:
        exclude_dir_names = {"__pycache__", ".git", ".fylorra", ".fylorra_trash", "converted_media", "converted_images", "converted_office"}
        if include_subfolders:
            for root, dirs, files in os.walk(folder):
                if len(out) >= int(max_files):
                    break
                dirs[:] = [d for d in dirs if d.lower() not in exclude_dir_names]
                if not include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in files:
                    if len(out) >= int(max_files):
                        break
                    if not include_hidden and name.startswith("."):
                        continue
                    p = Path(root) / name
                    if extensions_set and p.suffix.lower() not in extensions_set:
                        continue
                    if name_contains and name_contains not in p.name.lower():
                        continue
                    out.append(p)
        else:
            try:
                for entry in os.scandir(folder):
                    if len(out) >= int(max_files):
                        break
                    if not entry.is_file():
                        continue
                    if not include_hidden and entry.name.startswith("."):
                        continue
                    p = Path(entry.path)
                    if extensions_set and p.suffix.lower() not in extensions_set:
                        continue
                    if name_contains and name_contains not in p.name.lower():
                        continue
                    out.append(p)
            except Exception:
                pass

    out.sort(key=lambda x: str(x).lower())
    return out


def make_subfolder(target_folder: Path, subfolder: str) -> Path:
    target_folder = Path(target_folder)
    sub = (subfolder or "").strip().strip("\"'")
    if not sub:
        raise ValueError("subfolder is empty")
    dest = (target_folder / sub).resolve()
    if not _is_under(target_folder, dest):
        raise ValueError("subfolder must be within target folder")
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _safe_overwrite(dest: Path, *, overwrite: bool) -> bool:
    if not dest.exists():
        return True
    return bool(overwrite)


def _is_inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except Exception:
        return False


def move_files(
    target_folder: Path,
    *,
    dest_subfolder: str,
    include_subfolders: bool = True,
    include_hidden: bool = False,
    selector: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> FileOpResult:
    target_folder = Path(target_folder)
    files = select_files(target_folder, include_subfolders=include_subfolders, include_hidden=include_hidden, selector=selector)
    if not files:
        return FileOpResult(ok=True, message="No files matched.", affected=0)

    dest_dir = make_subfolder(target_folder, dest_subfolder)
    files = [p for p in files if not _is_inside(p, dest_dir)]
    if not files:
        return FileOpResult(ok=True, message="No files matched outside the destination folder.", affected=0)

    moved = 0
    skipped = 0
    for src in files:
        rel = src.relative_to(target_folder)
        out = dest_dir / rel.name
        if not _safe_overwrite(out, overwrite=overwrite):
            skipped += 1
            continue
        try:
            if out.exists() and overwrite:
                out.unlink()
            shutil.move(str(src), str(out))
            moved += 1
        except Exception:
            skipped += 1

    return FileOpResult(ok=True, message=f"Moved {moved} files (skipped {skipped}).", affected=moved, details={"skipped": skipped, "dest": str(dest_dir)})


def copy_files(
    target_folder: Path,
    *,
    dest_subfolder: str,
    include_subfolders: bool = True,
    include_hidden: bool = False,
    selector: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> FileOpResult:
    target_folder = Path(target_folder)
    files = select_files(target_folder, include_subfolders=include_subfolders, include_hidden=include_hidden, selector=selector)
    if not files:
        return FileOpResult(ok=True, message="No files matched.", affected=0)

    dest_dir = make_subfolder(target_folder, dest_subfolder)
    files = [p for p in files if not _is_inside(p, dest_dir)]
    if not files:
        return FileOpResult(ok=True, message="No files matched outside the destination folder.", affected=0)

    copied = 0
    skipped = 0
    for src in files:
        rel = src.relative_to(target_folder)
        out = dest_dir / rel.name
        if not _safe_overwrite(out, overwrite=overwrite):
            skipped += 1
            continue
        try:
            if out.exists() and overwrite:
                out.unlink()
            shutil.copy2(str(src), str(out))
            copied += 1
        except Exception:
            skipped += 1

    return FileOpResult(ok=True, message=f"Copied {copied} files (skipped {skipped}).", affected=copied, details={"skipped": skipped, "dest": str(dest_dir)})


def delete_files(
    target_folder: Path,
    *,
    include_subfolders: bool = True,
    include_hidden: bool = False,
    selector: dict[str, Any] | None = None,
) -> FileOpResult:
    """
    Safe delete:
    - If Send2Trash is installed, send to OS recycle bin.
    - Else move into target_folder/.fylorra_trash/<timestamp>/ (no permanent deletion).
    """
    target_folder = Path(target_folder)
    files = select_files(target_folder, include_subfolders=include_subfolders, include_hidden=include_hidden, selector=selector)
    if not files:
        return FileOpResult(ok=True, message="No files matched.", affected=0)

    try:
        from send2trash import send2trash  # type: ignore

        deleted = 0
        skipped = 0
        for src in files:
            try:
                send2trash(str(src))
                deleted += 1
            except Exception:
                skipped += 1
        return FileOpResult(ok=True, message=f"Sent {deleted} files to Recycle Bin (skipped {skipped}).", affected=deleted, details={"skipped": skipped})
    except Exception:
        trash_dir = make_subfolder(target_folder, f".fylorra_trash/{time.strftime('%Y%m%d_%H%M%S')}")
        files = [p for p in files if not _is_inside(p, trash_dir)]
        if not files:
            return FileOpResult(ok=True, message="No files matched outside the trash folder.", affected=0)
        deleted = 0
        skipped = 0
        for src in files:
            try:
                out = trash_dir / src.name
                if out.exists():
                    out = trash_dir / f"{src.stem}_{int(time.time()*1000)}{src.suffix}"
                shutil.move(str(src), str(out))
                deleted += 1
            except Exception:
                skipped += 1
        return FileOpResult(ok=True, message=f"Moved {deleted} files to trash folder (skipped {skipped}).", affected=deleted, details={"skipped": skipped, "trash": str(trash_dir)})


def delete_specific_files(
    files: list[Path | str],
    *,
    use_recycle_bin: bool = True,
    trash_root: Path | None = None,
) -> FileOpResult:
    """
    Delete a specific list of files safely:
    - If Send2Trash is installed and use_recycle_bin=True, send to OS recycle bin.
    - Else move into trash_root (default: ~/.fylorra/trash/<timestamp>/).
    """
    paths: list[Path] = []
    for f in files or []:
        try:
            p = Path(f)
            if p.exists() and p.is_file():
                paths.append(p)
        except Exception:
            continue

    if not paths:
        return FileOpResult(ok=True, message="No files to delete.", affected=0)

    if use_recycle_bin:
        try:
            from send2trash import send2trash  # type: ignore

            deleted = 0
            skipped = 0
            for p in paths:
                try:
                    send2trash(str(p))
                    deleted += 1
                except Exception:
                    skipped += 1
            return FileOpResult(ok=True, message=f"Sent {deleted} files to Recycle Bin (skipped {skipped}).", affected=deleted, details={"skipped": skipped})
        except Exception:
            pass

    try:
        base = trash_root
        if base is None:
            base = Path.home() / ".fylorra" / "trash"
        base.mkdir(parents=True, exist_ok=True)
        dest = base / time.strftime("%Y%m%d_%H%M%S")
        dest.mkdir(parents=True, exist_ok=True)
        moved = 0
        skipped = 0
        for p in paths:
            try:
                out = dest / p.name
                if out.exists():
                    out = dest / f"{p.stem}_{int(time.time()*1000)}{p.suffix}"
                shutil.move(str(p), str(out))
                moved += 1
            except Exception:
                skipped += 1
        return FileOpResult(ok=True, message=f"Moved {moved} files to trash folder (skipped {skipped}).", affected=moved, details={"skipped": skipped, "trash": str(dest)})
    except Exception as e:
        return FileOpResult(ok=False, message=f"Delete failed: {e}", affected=0)
