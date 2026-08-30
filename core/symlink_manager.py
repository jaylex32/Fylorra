"""Symbolic link helpers for Fylorra."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from core.branding import APP_NAME


@dataclass
class LinkRecord:
    link_path: str
    target_path: str
    link_type: str = "auto"
    status: str = "unknown"
    note: str = ""


class SymlinkManager:
    """Create, remove, and persist user-created file system links."""

    def __init__(self, settings_manager):
        self.settings_manager = settings_manager

    def list_links(self) -> list[dict[str, Any]]:
        records = []
        for item in self._load():
            record = self._normalize_record(item)
            if not record.link_path or not record.target_path:
                continue
            records.append(asdict(self._with_status(record)))
        return records

    def create_link(self, target_path: str, link_path: str, link_type: str = "auto") -> LinkRecord:
        target = Path(str(target_path or "")).expanduser()
        link = Path(str(link_path or "")).expanduser()
        link_type = str(link_type or "auto").strip().lower()
        if link_type not in {"auto", "file", "directory", "junction"}:
            link_type = "auto"

        if not target.exists():
            raise ValueError("Target path does not exist.")
        if link.exists() or link.is_symlink():
            raise ValueError("Link path already exists.")
        if not link.name:
            raise ValueError("Link path must include a name.")

        is_dir = target.is_dir()
        if is_dir and self._same_or_inside(link, target):
            raise ValueError("Link path cannot be inside the target folder; that would create a recursive folder loop.")

        link.parent.mkdir(parents=True, exist_ok=True)

        if link_type == "file" and is_dir:
            raise ValueError("Target is a folder; choose directory or auto.")
        if link_type in {"directory", "junction"} and not is_dir:
            raise ValueError("Target is a file; choose file or auto.")

        created_type = "directory" if is_dir else "file"
        try:
            os.symlink(str(target), str(link), target_is_directory=is_dir)
        except OSError as exc:
            if os.name == "nt" and is_dir and link_type in {"auto", "junction"}:
                self._create_windows_junction(target, link)
                created_type = "junction"
            else:
                raise RuntimeError(
                    "Could not create symbolic link. On Windows, enable Developer Mode "
                    f"or run {APP_NAME} as administrator."
                ) from exc

        record = LinkRecord(str(link), str(target), created_type)
        self._upsert(record)
        return self._with_status(record)

    def remove_link(self, link_path: str, *, forget_only: bool = False) -> bool:
        link = Path(str(link_path or "")).expanduser()
        if not forget_only:
            if link.exists() or link.is_symlink():
                if self._is_link_path(link):
                    try:
                        if link.is_dir() and (os.name == "nt" or not link.is_symlink()):
                            link.rmdir()
                        else:
                            link.unlink()
                    except OSError:
                        if link.is_symlink():
                            link.unlink()
                        else:
                            raise
                else:
                    raise ValueError("Selected path is not a symbolic link or junction.")
        records = [r for r in self._load() if str(r.get("link_path") or "") != str(link)]
        self._save(records)
        return True

    def _create_windows_junction(self, target: Path, link: Path) -> None:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "mklink failed").strip()
            raise RuntimeError(msg)

    def _is_link_path(self, path: Path) -> bool:
        try:
            if path.is_symlink():
                return True
            is_junction = getattr(path, "is_junction", None)
            if callable(is_junction) and is_junction():
                return True
        except Exception:
            return False
        return False

    def _same_or_inside(self, child: Path, parent: Path) -> bool:
        try:
            c = child.resolve()
            p = parent.resolve()
            return c == p or p in c.parents
        except Exception:
            c = os.path.normcase(os.path.abspath(str(child)))
            p = os.path.normcase(os.path.abspath(str(parent)))
            return c == p or c.startswith(p.rstrip("\\/") + os.sep)

    def _with_status(self, record: LinkRecord) -> LinkRecord:
        link = Path(record.link_path)
        target = Path(record.target_path)
        if self._is_link_path(link):
            if target.exists():
                record.status = "ok"
                record.note = "Ready"
            else:
                record.status = "broken"
                record.note = "Target missing"
        elif link.exists():
            record.status = "not_link"
            record.note = "Path exists but is not a link"
        else:
            record.status = "missing"
            record.note = "Link missing"
        return record

    def _normalize_record(self, item: dict[str, Any]) -> LinkRecord:
        return LinkRecord(
            link_path=str(item.get("link_path") or ""),
            target_path=str(item.get("target_path") or ""),
            link_type=str(item.get("link_type") or "auto"),
            status=str(item.get("status") or "unknown"),
            note=str(item.get("note") or ""),
        )

    def _load(self) -> list[dict[str, Any]]:
        loader = getattr(self.settings_manager, "load_symlinks", None)
        if callable(loader):
            return list(loader() or [])
        return []

    def _save(self, records: list[dict[str, Any]]) -> None:
        saver = getattr(self.settings_manager, "save_symlinks", None)
        if callable(saver):
            saver(records)

    def _upsert(self, record: LinkRecord) -> None:
        records = self._load()
        link_key = str(record.link_path)
        out = [r for r in records if str(r.get("link_path") or "") != link_key]
        out.append(asdict(record))
        self._save(out)
