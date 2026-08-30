from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from core.cloud_sync.gdrive import GoogleDriveProvider
from core.cloud_sync.onedrive import OneDriveProvider
from core.cloud_sync.sync_state import CloudSyncStateStore, FileStamp, RemoteStamp, SyncRecord
from core.branding import DEFAULT_CLOUD_SYNC_FOLDER


@dataclass(frozen=True)
class SyncStats:
    scanned: int
    skipped: int
    uploaded: int


@dataclass(frozen=True)
class FullSyncStats:
    scanned_local: int
    scanned_remote: int
    skipped: int
    uploaded: int
    downloaded: int
    conflicts: int
    deleted_local: int
    deleted_remote: int


def _default_excluded_dir_names() -> set[str]:
    return {
        ".git",
        ".svn",
        ".hg",
        ".idea",
        ".vscode",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
    }


def _iter_files(
    root: Path,
    *,
    include_subfolders: bool,
    excluded_dir_names: set[str],
    max_files: int,
    cancel_cb: Callable[[], None] | None = None,
):
    root = Path(root)
    if not root.exists():
        return

    count = 0
    if not include_subfolders:
        for p in root.iterdir():
            if cancel_cb:
                cancel_cb()
            if p.is_file():
                yield p
                count += 1
                if count >= max_files:
                    return
        return

    for dirpath, dirnames, filenames in os.walk(root):
        if cancel_cb:
            cancel_cb()
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in excluded_dir_names]
        for fn in filenames:
            if cancel_cb:
                cancel_cb()
            yield Path(dirpath) / fn
            count += 1
            if count >= max_files:
                return


def sync_folder_upload_only(
    provider,
    *,
    local_root: Path,
    remote_base: str,
    include_subfolders: bool = True,
    dry_run: bool = False,
    max_files: int = 200_000,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_cb: Callable[[], None] | None = None,
) -> SyncStats:
    """
    Upload-only sync: uploads new/changed files under remote_base, preserving structure.
    Uses a local stamp store to avoid re-uploading unchanged files.

    provider: OneDriveProvider or GoogleDriveProvider
    """
    local_root = Path(local_root)
    if not local_root.exists():
        raise FileNotFoundError(str(local_root))
    remote_base = str(remote_base or "").strip().strip("/").strip("\\")
    if not remote_base:
        remote_base = DEFAULT_CLOUD_SYNC_FOLDER

    store = CloudSyncStateStore()
    sync_id = CloudSyncStateStore.make_sync_id(local_root)
    _prev_remote, stamps = store.load(provider=provider.name, sync_id=sync_id)

    excluded = _default_excluded_dir_names()

    # We do a quick pre-count for a stable progress bar, but cap time by using max_files.
    if status_cb:
        status_cb("Counting files…")
    files = list(_iter_files(local_root, include_subfolders=include_subfolders, excluded_dir_names=excluded, max_files=max_files, cancel_cb=cancel_cb))
    total = len(files)
    scanned = skipped = uploaded = 0

    # Folder id cache for providers that need it (Google Drive).
    folder_cache: dict[str, str] = {}

    def ensure_remote_folder(rel_dir: str) -> str | None:
        rel_dir = rel_dir.strip().strip("/").strip("\\")
        full = f"{remote_base}/{rel_dir}" if rel_dir else remote_base

        if isinstance(provider, OneDriveProvider):
            provider.ensure_folder_path(full)
            return full

        if isinstance(provider, GoogleDriveProvider):
            if full in folder_cache:
                return folder_cache[full]
            folder_id = provider.ensure_folder_path(full)
            folder_cache[full] = folder_id
            return folder_id

        return None

    for i, fp in enumerate(files):
        if cancel_cb:
            cancel_cb()
        scanned += 1

        rel = str(fp.relative_to(local_root)).replace("\\", "/")
        try:
            st = fp.stat()
            cur = FileStamp(size=int(st.st_size), mtime_ns=int(st.st_mtime_ns))
        except Exception:
            continue

        prev = stamps.get(rel)
        if prev and prev.size == cur.size and prev.mtime_ns == cur.mtime_ns:
            skipped += 1
            if progress_cb:
                progress_cb(i + 1, total, f"Skipping unchanged: {rel}")
            continue

        if progress_cb:
            progress_cb(i + 1, total, f"{'Would upload' if dry_run else 'Uploading'}: {rel}")

        rel_dir = str(Path(rel).parent).replace("\\", "/")
        remote_folder_handle = ensure_remote_folder("" if rel_dir == "." else rel_dir)

        if not dry_run:
            if isinstance(provider, OneDriveProvider):
                provider.upload_file(fp, remote_folder=str(remote_folder_handle or remote_base))
            elif isinstance(provider, GoogleDriveProvider):
                provider.upload_file(fp, remote_folder=str(remote_folder_handle or ""))
            else:
                raise RuntimeError("Unsupported cloud provider")
        uploaded += 1
        stamps[rel] = cur

        # Persist every N files for resilience on long runs.
        if (uploaded % 20) == 0 and not dry_run:
            store.save(provider=provider.name, sync_id=sync_id, remote_base=remote_base, files=stamps)

    if not dry_run:
        store.save(provider=provider.name, sync_id=sync_id, remote_base=remote_base, files=stamps)

    if status_cb:
        status_cb(f"Done. Scanned {scanned}, uploaded {uploaded}, skipped {skipped}.")
    return SyncStats(scanned=scanned, skipped=skipped, uploaded=uploaded)


def _iso_to_mtime_ns(v: str | None) -> int:
    if not v:
        return 0
    s = str(v).strip()
    if not s:
        return 0
    try:
        # OneDrive is usually "...Z". Google is RFC3339 with zone.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except Exception:
        return 0


def _remote_stamp_for(provider, item) -> RemoteStamp:
    size = int(getattr(item, "size", None) or 0)
    mt = _iso_to_mtime_ns(getattr(item, "modified_time", None))
    token = ""
    if isinstance(provider, OneDriveProvider):
        token = str(getattr(item, "etag", None) or "")
    elif isinstance(provider, GoogleDriveProvider):
        token = str(getattr(item, "md5", None) or "")
    if not token:
        token = str(getattr(item, "modified_time", None) or "")
    return RemoteStamp(size=size, mtime_ns=mt, token=token)


def _remote_list_tree(
    provider,
    *,
    remote_base: str,
    include_subfolders: bool,
    max_files: int,
    status_cb: Callable[[str], None] | None = None,
    cancel_cb: Callable[[], None] | None = None,
) -> tuple[dict[str, tuple[object, RemoteStamp]], str | None]:
    """
    Returns:
      remote_files: rel_path -> (CloudItem, RemoteStamp)
      remote_root_handle:
        - OneDrive: path under root (remote_base normalized)
        - Google Drive: folder id for remote_base
    """
    remote_base = str(remote_base or "").strip().strip("/").strip("\\")
    if not remote_base:
        remote_base = DEFAULT_CLOUD_SYNC_FOLDER

    if isinstance(provider, OneDriveProvider):
        provider.ensure_folder_path(remote_base)
        root_handle = remote_base

        out: dict[str, tuple[object, RemoteStamp]] = {}
        count = 0

        def rec(folder_path: str, rel_prefix: str):
            nonlocal count
            if cancel_cb:
                cancel_cb()
            if count >= max_files:
                return
            try:
                items = provider.list_folder(folder_path, limit=500)
            except Exception as e:
                raise RuntimeError(f"Could not list OneDrive folder: {folder_path}") from e
            for it in items:
                if cancel_cb:
                    cancel_cb()
                if count >= max_files:
                    return
                name = str(getattr(it, "name", "") or "")
                if not name:
                    continue
                if not _safe_remote_rel(name):
                    continue
                if getattr(it, "is_folder", False):
                    if include_subfolders:
                        child_path = f"{folder_path}/{name}".strip("/")
                        rec(child_path, f"{rel_prefix}{name}/")
                    continue
                rel = f"{rel_prefix}{name}"
                safe_rel = _safe_remote_rel(rel)
                if safe_rel:
                    out[safe_rel] = (it, _remote_stamp_for(provider, it))
                    count += 1

        if status_cb:
            status_cb("Listing remote files…")
        rec(root_handle, "")
        return out, root_handle

    if isinstance(provider, GoogleDriveProvider):
        root_id = provider.ensure_folder_path(remote_base)
        out: dict[str, tuple[object, RemoteStamp]] = {}
        count = 0

        def rec(folder_id: str, rel_prefix: str):
            nonlocal count
            if cancel_cb:
                cancel_cb()
            if count >= max_files:
                return
            try:
                items = provider.list_folder(folder_id, limit=1000)
            except Exception as e:
                raise RuntimeError(f"Could not list Google Drive folder: {folder_id}") from e
            for it in items:
                if cancel_cb:
                    cancel_cb()
                if count >= max_files:
                    return
                name = str(getattr(it, "name", "") or "")
                if not name:
                    continue
                if not _safe_remote_rel(name):
                    continue
                if getattr(it, "is_folder", False):
                    if include_subfolders:
                        rec(str(getattr(it, "id", "") or ""), f"{rel_prefix}{name}/")
                    continue

                mime = str(getattr(it, "mime_type", "") or "")
                if mime.startswith("application/vnd.google-apps."):
                    # Google Docs/Sheets/etc require export logic; skip for now.
                    continue

                rel = f"{rel_prefix}{name}"
                safe_rel = _safe_remote_rel(rel)
                if safe_rel:
                    out[safe_rel] = (it, _remote_stamp_for(provider, it))
                    count += 1

        if status_cb:
            status_cb("Listing remote files…")
        rec(root_id, "")
        return out, root_id

    raise RuntimeError("Unsupported cloud provider")


