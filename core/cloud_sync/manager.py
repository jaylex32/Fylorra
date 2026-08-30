from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Literal

from core.cloud_sync.gdrive import GoogleDriveProvider
from core.cloud_sync.onedrive import OneDriveProvider
from core.cloud_sync.sync_engine import FullSyncStats, SyncStats, sync_folder_download_only, sync_folder_two_way, sync_folder_upload_only
from core.cloud_sync.token_store import CloudTokenStore

ProviderName = Literal["onedrive", "gdrive"]


@dataclass(frozen=True)
class CloudSyncResult:
    provider: ProviderName
    summary: str


class CloudSyncManager:
    """
    Thin convenience wrapper around cloud providers + sync helpers.

    Goal: keep all cloud operations reusable from multiple UI pages.
    """

    def __init__(self, *, settings_manager, token_store: CloudTokenStore | None = None):
        self._settings = settings_manager
        self._tokens = token_store or CloudTokenStore()
        self._onedrive = OneDriveProvider(settings_manager=self._settings, token_store=self._tokens)
        self._gdrive = GoogleDriveProvider(settings_manager=self._settings, token_store=self._tokens)

    @property
    def token_store(self) -> CloudTokenStore:
        return self._tokens

    def provider(self, name: ProviderName):
        if name == "onedrive":
            return self._onedrive
        if name == "gdrive":
            return self._gdrive
        raise ValueError(f"Unknown provider: {name}")

    def is_connected(self, name: ProviderName) -> bool:
        return bool(self.provider(name).is_connected())

    def connect(self, name: ProviderName, *, status_cb=None) -> str | None:
        p = self.provider(name)
        if name == "onedrive":
            return p.connect(status_cb=status_cb)
        return p.connect()

    def disconnect(self, name: ProviderName) -> None:
        self.provider(name).disconnect()

    def test(self, name: ProviderName) -> str:
        return str(self.provider(name).test_connection())

    def list_root(self, name: ProviderName, *, limit: int = 100):
        return self.provider(name).list_root(limit=limit)

    def list_folder(self, name: ProviderName, folder_ref: str, *, limit: int = 200):
        """
        folder_ref:
        - OneDrive: remote path (e.g. "Fylorra Sync/Pictures")
        - Google Drive: folder id (or "root")
        """
        p = self.provider(name)
        if hasattr(p, "list_folder"):
            return p.list_folder(folder_ref, limit=limit)  # type: ignore[attr-defined]
        return p.list_root(limit=limit)

    def upload_file(
        self,
        name: ProviderName,
        local_path: Path,
        *,
        remote_folder: str | None = None,
        remote_name: str | None = None,
        progress_cb=None,
    ):
        return self.provider(name).upload_file(
            local_path,
            remote_folder=remote_folder,
            remote_name=remote_name,
            progress_cb=progress_cb,
        )

    def download_file(self, name: ProviderName, item_id: str, dest_path: Path, *, progress_cb=None):
        return self.provider(name).download_file(item_id, dest_path, progress_cb=progress_cb)

    def sync_upload_only(
        self,
        name: ProviderName,
        *,
        local_root: Path,
        remote_base: str,
        include_subfolders: bool = True,
        dry_run: bool = False,
        max_files: int = 200_000,
        status_cb=None,
        progress_cb=None,
        cancel_cb=None,
    ) -> SyncStats:
        p = self.provider(name)
        return sync_folder_upload_only(
            p,
            local_root=Path(local_root),
            remote_base=str(remote_base or ""),
            include_subfolders=bool(include_subfolders),
            dry_run=bool(dry_run),
            max_files=int(max_files),
            status_cb=status_cb,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )

    def sync_download_only(
        self,
        name: ProviderName,
        *,
        local_root: Path,
        remote_base: str,
        include_subfolders: bool = True,
        dry_run: bool = False,
        delete_policy: str = "ignore",
        max_files: int = 200_000,
        status_cb=None,
        progress_cb=None,
        cancel_cb=None,
    ) -> FullSyncStats:
        p = self.provider(name)
        return sync_folder_download_only(
            p,
            local_root=Path(local_root),
            remote_base=str(remote_base or ""),
            include_subfolders=bool(include_subfolders),
            dry_run=bool(dry_run),
            delete_policy=str(delete_policy or "ignore"),
            max_files=int(max_files),
            status_cb=status_cb,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )

    def sync_two_way(
        self,
        name: ProviderName,
        *,
        local_root: Path,
        remote_base: str,
        include_subfolders: bool = True,
        dry_run: bool = False,
        delete_policy: str = "ignore",
        conflict_policy: str = "keep_both",
        max_files: int = 200_000,
        status_cb=None,
        progress_cb=None,
        cancel_cb=None,
    ) -> FullSyncStats:
        p = self.provider(name)
        return sync_folder_two_way(
            p,
            local_root=Path(local_root),
            remote_base=str(remote_base or ""),
            include_subfolders=bool(include_subfolders),
            dry_run=bool(dry_run),
            delete_policy=str(delete_policy or "ignore"),
            conflict_policy=str(conflict_policy or "keep_both"),
            max_files=int(max_files),
            status_cb=status_cb,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )

    def transfer_file_between_providers(
        self,
        *,
        src: ProviderName,
        src_item_id: str,
        src_name: str,
        dest: ProviderName,
        dest_folder: str | None,
        dest_name: str | None = None,
        progress_cb=None,
        cancel_cb=None,
    ):
        """
        Simple cloud→cloud transfer for a single file: download to a temp file, then upload to dest.

        dest_folder:
          - OneDrive: remote path under root
          - Google Drive: folder id OR a /path (caller may pre-resolve)
        """
        if cancel_cb:
            cancel_cb()
        tmp_dir = Path(tempfile.gettempdir()) / "fylorra_cloud_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / (dest_name or src_name or "download.bin")

        def prog_phase(phase: str):
            if callable(progress_cb):
                try:
                    progress_cb(0, 0, phase)
                except Exception:
                    pass

        prog_phase("Downloading…")
        self.download_file(src, src_item_id, tmp_path, progress_cb=progress_cb)
        if cancel_cb:
            cancel_cb()
        prog_phase("Uploading…")
        out = self.upload_file(dest, tmp_path, remote_folder=dest_folder, remote_name=dest_name or src_name, progress_cb=progress_cb)
        try:
            tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass
        return out

    def transfer_folder_between_providers(
        self,
        *,
        src: ProviderName,
        src_folder_ref: str,
        src_folder_name: str,
        dest: ProviderName,
        dest_folder: str | None,
        progress_cb=None,
        cancel_cb=None,
    ) -> None:
        """
        Cloud→cloud transfer for a folder: recursively download files to a temp dir and upload into dest.

        src_folder_ref:
          - OneDrive: folder path under root (e.g. "Fylorra Sync/Pictures/Album")
          - Google Drive: folder id

        dest_folder:
          - OneDrive: destination folder path under root
          - Google Drive: destination folder id
        """
        if cancel_cb:
            cancel_cb()

        src_folder_name = str(src_folder_name or "").strip() or "Folder"
        dest_folder = str(dest_folder or "").strip()

        tmp_root = Path(tempfile.gettempdir()) / "fylorra_cloud_tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        src_p = self.provider(src)
        dest_p = self.provider(dest)
        if not src_p.is_connected() or not dest_p.is_connected():
            raise RuntimeError("Both providers must be connected.")

        # Destination root for this transfer = dest_folder / src_folder_name.
        if dest == "onedrive":
            dest_root_path = f"{dest_folder}/{src_folder_name}".strip("/").strip("\\")
            # Ensure root exists.
            dest_p.ensure_folder_path(dest_root_path)  # type: ignore[attr-defined]
        else:
            # Google Drive: ensure a child folder exists under dest_folder id.
            dest_parent_id = dest_folder or "root"

            def _gd_get_or_create(parent_id: str, name: str) -> str:
                for it in dest_p.list_folder(parent_id, limit=500):  # type: ignore[attr-defined]
                    if it.is_folder and (it.name or "") == name:
                        return it.id
                created = dest_p.create_folder(parent_id=parent_id, name=name)  # type: ignore[attr-defined]
                return created.id

            dest_root_id = _gd_get_or_create(dest_parent_id, src_folder_name)

        # For Google Drive, keep a mapping of relative folder path -> folder id.
        gd_folder_map: dict[str, str] = {}
        if dest == "gdrive":
            gd_folder_map[""] = dest_root_id  # type: ignore[name-defined]

        processed = 0

        def _progress(msg: str):
            if callable(progress_cb):
                try:
                    progress_cb(processed, 0, msg)
                except Exception:
                    pass

        def _iter_children(folder_ref: str):
            if src == "onedrive":
                return src_p.list_folder(folder_ref, limit=500)  # type: ignore[attr-defined]
            return src_p.list_folder(folder_ref or "root", limit=500)  # type: ignore[attr-defined]

        def _walk(src_ref: str, rel_dir: str):
            nonlocal processed
            if cancel_cb:
                cancel_cb()
            children = _iter_children(src_ref)
            for it in children:
                if cancel_cb:
                    cancel_cb()
                name = str(it.name or "").strip()
                if not name:
                    continue
                child_rel = f"{rel_dir}/{name}".strip("/")
                if it.is_folder:
                    if src == "onedrive":
                        child_ref = f"{src_ref}/{name}".strip("/").strip("\\")
                    else:
                        child_ref = str(it.id or "")
                    if dest == "onedrive":
                        dest_path = f"{dest_root_path}/{child_rel}".strip("/").strip("\\")  # type: ignore[name-defined]
                        dest_p.ensure_folder_path(dest_path)  # type: ignore[attr-defined]
                    else:
                        parent_rel = rel_dir.strip("/")
                        parent_id = gd_folder_map.get(parent_rel, gd_folder_map.get("", "root"))
                        # Create (or reuse) folder under the parent id.
                        folder_id = None
                        for existing in dest_p.list_folder(parent_id, limit=500):  # type: ignore[attr-defined]
                            if existing.is_folder and (existing.name or "") == name:
                                folder_id = existing.id
                                break
                        if folder_id is None:
                            folder_id = dest_p.create_folder(parent_id=parent_id, name=name).id  # type: ignore[attr-defined]
                        gd_folder_map[child_rel] = folder_id
                    _walk(child_ref, child_rel)
                    continue

                # File
                processed += 1
                _progress(f"Transferring {child_rel}")
                tmp_path = tmp_root / f"{it.id}_{name}"
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass

                self.download_file(src, it.id, tmp_path, progress_cb=progress_cb)
                if cancel_cb:
                    cancel_cb()

                if dest == "onedrive":
                    dest_dir = f"{dest_root_path}/{rel_dir}".strip("/").strip("\\")  # type: ignore[name-defined]
                    dest_p.ensure_folder_path(dest_dir)  # type: ignore[attr-defined]
                    self.upload_file(dest, tmp_path, remote_folder=dest_dir, remote_name=name, progress_cb=progress_cb)
                else:
                    dest_dir_id = gd_folder_map.get(rel_dir.strip("/"), gd_folder_map.get("", "root"))
                    self.upload_file(dest, tmp_path, remote_folder=dest_dir_id, remote_name=name, progress_cb=progress_cb)

                try:
                    tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
                except Exception:
                    pass

        _progress("Scanning folder…")
        _walk(str(src_folder_ref or "").strip(), "")
        _progress("Done.")

    def ensure_gdrive_folder_path(self, path_like: str) -> str:
        """
        Create (if needed) and return a Google Drive folder id for a /-separated path under root.
        """
        p = self.provider("gdrive")
        if hasattr(p, "ensure_folder_path"):
            return p.ensure_folder_path(path_like)  # type: ignore[attr-defined]
        raise RuntimeError("Google Drive provider does not support ensure_folder_path()")

    def sync_upload_only(
        self,
        name: ProviderName,
        *,
        local_root: Path,
        remote_folder: str,
        include_subfolders: bool,
        max_files: int = 200_000,
        excluded_dir_names: set[str] | None = None,
        progress_cb=None,
        cancel_cb=None,
    ) -> SyncStats:
        p = self.provider(name)
        if not p.is_connected():
            raise RuntimeError(f"{name} is not connected.")
        return sync_folder_upload_only(
            provider=p,
            local_root=local_root,
            remote_folder=remote_folder,
            include_subfolders=include_subfolders,
            max_files=max_files,
            excluded_dir_names=excluded_dir_names,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )
