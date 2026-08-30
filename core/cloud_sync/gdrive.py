from __future__ import annotations

from pathlib import Path
from typing import Any

import json

try:
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload  # type: ignore
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore
except Exception:  # pragma: no cover
    build = None  # type: ignore
    MediaFileUpload = None  # type: ignore
    MediaIoBaseDownload = None  # type: ignore
    InstalledAppFlow = None  # type: ignore
    Credentials = None  # type: ignore

import io

from core.cloud_sync.base import CloudItem
from core.cloud_sync.app_credentials import get_gdrive_client_secrets_path
from core.cloud_sync.token_store import CloudTokenStore


SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveProvider:
    name = "Google Drive"

    def __init__(self, *, settings_manager, token_store: CloudTokenStore | None = None):
        self._settings = settings_manager
        self._tokens = token_store or CloudTokenStore()
        self._creds = None

    def _ensure_deps(self) -> None:
        if build is None or InstalledAppFlow is None or Credentials is None:
            raise RuntimeError(
                "Google Drive dependencies missing. Install: google-auth, google-auth-oauthlib, google-api-python-client"
            )

    def _load_creds(self):
        self._ensure_deps()
        if self._creds is not None:
            return self._creds
        raw = self._tokens.get("gdrive", "credentials_json", "")
        if raw:
            try:
                info = json.loads(raw)
                self._creds = Credentials.from_authorized_user_info(info, SCOPES)  # type: ignore[arg-type]
            except Exception:
                self._creds = None
        return self._creds

    def _save_creds(self, creds) -> None:
        try:
            self._tokens.set("gdrive", "credentials_json", creds.to_json())
        except Exception:
            pass

    def is_connected(self) -> bool:
        try:
            creds = self._load_creds()
            if not creds:
                return False
            # If we have a refresh token, the service can refresh on demand.
            return bool(getattr(creds, "valid", False) or getattr(creds, "refresh_token", None))
        except Exception:
            return False

    def connect(self) -> str | None:
        self._ensure_deps()
        secrets_path = str(get_gdrive_client_secrets_path(self._settings) or "").strip()
        if not secrets_path:
            raise RuntimeError("Google Drive requires an OAuth client secrets JSON (Settings → Cloud Sync).")
        sp = Path(secrets_path)
        if not sp.exists():
            raise FileNotFoundError(str(sp))

        flow = InstalledAppFlow.from_client_secrets_file(str(sp), SCOPES)
        try:
            creds = flow.run_local_server(port=0)
        except Exception as e:
            msg = str(e)
            # Common: app is in "Testing" and user isn't added as a test user.
            raise RuntimeError(
                "Google sign-in failed.\n\n"
                "If you see 'Access blocked' in the browser, open your Google Cloud Console:\n"
                "- OAuth consent screen → Publishing status: Testing\n"
                "- Add your account under Test users (or Publish the app)\n\n"
                f"Details: {msg}"
            ) from e
        self._creds = creds
        self._save_creds(creds)
        try:
            about = self._service().about().get(fields="user(emailAddress,displayName)").execute()
            user = (about or {}).get("user") or {}
            return user.get("emailAddress") or user.get("displayName")
        except Exception:
            return None

    def disconnect(self) -> None:
        try:
            self._tokens.clear_provider("gdrive")
        except Exception:
            pass
        self._creds = None

    def _service(self):
        self._ensure_deps()
        creds = self._load_creds()
        if not creds:
            raise RuntimeError("Not connected to Google Drive.")
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def test_connection(self) -> str:
        about = self._service().about().get(fields="user(emailAddress,displayName)").execute()
        user = (about or {}).get("user") or {}
        return f"Connected as {user.get('emailAddress') or user.get('displayName') or 'Unknown'}"

    def list_root(self, *, limit: int = 50) -> list[CloudItem]:
        return self.list_folder("root", limit=limit)

    def list_folder(self, folder_id: str = "root", *, limit: int = 200) -> list[CloudItem]:
        svc = self._service()
        fid = str(folder_id or "root").strip() or "root"
        res = (
            svc.files()
            .list(
                q=f"'{fid}' in parents and trashed=false",
                pageSize=int(limit),
                fields="files(id,name,mimeType,size,modifiedTime,md5Checksum)",
                orderBy="folder,name",
            )
            .execute()
        )
        out: list[CloudItem] = []
        for it in (res.get("files") or []):
            mime = str(it.get("mimeType") or "")
            out.append(
                CloudItem(
                    id=str(it.get("id") or ""),
                    name=str(it.get("name") or ""),
                    is_folder=(mime == "application/vnd.google-apps.folder"),
                    size=int(it.get("size") or 0) if it.get("size") is not None else None,
                    mime_type=mime or None,
                    modified_time=str(it.get("modifiedTime") or "") or None,
                    md5=str(it.get("md5Checksum") or "") or None,
                )
            )
        return out

    def ensure_folder_path(self, folder_path: str) -> str:
        """
        Ensure a nested folder path exists and return the final folder id.
        folder_path: "Fylorra Sync/Pictures/Sub"
        """
        svc = self._service()
        folder_path = str(folder_path or "").strip().strip("/").strip("\\")
        if not folder_path:
            return "root"

        parent_id = "root"
        for part in [p for p in folder_path.replace("\\", "/").split("/") if p]:
            part_esc = part.replace("'", "\\'")
            # Find existing folder
            q = (
                f"trashed=false and mimeType='application/vnd.google-apps.folder' and "
                f"name='{part_esc}' and '{parent_id}' in parents"
            )
            res = svc.files().list(q=q, pageSize=1, fields="files(id,name)").execute()
            files = res.get("files") or []
            if files:
                parent_id = str(files[0].get("id") or parent_id)
                continue

            meta: dict[str, Any] = {"name": part, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
            created = svc.files().create(body=meta, fields="id").execute()
            parent_id = str(created.get("id") or parent_id)

        return parent_id

    def upload_file(
        self,
        local_path: Path,
        *,
        remote_folder: str | None = None,
        remote_name: str | None = None,
        progress_cb=None,
    ) -> CloudItem:
        svc = self._service()
        lp = Path(local_path)
        if not lp.exists() or not lp.is_file():
            raise FileNotFoundError(str(lp))

        parents = []
        if remote_folder:
            # For now: treat remote_folder as a folder ID.
            parents = [remote_folder]

        meta: dict[str, Any] = {"name": remote_name or lp.name}
        if parents:
            meta["parents"] = parents

        media = MediaFileUpload(str(lp), resumable=True)
        req = svc.files().create(body=meta, media_body=media, fields="id,name,size,modifiedTime,md5Checksum")

        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if callable(progress_cb) and status:
                try:
                    total = int(status.total_size or 0)
                    done = int(status.resumable_progress or 0)
                    progress_cb(done, total, f"Uploading {lp.name}…")
                except Exception:
                    pass
        return CloudItem(
            id=str(resp.get("id") or ""),
            name=str(resp.get("name") or lp.name),
            is_folder=False,
            size=int(resp.get("size") or 0) if resp.get("size") is not None else None,
            modified_time=str(resp.get("modifiedTime") or "") or None,
            md5=str(resp.get("md5Checksum") or "") or None,
        )

    def update_file(self, item_id: str, local_path: Path, *, progress_cb=None) -> CloudItem:
        svc = self._service()
        lp = Path(local_path)
        if not lp.exists() or not lp.is_file():
            raise FileNotFoundError(str(lp))
        if not item_id:
            raise ValueError("item_id is required")

        media = MediaFileUpload(str(lp), resumable=True)
        req = svc.files().update(fileId=str(item_id), media_body=media, fields="id,name,size,modifiedTime,md5Checksum")  # type: ignore[arg-type]  # noqa: E501

        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if callable(progress_cb) and status:
                try:
                    total = int(status.total_size or 0)
                    done = int(status.resumable_progress or 0)
                    progress_cb(done, total, f"Uploading {lp.name}…")
                except Exception:
                    pass

        return CloudItem(
            id=str(resp.get("id") or item_id),
            name=str(resp.get("name") or lp.name),
            is_folder=False,
            size=int(resp.get("size") or 0) if resp.get("size") is not None else None,
            modified_time=str(resp.get("modifiedTime") or "") or None,
            md5=str(resp.get("md5Checksum") or "") or None,
        )

    def download_file(self, item_id: str, dest_path: Path, *, progress_cb=None) -> Path:
        svc = self._service()
        if not item_id:
            raise ValueError("item_id is required")
        dp = Path(dest_path)
        dp.parent.mkdir(parents=True, exist_ok=True)

        request = svc.files().get_media(fileId=item_id)
        fh = io.FileIO(str(dp), "wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if callable(progress_cb) and status:
                try:
                    progress_cb(int(status.resumable_progress or 0), int(status.total_size or 0), "Downloading…")
                except Exception:
                    pass
        return dp

    def create_folder(self, *, parent_id: str, name: str) -> CloudItem:
        self._ensure_deps()
        svc = self._service()
        folder_name = str(name or "").strip()
        if not folder_name:
            raise ValueError("Folder name is required.")
        parent_id = str(parent_id or "root").strip() or "root"
        meta: dict[str, Any] = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        created = svc.files().create(body=meta, fields="id,name").execute()
        return CloudItem(id=str(created.get("id") or ""), name=str(created.get("name") or folder_name), is_folder=True, size=None)

    def delete_item(self, item_id: str) -> None:
        self._ensure_deps()
        if not item_id:
            raise ValueError("item_id is required")
        svc = self._service()
        svc.files().delete(fileId=item_id).execute()

    def rename_item(self, item_id: str, new_name: str) -> CloudItem:
        self._ensure_deps()
        if not item_id:
            raise ValueError("item_id is required")
        new_name = str(new_name or "").strip()
        if not new_name:
            raise ValueError("new_name is required")
        svc = self._service()
        res = svc.files().update(fileId=item_id, body={"name": new_name}, fields="id,name,mimeType,size").execute()
        is_folder = str(res.get("mimeType") or "") == "application/vnd.google-apps.folder"
        size = int(res.get("size") or 0) if res.get("size") is not None and not is_folder else None
        return CloudItem(id=str(res.get("id") or item_id), name=str(res.get("name") or new_name), is_folder=is_folder, size=size)

    def move_item(self, item_id: str, *, dest_parent_id: str) -> CloudItem:
        """
        Move an item to a different folder (same provider).
        """
        self._ensure_deps()
        if not item_id:
            raise ValueError("item_id is required")
        dest_parent_id = str(dest_parent_id or "root").strip() or "root"
        svc = self._service()
        cur = svc.files().get(fileId=item_id, fields="parents").execute()
        parents = cur.get("parents") or []
        remove = ",".join(parents) if parents else ""
        res = svc.files().update(
            fileId=item_id,
            addParents=dest_parent_id,
            removeParents=remove or None,
            fields="id,name,mimeType,size,parents",
        ).execute()
        is_folder = str(res.get("mimeType") or "") == "application/vnd.google-apps.folder"
        size = int(res.get("size") or 0) if res.get("size") is not None and not is_folder else None
        return CloudItem(id=str(res.get("id") or item_id), name=str(res.get("name") or ""), is_folder=is_folder, size=size)

    def copy_item(self, item_id: str, *, dest_parent_id: str, new_name: str | None = None) -> CloudItem:
        """
        Copy an item into a folder.
        """
        self._ensure_deps()
        if not item_id:
            raise ValueError("item_id is required")
        dest_parent_id = str(dest_parent_id or "root").strip() or "root"
        svc = self._service()
        body: dict[str, Any] = {"parents": [dest_parent_id]}
        if new_name:
            body["name"] = str(new_name).strip()
        res = svc.files().copy(fileId=item_id, body=body, fields="id,name,mimeType,size").execute()
        is_folder = str(res.get("mimeType") or "") == "application/vnd.google-apps.folder"
        size = int(res.get("size") or 0) if res.get("size") is not None and not is_folder else None
        return CloudItem(id=str(res.get("id") or ""), name=str(res.get("name") or ""), is_folder=is_folder, size=size)