def _conflict_name(name: str, *, side: str) -> str:
    p = Path(name)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    suf = p.suffix
    stem = p.stem
    return f"{stem} (conflict {side} {stamp}){suf}"


def _safe_write_local_file(provider_name: str, path: Path) -> None:
    # Placeholder for future: Windows "file in use" detection.
    # For now we just ensure parent exists.
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _safe_remote_rel(rel: str) -> str:
    raw = str(rel or "").replace("\\", "/").lstrip("/")
    if "\r" in raw or "\n" in raw:
        return ""
    parts = []
    for part in raw.split("/"):
        piece = part.strip()
        if not piece or piece in {".", ".."}:
            return ""
        parts.append(piece)
    return "/".join(parts)


def _safe_local_component(name: str) -> str:
    import re

    cleaned = str(name or "").strip()
    cleaned = re.sub(r'[<>:"|?*\x00-\x1f]', "_", cleaned)
    cleaned = cleaned.strip(" .")
    reserved = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }
    if cleaned.split(".", 1)[0].lower() in reserved:
        cleaned = f"_{cleaned}"
    return cleaned[:180] or "cloud_file"


def _safe_local_path(local_root: Path, rel: str) -> Path:
    safe_rel = _safe_remote_rel(rel)
    if not safe_rel:
        raise ValueError(f"Unsafe cloud relative path: {rel}")
    out = Path(local_root).joinpath(*[_safe_local_component(p) for p in safe_rel.split("/")])
    root_resolved = Path(local_root).resolve()
    out_resolved = out.resolve()
    if root_resolved != out_resolved and root_resolved not in out_resolved.parents:
        raise ValueError(f"Unsafe cloud local path: {out}")
    return out


