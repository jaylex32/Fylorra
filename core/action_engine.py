"""Action Engine - Executes automated actions on files"""

import shutil
import os
import time
import subprocess
import shlex
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import zipfile

from core.branding import APP_DATA_DIR_NAME


ACTIVE_DOWNLOAD_SUFFIXES = {
    ".crdownload",
    ".part",
    ".partial",
    ".download",
    ".opdownload",
    ".!qb",
    ".bc!",
}


def _is_active_download_artifact(path: Path) -> bool:
    """Detect common browser/download-manager temporary files and folders."""
    try:
        parts = [str(part).lower() for part in path.parts]
        if any(part.endswith(".download") for part in parts):
            return True
        name = path.name.lower()
        if name.endswith(tuple(ACTIVE_DOWNLOAD_SUFFIXES)):
            return True
        if path.suffix.lower() in ACTIVE_DOWNLOAD_SUFFIXES:
            return True
        if name.endswith(".tmp") or path.suffix.lower() == ".tmp":
            return _is_younger_than(path, 3600) if path.exists() else True
    except Exception:
        pass
    return False


def _is_younger_than(path: Path, seconds: float) -> bool:
    try:
        if seconds <= 0:
            return False
        age = time.time() - path.stat().st_mtime
        return age < seconds
    except Exception:
        return False


