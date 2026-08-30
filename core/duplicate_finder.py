"""
Fylorra - Duplicate Finder

Baseline duplicate detection:
- Finds exact duplicates by hashing file contents.
- Uses size grouping to avoid hashing everything.
- Safe defaults: returns groups (original + duplicates) without deleting.
"""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DuplicateGroup:
    """A group of identical files (by content hash)."""

    sha256: str
    original: str
    duplicates: list[str]
    size: int


def _iter_files_stream(folder: Path, *, include_subfolders: bool, exclude_dir_names: set[str] | None = None):
    """
    Stream file paths without building a massive in-memory list.
    This is critical for large folders (hundreds of thousands of files).
    """
    folder = Path(folder)
    if not include_subfolders:
        try:
            for entry in os.scandir(folder):
                if entry.is_file():
                    yield Path(entry.path)
        except Exception:
            return
        return

    for root, dirs, files in os.walk(folder):
        try:
            if exclude_dir_names:
                dirs[:] = [d for d in dirs if d not in exclude_dir_names]
        except Exception:
            pass
        for name in files:
            yield Path(root) / name


def _sha256(path: Path, *, cancel_event: threading.Event | None = None) -> str | None:
    h = hashlib.sha256()
    try:
        with Path(path).open("rb") as f:
            while True:
                if cancel_event and cancel_event.is_set():
                    return None
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def find_exact_duplicates(
    folder: Path,
    *,
    include_subfolders: bool = True,
    cancel_event: threading.Event | None = None,
    progress_cb=None,  # callable(cur:int,total:int,path:Path) -> None
    max_files: int | None = 500_000,
) -> list[DuplicateGroup]:
    """
    Returns groups of exact duplicate files under `folder`.
    """
    folder = Path(folder)
    exclude = {
        ".fylorra",
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "Converted_Media",
        "Converted_Images",
        "Converted_Office",
        "Converted_PDF",
        "Converted_Archives",
    }
    # 1) First pass: count sizes (streaming). This avoids storing hundreds of thousands of paths.
    size_counts: dict[int, int] = {}
    scanned = 0
    last_path = None
    for p in _iter_files_stream(folder, include_subfolders=include_subfolders, exclude_dir_names=exclude):
        if cancel_event and cancel_event.is_set():
            return []
        scanned += 1
        if max_files and scanned > int(max_files):
            raise RuntimeError(
                f"Too many files to scan ({scanned:,}+) for duplicates. "
                "Pick a narrower folder (recommended) or run duplicate detection per library/folder."
            )
        last_path = p
        try:
            size = int(p.stat().st_size)
        except Exception:
            continue
        if size <= 0:
            continue
        size_counts[size] = int(size_counts.get(size, 0)) + 1
        if progress_cb and (scanned % 2000 == 0):
            try:
                # total=0 means "unknown" (indeterminate stage).
                progress_cb(scanned, 0, p)
            except Exception:
                pass

    if scanned <= 0:
        return []

    candidate_sizes = {s for s, c in size_counts.items() if c >= 2 and s > 0}
    if not candidate_sizes:
        # Still emit one update at end.
        if progress_cb and last_path is not None:
            try:
                progress_cb(scanned, 0, last_path)
            except Exception:
                pass
        return []

    total_candidates = int(sum(size_counts.get(s, 0) for s in candidate_sizes))
    if total_candidates <= 0:
        return []

    # 2) Second pass: hash only candidate sizes.
    groups: dict[tuple[int, str], list[str]] = {}
    hashed = 0
    for p in _iter_files_stream(folder, include_subfolders=include_subfolders, exclude_dir_names=exclude):
        if cancel_event and cancel_event.is_set():
            return []
        try:
            size = int(p.stat().st_size)
        except Exception:
            continue
        if size not in candidate_sizes:
            continue

        digest = _sha256(p, cancel_event=cancel_event)
        if not digest:
            continue
        key = (size, digest)
        groups.setdefault(key, []).append(str(p))
        hashed += 1
        if progress_cb and (hashed % 50 == 0 or hashed == total_candidates):
            try:
                progress_cb(hashed, total_candidates, p)
            except Exception:
                pass

    out: list[DuplicateGroup] = []
    for (size, digest), paths in groups.items():
        if len(paths) < 2:
            continue
        # Deterministic "original": shortest path, then lexicographic.
        paths_sorted = sorted(paths, key=lambda s: (len(s), s.lower()))
        original = paths_sorted[0]
        dups = paths_sorted[1:]
        out.append(DuplicateGroup(sha256=digest, original=original, duplicates=dups, size=size))

    # Sort biggest impact first.
    out.sort(key=lambda g: (g.size * (len(g.duplicates))), reverse=True)
    return out