def sync_folder_download_only(
    provider,
    *,
    local_root: Path,
    remote_base: str,
    include_subfolders: bool = True,
    dry_run: bool = False,
    max_files: int = 200_000,
    delete_policy: Literal["ignore", "mirror"] = "ignore",
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_cb: Callable[[], None] | None = None,
) -> FullSyncStats:
    """
    Download-only sync: downloads new/changed remote files under remote_base into local_root.

    delete_policy:
      - ignore (default): remote deletions do not delete local files
      - mirror: remote deletions delete local files (dangerous)
    """
    local_root = Path(local_root)
    if not local_root.exists():
        raise FileNotFoundError(str(local_root))

    store = CloudSyncStateStore()
    sync_id = CloudSyncStateStore.make_sync_id(local_root)
    _prev_remote, records = store.load_records(provider=provider.name, sync_id=sync_id)

    remote_files, _root_handle = _remote_list_tree(
        provider,
        remote_base=remote_base,
        include_subfolders=include_subfolders,
        max_files=max_files,
        status_cb=status_cb,
        cancel_cb=cancel_cb,
    )

    # local presence map (only to detect deletions with mirror policy)
    excluded = _default_excluded_dir_names()
    local_map: dict[str, FileStamp] = {}
    for fp in _iter_files(local_root, include_subfolders=include_subfolders, excluded_dir_names=excluded, max_files=max_files, cancel_cb=cancel_cb):
        try:
            st = fp.stat()
            rel = str(fp.relative_to(local_root)).replace("\\", "/")
            local_map[rel] = FileStamp(size=int(st.st_size), mtime_ns=int(st.st_mtime_ns))
        except Exception:
            continue

    scanned_local = len(local_map)
    scanned_remote = len(remote_files)
    skipped = uploaded = 0
    downloaded = conflicts = deleted_local = deleted_remote = 0

    # Work set includes previous records too, so deletions can be handled.
    rels = set(remote_files.keys()) | set(local_map.keys()) | set(records.keys())
    total = max(1, len(rels))

    def _rec_for(rel: str) -> SyncRecord:
        return records.get(rel) or SyncRecord(local=None, remote=None)

    for i, rel in enumerate(sorted(rels)):
        if cancel_cb:
            cancel_cb()
        if progress_cb:
            progress_cb(i, total, rel)

        in_remote = rel in remote_files
        in_local = rel in local_map
        had_prev = rel in records
        prev = _rec_for(rel)

        if in_remote:
            it, rstamp = remote_files[rel]
        else:
            it, rstamp = None, None

        # Handle remote deletions
        if not in_remote and in_local and prev.remote is not None:
            if delete_policy == "mirror":
                if not dry_run:
                    try:
                        _safe_local_path(local_root, rel).unlink(missing_ok=True)
                    except Exception:
                        pass
                deleted_local += 1
                records[rel] = SyncRecord(local=None, remote=None)
            else:
                # keep local; don't re-upload in download-only mode
                records[rel] = SyncRecord(local=local_map.get(rel), remote=None)
                skipped += 1
            continue

        if not in_remote:
            # nothing to do
            records[rel] = SyncRecord(local=local_map.get(rel), remote=None)
            skipped += 1
            continue

        # Remote exists
        cur_remote = rstamp
        prev_remote = prev.remote
        prev_local = prev.local
        cur_local = local_map.get(rel)

        # First run baseline: if we have never seen this rel path before and it exists on both
        # sides, record the current stamps without moving data.
        if had_prev is False and cur_local is not None and cur_remote is not None:
            records[rel] = SyncRecord(local=cur_local, remote=cur_remote)
            skipped += 1
            continue

        remote_changed = prev_remote is None or cur_remote != prev_remote
        local_changed = prev_local is None or (cur_local is not None and cur_local != prev_local)

        # If local is missing, this is either a new remote file or a locally-deleted file that we should restore.
        if cur_local is None:
            if prev_local is None:
                # new remote file
                remote_changed = True
            elif delete_policy == "ignore":
                # local deletion, do not restore
                records[rel] = SyncRecord(local=None, remote=cur_remote)
                skipped += 1
                continue

        if not remote_changed and not local_changed:
            records[rel] = SyncRecord(local=cur_local, remote=cur_remote)
            skipped += 1
            continue

        # Download remote -> local (overwrite)
        dst = _safe_local_path(local_root, rel)
        _safe_write_local_file(provider.name, dst)
        if not dry_run:
            try:
                provider.download_file(str(getattr(it, "id", "")), dst)
            except Exception:
                # If download fails, keep previous record and continue.
                skipped += 1
                continue
        try:
            st = dst.stat()
            cur_local2 = FileStamp(size=int(st.st_size), mtime_ns=int(st.st_mtime_ns))
        except Exception:
            cur_local2 = cur_local

        downloaded += 1
        records[rel] = SyncRecord(local=cur_local2, remote=cur_remote)

    if not dry_run:
        store.save_records(provider=provider.name, sync_id=sync_id, remote_base=str(remote_base or ""), files=records)

    if status_cb:
        status_cb(f"Done. Downloaded {downloaded}, skipped {skipped}.")

    return FullSyncStats(
        scanned_local=scanned_local,
        scanned_remote=scanned_remote,
        skipped=skipped,
        uploaded=uploaded,
        downloaded=downloaded,
        conflicts=conflicts,
        deleted_local=deleted_local,
        deleted_remote=deleted_remote,
    )