class ActionEngine:
    """Executes various file automation actions"""

    def __init__(self):
        self.action_handlers = {
            "copy": self._action_copy,
            "move": self._action_move,
            "rename": self._action_rename,
            "delete": self._action_delete,
            "clean_folder": self._action_clean_folder,
            "archive": self._action_archive,
            "execute": self._action_execute,
            "organize": self._action_organize
        }
        # Optional informational message from the last executed action (used by UI).
        self.last_action_info: str = ""

    def execute_action(self, action_type: str, file_path: str,
                       params: Dict[str, Any]) -> bool:
        """
        Execute an action on a file

        Args:
            action_type: Type of action to execute
            file_path: Path to the file
            params: Action parameters

        Returns:
            True if action succeeded, False otherwise
        """
        try:
            self.last_action_info = ""
            handler = self.action_handlers.get(action_type)
            if not handler:
                self.last_action_info = f"Unknown action type: {action_type}"
                print(self.last_action_info)
                return False

            return bool(handler(file_path, params))

        except Exception as e:
            self.last_action_info = f"Error executing {action_type}: {e}"
            print(f"Error executing action {action_type}: {e}")
            return False

    def preview_action(self, action_type: str, file_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a side-effect-free explanation of what an action would do."""
        action_type = str(action_type or "").strip().lower()
        params = dict(params or {})
        source = Path(file_path)
        preview: Dict[str, Any] = {
            "ok": False,
            "action": action_type or "unknown",
            "source": str(source),
            "target": "",
            "summary": "",
            "warning": "",
        }

        if action_type not in self.action_handlers:
            preview["summary"] = f"Unknown action: {action_type}"
            return preview

        if action_type == "delete":
            mode = "Recycle Bin/app trash" if bool(params.get("use_recycle_bin", True)) else "permanent delete"
            preview.update(ok=True, summary=f"Delete {source.name} using {mode}.")
            return preview

        if action_type == "execute":
            command = str(params.get("command") or "").strip()
            command_list = params.get("command_list")
            if not command and not (isinstance(command_list, list) and command_list):
                preview["summary"] = "No command is configured."
                return preview
            if bool(params.get("use_shell", False)) and not bool(params.get("allow_shell_execution", False)):
                preview["summary"] = "Shell command is blocked until allow_shell_execution=True is set."
                preview["warning"] = "Shell commands are high risk."
                return preview
            display = command or " ".join(str(x) for x in command_list)
            preview.update(ok=True, summary=f"Run command for {source.name}: {display}")
            return preview

        if action_type == "clean_folder":
            include = "including subfolders" if bool(params.get("include_subfolders", True)) else "top-level files only"
            mode = "Recycle Bin/app trash" if bool(params.get("use_recycle_bin", True)) else "permanent delete"
            min_age = float(params.get("min_age_seconds", 86400) or 0)
            age_text = f" files older than {int(round(min_age / 3600))} hour(s)" if min_age > 0 else " files regardless of age"
            dl_text = " Active download/temp files will be skipped." if bool(params.get("skip_active_downloads", True)) else ""
            preview.update(ok=True, target=str(source), summary=f"Clean{age_text} in {source} ({include}) using {mode}.{dl_text}")
            if self._is_dangerous_cleanup_root(source):
                preview["ok"] = False
                preview["warning"] = "Protected folder cleanup will be refused."
            return preview

        if not source.exists() or not source.is_file():
            preview["summary"] = f"Source file does not exist: {source}"
            return preview

        try:
            if action_type in {"copy", "move"}:
                dest_folder = str(params.get("destination") or "").strip()
                if not dest_folder:
                    preview["summary"] = f"{action_type.title()} needs a destination folder."
                    return preview
                target = self._planned_copy_move_destination(source, Path(dest_folder), params)
                verb = "Copy" if action_type == "copy" else "Move"
                preview.update(
                    ok=True,
                    target=str(target) if target else "",
                    summary=f"{verb} {source.name} to {target}" if target else f"Skip {source.name}; destination already exists.",
                )
                return preview

            if action_type == "rename":
                target = self._planned_rename_destination(source, params)
                if target is None:
                    preview["summary"] = "Rename would be skipped because the generated name is invalid or unchanged."
                    return preview
                preview.update(ok=True, target=str(target), summary=f"Rename {source.name} to {target.name}.")
                return preview

            if action_type == "archive":
                target = self._planned_archive_destination(source, params)
                if target is None:
                    preview["summary"] = "Archive name is invalid."
                    return preview
                preview.update(ok=True, target=str(target), summary=f"Add {source.name} to archive {target}.")
                return preview

            if action_type == "organize":
                target = self._planned_organize_destination(source, params)
                if target is None:
                    preview["summary"] = f"Unknown organize mode: {params.get('organize_by')}"
                    return preview
                preview.update(ok=True, target=str(target), summary=f"Move {source.name} into {target.parent}.")
                return preview
        except Exception as e:
            preview["summary"] = f"Preview failed: {e}"
            return preview

        preview["summary"] = f"No preview available for {action_type}."
        return preview

    def _action_copy(self, file_path: str, params: Dict) -> bool:
        """Copy file to destination"""
        dest_folder = params.get("destination")
        if not dest_folder:
            self.last_action_info = "Copy failed: destination folder is missing."
            return False

        source = Path(file_path)
        if not source.exists() or not source.is_file():
            self.last_action_info = f"Copy failed: source file does not exist: {source}"
            return False

        dest_path = Path(dest_folder)
        dest_path.mkdir(parents=True, exist_ok=True)

        dest_file = self._planned_copy_move_destination(source, dest_path, params)
        if dest_file is None:
            return True

        shutil.copy2(source, dest_file)
        return True

    def _action_move(self, file_path: str, params: Dict) -> bool:
        """Move file to destination"""
        dest_folder = params.get("destination")
        if not dest_folder:
            self.last_action_info = "Move failed: destination folder is missing."
            return False

        source = Path(file_path)
        if not source.exists() or not source.is_file():
            self.last_action_info = f"Move failed: source file does not exist: {source}"
            return False

        dest_path = Path(dest_folder)
        dest_path.mkdir(parents=True, exist_ok=True)

        dest_file = self._planned_copy_move_destination(source, dest_path, params)
        if dest_file is None:
            return True

        shutil.move(str(source), str(dest_file))
        return True

    def _action_rename(self, file_path: str, params: Dict) -> bool:
        """Rename file"""
        pattern = params.get("pattern", "{name}")

        file_obj = Path(file_path)
        if not file_obj.exists() or not file_obj.is_file():
            self.last_action_info = f"Rename failed: source file does not exist: {file_obj}"
            return False
        new_path = self._planned_rename_destination(file_obj, params)
        if new_path is None:
            self.last_action_info = "Rename failed: generated filename is empty or invalid."
            return False

        file_obj.rename(new_path)
        return True

    def _action_delete(self, file_path: str, params: Dict) -> bool:
        """Delete file (with optional recycle bin support)"""
        use_recycle_bin = params.get("use_recycle_bin", True)
        silent = bool(params.get("silent", False))
        skip_active_downloads = bool(params.get("skip_active_downloads", True))
        min_age_seconds = float(params.get("min_age_seconds", 0) or 0)

        p = Path(file_path)
        if not p.exists():
            return True
        if skip_active_downloads and _is_active_download_artifact(p):
            self.last_action_info = f"Skipped active download/temp artifact: {p.name}"
            return True
        if min_age_seconds > 0 and _is_younger_than(p, min_age_seconds):
            self.last_action_info = f"Skipped recent file: {p.name}"
            return True

        # In silent mode, avoid platform operations that can show OS UI.
        if use_recycle_bin and not silent:
            # Prefer send2trash (cross-platform) if available.
            try:
                from send2trash import send2trash  # type: ignore
                send2trash(str(p))
                return True
            except Exception:
                pass
            # Windows fallback (pywin32).
            try:
                from win32com.shell import shell, shellcon  # type: ignore

                shell.SHFileOperation(
                    (0, shellcon.FO_DELETE, str(p), None, shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION)
                )
                return True
            except Exception:
                pass

        if use_recycle_bin:
            # Portable trash fallback: move to an app-level trash folder OUTSIDE the monitored tree.
            # This prevents infinite monitor loops when monitoring recursive deletes.
            try:
                trash_root = Path.home() / APP_DATA_DIR_NAME / "trash" / time.strftime("%Y%m%d_%H%M%S")
                trash_root.mkdir(parents=True, exist_ok=True)
                dest = self._get_unique_path(trash_root / p.name)
                shutil.move(str(p), str(dest))
                return True
            except Exception:
                pass

        # Permanent delete
        try:
            os.remove(str(p))
        except Exception:
            return False

        return True

    def _action_clean_folder(self, file_path: str, params: Dict) -> bool:
        """
        Delete all contents from a folder (files + optional subfolders).
        Parameters:
        - include_subfolders: bool (default True)
        - use_recycle_bin: bool (default True)
        - silent: bool (default True) - avoid OS UI prompts (recommended)
        - ignore_locked: bool (default True) - skip locked/in-use files
        - min_age_seconds: default 86400; recent files are skipped
        - skip_active_downloads: default True; browser/downloader temp files are skipped
        """
        folder = Path(file_path)
        if not folder.exists() or not folder.is_dir():
            self.last_action_info = f"Clean failed: folder does not exist: {folder}"
            return False
        if self._is_dangerous_cleanup_root(folder):
            self.last_action_info = f"Refused to clean protected folder: {folder}"
            return False
        include_sub = bool(params.get("include_subfolders", True))
        use_recycle_bin = bool(params.get("use_recycle_bin", True))
        silent = bool(params.get("silent", True))
        ignore_locked = bool(params.get("ignore_locked", True))
        skip_active_downloads = bool(params.get("skip_active_downloads", True))
        min_age_seconds = float(params.get("min_age_seconds", 86400) or 0)

        # Collect targets first to avoid iterator invalidation while deleting.
        targets: List[Path] = []
        try:
            if include_sub:
                for item in folder.rglob("*"):
                    if item.is_file():
                        targets.append(item)
                # Delete empty dirs after files.
                dirs = sorted([p for p in folder.rglob("*") if p.is_dir()], key=lambda x: len(str(x)), reverse=True)
            else:
                for item in folder.iterdir():
                    if item.is_file():
                        targets.append(item)
                dirs = [p for p in folder.iterdir() if p.is_dir()]
        except Exception:
            return False

        ok = True
        deleted = 0
        skipped = 0
        skipped_recent = 0
        skipped_active = 0
        failed = 0
        for f in targets:
            try:
                if skip_active_downloads and _is_active_download_artifact(f):
                    skipped_active += 1
                    continue
                if min_age_seconds > 0 and _is_younger_than(f, min_age_seconds):
                    skipped_recent += 1
                    continue
                did = self._action_delete(
                    str(f),
                    {
                        "use_recycle_bin": use_recycle_bin,
                        "silent": silent,
                        "skip_active_downloads": skip_active_downloads,
                        "min_age_seconds": 0,
                    },
                )
                if did:
                    deleted += 1
                else:
                    failed += 1
                    ok = False
            except PermissionError:
                skipped += 1
                if not ignore_locked:
                    ok = False
            except OSError:
                skipped += 1
                if not ignore_locked:
                    ok = False
            except Exception:
                failed += 1
                ok = False
        # Remove directories (only if include_sub or direct children).
        for d in dirs:
            try:
                if d.exists():
                    # Only remove empty directories. Never recurse here, because
                    # skipped recent/download files may still be inside.
                    d.rmdir()
            except Exception:
                skipped += 1
                if not ignore_locked:
                    ok = False

        try:
            self.last_action_info = (
                f"Deleted {deleted} files, skipped {skipped} locked/non-empty items, "
                f"skipped {skipped_recent} recent files, skipped {skipped_active} active download files, failed {failed}."
            )
        except Exception:
            pass

        return ok

    def _action_archive(self, file_path: str, params: Dict) -> bool:
        """Archive file to zip"""
        dest_folder = params.get("destination", Path(file_path).parent)
        archive_name = params.get("archive_name", "archive_{date}.zip")
        source = Path(file_path)
        if not source.exists() or not source.is_file():
            self.last_action_info = f"Archive failed: source file does not exist: {source}"
            return False
        archive_path = self._planned_archive_destination(source, params)
        if archive_path is None:
            self.last_action_info = "Archive failed: generated archive name is empty or invalid."
            return False
        if self._same_path(source, archive_path):
            self.last_action_info = "Refused to archive a file into itself."
            return False
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Create or append to archive
        mode = 'a' if archive_path.exists() else 'w'
        with zipfile.ZipFile(archive_path, mode, zipfile.ZIP_DEFLATED) as zipf:
            arcname = self._unique_archive_member_name(zipf, source.name)
            zipf.write(source, arcname)

        # Optionally delete original
        if params.get("delete_original", False):
            os.remove(source)

        return True

    def _action_execute(self, file_path: str, params: Dict) -> bool:
        """Execute a command or script"""
        command = params.get("command")
        command_list = params.get("command_list")
        use_shell = bool(params.get("use_shell", False))
        if not command:
            if not isinstance(command_list, list) or not command_list:
                self.last_action_info = "Execute failed: command is missing."
                return False

        values = {
            "path": str(file_path),
            "file": str(file_path),
            "filename": Path(file_path).name,
            "folder": str(Path(file_path).parent),
        }

        if isinstance(command_list, list) and command_list:
            args = [str(part).format_map(_SafeFormat(values)) for part in command_list]
            if not args or not str(args[0]).strip():
                self.last_action_info = "Execute failed: command is empty."
                return False
            subprocess.Popen(args, shell=False)
            return True

        command = str(command)
        command = command.format_map(_SafeFormat(values))
        if use_shell:
            if not bool(params.get("allow_shell_execution", False)):
                self.last_action_info = "Execute refused: shell commands require allow_shell_execution=True."
                return False
            subprocess.Popen(command, shell=True)
            return True

        args = shlex.split(command, posix=(os.name != "nt"))
        if not args:
            self.last_action_info = "Execute failed: command is empty."
            return False
        subprocess.Popen(args, shell=False)
        return True

    def _action_organize(self, file_path: str, params: Dict) -> bool:
        """Organize file by extension, date, or custom rules"""
        file_obj = Path(file_path)
        if not file_obj.exists() or not file_obj.is_file():
            self.last_action_info = f"Organize failed: source file does not exist: {file_obj}"
            return False

        dest_file = self._planned_organize_destination(file_obj, params)
        if dest_file is None:
            if self.last_action_info:
                return True
            self.last_action_info = f"Organize failed: unknown mode {params.get('organize_by')}"
            return False

        # Create destination and move file
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(file_path, dest_file)
        return True

    def _planned_copy_move_destination(self, source: Path, dest_folder: Path, params: Dict[str, Any]) -> Optional[Path]:
        return self._resolve_destination_conflict(source, Path(dest_folder) / source.name, params)

    def _planned_rename_destination(self, source: Path, params: Dict[str, Any]) -> Optional[Path]:
        pattern = params.get("pattern", "{name}")
        now = datetime.now()
        new_name = str(pattern).format_map(_SafeFormat(
            name=source.stem,
            ext=source.suffix,
            date=now.strftime("%Y%m%d"),
            time=now.strftime("%H%M%S"),
            timestamp=now.strftime("%Y%m%d_%H%M%S")
        ))
        final_name = new_name if new_name.lower().endswith(source.suffix.lower()) else new_name + source.suffix
        safe_name = self._safe_file_name(final_name)
        if not safe_name:
            return None
        target = source.parent / safe_name
        if self._same_path(source, target):
            self.last_action_info = "Skipped rename because the generated name is unchanged."
            return None
        return self._get_unique_path(target) if target.exists() else target

    def _planned_archive_destination(self, source: Path, params: Dict[str, Any]) -> Optional[Path]:
        dest_folder = Path(params.get("destination") or source.parent)
        now = datetime.now()
        archive_name = str(params.get("archive_name") or "archive_{date}.zip").format_map(_SafeFormat(
            date=now.strftime("%Y%m%d"),
            time=now.strftime("%H%M%S"),
            timestamp=now.strftime("%Y%m%d_%H%M%S"),
            name=source.stem,
            ext=source.suffix,
        ))
        safe_name = self._safe_file_name(archive_name)
        if not safe_name:
            return None
        return dest_folder / safe_name

    def _planned_organize_destination(self, source: Path, params: Dict[str, Any]) -> Optional[Path]:
        organize_by = str(params.get("organize_by") or "extension").strip().lower()
        base_folder = Path(params.get("destination") or source.parent)
        if organize_by == "extension":
            folder = source.suffix[1:].lower() if source.suffix else "no_extension"
        elif organize_by == "date":
            mod_time = datetime.fromtimestamp(source.stat().st_mtime)
            return self._resolve_destination_conflict(source, base_folder / mod_time.strftime("%Y") / mod_time.strftime("%m") / source.name, params)
        elif organize_by == "type":
            folder = self._file_type_category(source)
        else:
            return None
        return self._resolve_destination_conflict(source, base_folder / folder / source.name, params)

    def _file_type_category(self, source: Path) -> str:
        type_map = {
            "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff"],
            "documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".xlsx", ".pptx", ".csv"],
            "videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"],
            "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
            "archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "code": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".html", ".css", ".go", ".rs", ".json"],
        }
        ext = source.suffix.lower()
        for category, exts in type_map.items():
            if ext in exts:
                return category
        return "others"

    def _resolve_destination_conflict(self, source: Path, dest_file: Path, params: Dict[str, Any]) -> Optional[Path]:
        """Resolve copy/move conflicts without overwriting unless requested explicitly."""
        if self._same_path(source, dest_file):
            self.last_action_info = "Skipped because source and destination are the same file."
            return None
        if not dest_file.exists():
            return dest_file

        policy = str(params.get("handle_duplicates") or "rename").strip().lower()
        if policy in {"rename", "unique", "keep_both"}:
            return self._get_unique_path(dest_file)
        if policy == "overwrite":
            return dest_file

        self.last_action_info = f"Skipped because destination already exists: {dest_file}"
        return None

    def _same_path(self, left: Path, right: Path) -> bool:
        try:
            return left.resolve() == right.resolve()
        except Exception:
            return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))

    def _safe_file_name(self, name: str) -> str:
        """Return a filesystem leaf name; template slashes and invalid chars become underscores."""
        cleaned = str(name or "").strip().replace("/", "_").replace("\\", "_")
        cleaned = re.sub(r'[<>:"|?*\x00-\x1f]', "_", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        if not cleaned:
            return ""

        reserved = {
            "con", "prn", "aux", "nul",
            "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
            "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
        }
        if cleaned.split(".", 1)[0].lower() in reserved:
            cleaned = f"_{cleaned}"
        return cleaned[:240]

    def _unique_archive_member_name(self, zipf: zipfile.ZipFile, name: str) -> str:
        safe = self._safe_file_name(name) or "file"
        existing = set(zipf.namelist())
        if safe not in existing:
            return safe
        path = Path(safe)
        counter = 1
        while True:
            candidate = f"{path.stem}_{counter}{path.suffix}"
            if candidate not in existing:
                return candidate
            counter += 1

    def _is_dangerous_cleanup_root(self, folder: Path) -> bool:
        try:
            resolved = folder.resolve()
        except Exception:
            resolved = folder.absolute()

        protected = [Path.home(), Path.home() / APP_DATA_DIR_NAME]
        try:
            protected.append(Path(os.environ.get("USERPROFILE", "")).resolve())
        except Exception:
            pass
        for env_key in ("WINDIR", "SystemRoot", "ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(env_key)
            if value:
                try:
                    protected.append(Path(value).resolve())
                except Exception:
                    pass

        try:
            if resolved.parent == resolved:
                return True
        except Exception:
            return True

        for item in protected:
            try:
                if item and resolved == item.resolve():
                    return True
            except Exception:
                continue
        return False

    def _get_unique_path(self, path: Path) -> Path:
        """Generate unique file path if file already exists"""
        if not path.exists():
            return path

        counter = 1
        while True:
            new_path = path.parent / f"{path.stem}_{counter}{path.suffix}"
            if not new_path.exists():
                return new_path
            counter += 1


class _SafeFormat(dict):
    def __missing__(self, key):
        return "{" + str(key) + "}"