def sync_folder_two_way(
    provider,
    *,
    local_root: Path,
    remote_base: str,
    include_subfolders: bool = True,
    dry_run: bool = False,
    max_files: int = 200_000,
    delete_policy: Literal["ignore", "mirror"] = "ignore",
    conflict_policy: Literal["keep_both", "prefer_local", "prefer_remote"] = "keep_both",
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_cb: Callable[[], None] | None = None,
) -> FullSyncStats:
    """
    Two-way sync between local_root and remote_base.

    Safety defaults:
      - delete_policy="ignore": deletions do not propagate; missing-on-one-side is treated as a deletion only if it existed on both sides at last sync.
      - conflict_policy="keep_both": avoids overwriting either side by saving a conflict copy.
    """
    local_root = Path(local_root)
    if not local_root.exists():
        raise FileNotFoundError(str(local_root))

    store = CloudSyncStateStore()
    sync_id = CloudSyncStateStore.make_sync_id(local_root)
    _prev_remote, records = store.load_records(provider=provider.name, sync_id=sync_id)

    excluded = _default_excluded_dir_names()
    local_map: dict[str, FileStamp] = {}
    for fp in _iter_files(local_root, include_subfolders=include_subfolders, excluded_dir_names=excluded, max_files=max_files, cancel_cb=cancel_cb):
        try:
            st = fp.stat()
            rel = str(fp.relative_to(local_root)).replace("\\", "/")
            local_map[rel] = FileStamp(size=int(st.st_size), mtime_ns=int(st.st_mtime_ns))
        except Exception:
            continue

    remote_files, _root_handle = _remote_list_tree(
        provider,
        remote_base=remote_base,
        include_subfolders=include_subfolders,
        max_files=max_files,
        status_cb=status_cb,
        cancel_cb=cancel_cb,
    )

    scanned_local = len(local_map)
    scanned_remote = len(remote_files)
    skipped = uploaded = downloaded = conflicts = deleted_local = deleted_remote = 0

    # Folder id cache for providers that need it (Google Drive).
    folder_cache: dict[str, str] = {}

    def ensure_remote_folder(rel_dir: str) -> str | None:
        rel_dir = rel_dir.strip().strip("/").strip("\\")
        full = f"{str(remote_base or '').strip().strip('/').strip('\\\\')}/{rel_dir}" if rel_dir else str(remote_base or '').strip().strip('/').strip('\\\\')  # noqa: E501
        full = full.strip().strip("/").strip("\\")
        if not full:
            full = DEFAULT_CLOUD_SYNC_FOLDER

        if isinstance(provider, OneDriveProvider):
            provider.ensure_folder_path(full)
            return full

        if isinstance(provider, GoogleDriveProvider):
            if full in folder_cache:
                return folder_cache[full]
            folder_id = provider.ensure_folder_path(full)
            folder_cache[full] = folder_id
            return folder_id

        return None

    def upload_rel(rel: str, *, src_path: Path, name_override: str | None = None, existing_remote_item=None) -> RemoteStamp | None:
        rel_dir = str(Path(rel).parent).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        remote_folder_handle = ensure_remote_folder(rel_dir)
        remote_name = name_override or Path(rel).name
        if dry_run:
            return RemoteStamp(size=int(src_path.stat().st_size), mtime_ns=int(src_path.stat().st_mtime_ns), token="dry_run")

        if isinstance(provider, OneDriveProvider):
            res = provider.upload_file(src_path, remote_folder=str(remote_folder_handle or remote_base), remote_name=remote_name)
            return _remote_stamp_for(provider, res)

        if isinstance(provider, GoogleDriveProvider):
            existing_id = str(getattr(existing_remote_item, "id", "") or "")
            if existing_id:
                res = provider.update_file(existing_id, src_path)
            else:
                res = provider.upload_file(src_path, remote_folder=str(remote_folder_handle or ""), remote_name=remote_name)
            return _remote_stamp_for(provider, res)

        raise RuntimeError("Unsupported cloud provider")

    def download_rel(rel: str, *, item, name_override: str | None = None) -> FileStamp | None:
        dst = _safe_local_path(local_root, name_override or rel)
        _safe_write_local_file(provider.name, dst)
        if not dry_run:
            provider.download_file(str(getattr(item, "id", "")), dst)
        try:
            st = dst.stat()
            return FileStamp(size=int(st.st_size), mtime_ns=int(st.st_mtime_ns))
        except Exception:
            return None

    rels = set(remote_files.keys()) | set(local_map.keys()) | set(records.keys())
    total = max(1, len(rels))

    for i, rel in enumerate(sorted(rels)):
        if cancel_cb:
            cancel_cb()
        if progress_cb:
            progress_cb(i, total, rel)

        in_local = rel in local_map
        in_remote = rel in remote_files
        had_prev = rel in records
        prev = records.get(rel) or SyncRecord(local=None, remote=None)

        if in_remote:
            remote_item, cur_remote = remote_files[rel]
        else:
            remote_item, cur_remote = None, None
        cur_local = local_map.get(rel)

        # Missing cases: detect deletions vs new files based on last sync record.
        if in_local and not in_remote:
            if prev.remote is not None:
                # remote deletion
                if delete_policy == "mirror":
                    if not dry_run:
                        try:
                            _safe_local_path(local_root, rel).unlink(missing_ok=True)
                        except Exception:
                            pass
                    deleted_local += 1
                    records[rel] = SyncRecord(local=None, remote=None)
                else:
                    # keep local; do not restore to cloud automatically
                    records[rel] = SyncRecord(local=cur_local, remote=None)
                    skipped += 1
            else:
                # new local file -> upload
                try:
                    new_remote = upload_rel(rel, src_path=local_root / rel, existing_remote_item=None)
                    uploaded += 1
                    records[rel] = SyncRecord(local=cur_local, remote=new_remote)
                except Exception:
                    skipped += 1
            continue

        if in_remote and not in_local:
            if prev.local is not None:
                # local deletion
                if delete_policy == "mirror":
                    if not dry_run:
                        try:
                            provider.delete_item(str(getattr(remote_item, "id", "")))
                        except Exception:
                            pass
                    deleted_remote += 1
                    records[rel] = SyncRecord(local=None, remote=None)
                else:
                    records[rel] = SyncRecord(local=None, remote=cur_remote)
                    skipped += 1
            else:
                # new remote file -> download
                try:
                    new_local = download_rel(rel, item=remote_item)
                    downloaded += 1
                    records[rel] = SyncRecord(local=new_local, remote=cur_remote)
                except Exception:
                    skipped += 1
            continue

        if not in_local and not in_remote:
            # removed on both sides
            records[rel] = SyncRecord(local=None, remote=None)
            skipped += 1
            continue

        # Both present
        prev_local = prev.local
        prev_remote = prev.remote

        # First run baseline: if we have never seen this rel path before and it exists on both
        # sides, record the current stamps without moving data.
        if not had_prev:
            records[rel] = SyncRecord(local=cur_local, remote=cur_remote)
            skipped += 1
            continue

        local_changed = prev_local is None or cur_local != prev_local
        remote_changed = prev_remote is None or cur_remote != prev_remote

        if not local_changed and not remote_changed:
            records[rel] = SyncRecord(local=cur_local, remote=cur_remote)
            skipped += 1
            continue

        if local_changed and not remote_changed:
            try:
                new_remote = upload_rel(rel, src_path=local_root / rel, existing_remote_item=remote_item)
                uploaded += 1
                records[rel] = SyncRecord(local=cur_local, remote=new_remote)
            except Exception:
                skipped += 1
            continue

        if remote_changed and not local_changed:
            try:
                new_local = download_rel(rel, item=remote_item)
                downloaded += 1
                records[rel] = SyncRecord(local=new_local, remote=cur_remote)
            except Exception:
                skipped += 1
            continue

        # Conflict
        conflicts += 1
        if conflict_policy == "prefer_local":
            try:
                new_remote = upload_rel(rel, src_path=local_root / rel, existing_remote_item=remote_item)
                uploaded += 1
                records[rel] = SyncRecord(local=cur_local, remote=new_remote)
            except Exception:
                skipped += 1
            continue

        if conflict_policy == "prefer_remote":
            try:
                new_local = download_rel(rel, item=remote_item)
                downloaded += 1
                records[rel] = SyncRecord(local=new_local, remote=cur_remote)
            except Exception:
                skipped += 1
            continue

        # keep_both: keep the newer version as the primary, save the older as a conflict copy on the other side.
        remote_newer = bool(cur_remote and cur_remote.mtime_ns and cur_remote.mtime_ns >= int(cur_local.mtime_ns if cur_local else 0))
        try:
            if remote_newer:
                # Primary: remote -> local overwrite; preserve local as conflict on remote
                try:
                    conflict_remote_name = _conflict_name(Path(rel).name, side="local")
                    upload_rel(rel, src_path=local_root / rel, name_override=conflict_remote_name, existing_remote_item=None)
                    uploaded += 1
                except Exception:
                    pass
                new_local = download_rel(rel, item=remote_item)
                downloaded += 1
                records[rel] = SyncRecord(local=new_local, remote=cur_remote)
            else:
                # Primary: local -> remote overwrite; preserve remote as conflict on local
                try:
                    conflict_local_name = str(Path(rel).with_name(_conflict_name(Path(rel).name, side="remote")).as_posix())
                    download_rel(rel, item=remote_item, name_override=conflict_local_name)
                    downloaded += 1
                except Exception:
                    pass
                new_remote = upload_rel(rel, src_path=local_root / rel, existing_remote_item=remote_item)
                uploaded += 1
                records[rel] = SyncRecord(local=cur_local, remote=new_remote)
        except Exception:
            skipped += 1
            records[rel] = SyncRecord(local=cur_local, remote=cur_remote)

    if not dry_run:
        store.save_records(provider=provider.name, sync_id=sync_id, remote_base=str(remote_base or ""), files=records)
    if status_cb:
        status_cb(f"Done. Uploaded {uploaded}, downloaded {downloaded}, conflicts {conflicts}.")

    return FullSyncStats(
        scanned_local=scanned_local,
        scanned_remote=scanned_remote,
        skipped=skipped,
        uploaded=uploaded,
        downloaded=downloaded,
        conflicts=conflicts,
        deleted_local=deleted_local,
        deleted_remote=deleted_remote,
    )
