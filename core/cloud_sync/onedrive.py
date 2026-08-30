from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from urllib.parse import quote

try:
    import msal  # type: ignore
except Exception:  # pragma: no cover
    msal = None  # type: ignore

from core.cloud_sync.base import CloudItem
from core.cloud_sync.app_credentials import get_onedrive_client_id, get_onedrive_tenant
from core.cloud_sync.token_store import CloudTokenStore


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


@dataclass
class _OneDriveAuth:
    client_id: str
    tenant: str = "common"


class OneDriveProvider:
    name = "OneDrive"

    def __init__(self, *, settings_manager, token_store: CloudTokenStore | None = None):
        self._settings = settings_manager
        self._tokens = token_store or CloudTokenStore()
        self._cache = None
        self._app = None

    def _auth(self) -> _OneDriveAuth:
        client_id = get_onedrive_client_id(self._settings)
        tenant = get_onedrive_tenant(self._settings) or "common"
        return _OneDriveAuth(client_id=client_id, tenant=tenant)

    def _ensure_msal(self) -> None:
        if msal is None:
            raise RuntimeError("msal is not installed. Add it to requirements and reinstall.")

    def _ensure_app(self):
        self._ensure_msal()
        auth = self._auth()
        if not auth.client_id:
            raise RuntimeError("OneDrive Client ID is required (Settings → Cloud Sync).")

        cache = msal.SerializableTokenCache()
        try:
            raw = self._tokens.get("onedrive", "msal_cache", "")
            if raw:
                cache.deserialize(raw)
        except Exception:
            pass

        self._cache = cache
        self._app = msal.PublicClientApplication(
            auth.client_id,
            authority=f"https://login.microsoftonline.com/{auth.tenant}",
            token_cache=cache,
        )
        return self._app

    def _persist_cache(self) -> None:
        try:
            if self._cache and self._cache.has_state_changed:
                self._tokens.set("onedrive", "msal_cache", self._cache.serialize())
        except Exception:
            pass

    def is_connected(self) -> bool:
        try:
            app = self._ensure_app()
            return bool(app.get_accounts())
        except Exception:
            return False

    def connect(self, *, status_cb=None) -> str | None:
        app = self._ensure_app()
        # MSAL/AAD treat 'openid', 'profile', 'offline_access' as reserved scopes and will add them automatically
        # when needed. Passing them explicitly can cause "reserved scope" errors.
        scopes = ["User.Read", "Files.ReadWrite.All"]

        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            # Make this actionable (common Azure app-registration misconfiguration).
            err = str(flow.get("error") or "unknown_error")
            desc = str(flow.get("error_description") or "")
            raw = f"{err}: {desc}".strip(": ")
            hint = (
                "OneDrive sign-in could not start.\n\n"
                "Most common fixes (Azure Portal → App registrations):\n"
                "1) Authentication → Advanced settings → enable 'Allow public client flows'\n"
                "2) Ensure the app is a Public client (mobile/desktop) and not a confidential 'Web' app\n"
                "3) Supported account types: pick the correct one (Personal Microsoft accounts and/or your tenant)\n\n"
                "Then try Connect again.\n\n"
                f"Details: {raw}"
            )
            raise RuntimeError(hint)

        # Caller should show flow["message"] in UI. Include explicit fields to allow robust UI parsing.
        msg = str(flow.get("message", "") or "")
        user_code = str(flow.get("user_code", "") or "")
        verify_uri = str(flow.get("verification_uri", "") or flow.get("verification_uri_complete", "") or "")
        packed = msg
        if user_code or verify_uri:
            packed = f"{msg}\n\nCode: {user_code}\nURL: {verify_uri}".strip()

        self._tokens.set("onedrive", "device_flow_message", packed)
        if callable(status_cb):
            try:
                status_cb(packed)
            except Exception:
                pass
        result = app.acquire_token_by_device_flow(flow)
        self._persist_cache()

        if not result or "access_token" not in result:
            # Provide clearer error
            err = str((result or {}).get("error") or "auth_failed")
            desc = str((result or {}).get("error_description") or "")
            raise RuntimeError(f"OneDrive auth failed: {err}\n\n{desc}".strip())

        # Clear message once connected
        self._tokens.set("onedrive", "device_flow_message", "")
        try:
            return self._get_me().get("userPrincipalName") or self._get_me().get("displayName")
        except Exception:
            return None

    def disconnect(self) -> None:
        try:
            self._tokens.clear_provider("onedrive")
        except Exception:
            pass
        self._cache = None
        self._app = None

    def _get_access_token(self) -> str:
        app = self._ensure_app()
        scopes = ["User.Read", "Files.ReadWrite.All"]
        accounts = app.get_accounts()
        if accounts:
            res = app.acquire_token_silent(scopes=scopes, account=accounts[0])
            self._persist_cache()
            if res and "access_token" in res:
                return res["access_token"]
        raise RuntimeError("Not connected to OneDrive. Click Connect in Settings → Cloud Sync.")

    def _get(self, url: str, **kwargs) -> Any:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        headers.update(kwargs.pop("headers", {}) or {})
        r = requests.get(url, headers=headers, timeout=60, **kwargs)
        r.raise_for_status()
        return r.json()

    def _put(self, url: str, data: bytes, *, content_type: str = "application/octet-stream") -> Any:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": content_type}
        r = requests.put(url, headers=headers, data=data, timeout=300)
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, json_data: dict) -> Any:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=json_data, timeout=60)
        r.raise_for_status()
        return r.json()

    def _patch(self, url: str, json_data: dict) -> Any:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.patch(url, headers=headers, json=json_data, timeout=60)
        r.raise_for_status()
        # PATCH responses are usually JSON
        try:
            return r.json()
        except Exception:
            return {}

    def _delete(self, url: str) -> None:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.delete(url, headers=headers, timeout=60)
        # DELETE can return 204 No Content
        if r.status_code not in (200, 202, 204):
            r.raise_for_status()

    def _get_me(self) -> dict:
        return self._get(f"{GRAPH_BASE}/me")

    def test_connection(self) -> str:
        me = self._get_me()
        return f"Connected as {me.get('displayName') or me.get('userPrincipalName') or 'Unknown'}"

    def list_root(self, *, limit: int = 50) -> list[CloudItem]:
        data = self._get(f"{GRAPH_BASE}/me/drive/root/children?$top={int(limit)}")
        out: list[CloudItem] = []
        for it in (data.get("value") or []):
            out.append(
                CloudItem(
                    id=str(it.get("id") or ""),
                    name=str(it.get("name") or ""),
                    is_folder=bool(it.get("folder")),
                    size=int(it.get("size") or 0) if it.get("size") is not None else None,
                    path=(it.get("parentReference") or {}).get("path"),
                    modified_time=str(it.get("lastModifiedDateTime") or "") or None,
                    etag=str(it.get("eTag") or "") or None,
                )
            )
        return out

    def list_folder(self, folder_path: str | None = None, *, limit: int = 200) -> list[CloudItem]:
        """
        List children of a folder by path (under drive root).
        folder_path:
          - None / ""  -> root
          - "Fylorra Sync/Pictures" -> that folder
        """
        p = str(folder_path or "").strip().strip("/").strip("\\")
        if not p:
            url = f"{GRAPH_BASE}/me/drive/root/children?$top={int(limit)}"
        else:
            # Must URL-encode the path segment.
            seg = quote("/" + p, safe="/")
            url = f"{GRAPH_BASE}/me/drive/root:{seg}:/children?$top={int(limit)}"
        data = self._get(url)
        out: list[CloudItem] = []
        for it in (data.get("value") or []):
            out.append(
                CloudItem(
                    id=str(it.get("id") or ""),
                    name=str(it.get("name") or ""),
                    is_folder=bool(it.get("folder")),
                    size=int(it.get("size") or 0) if it.get("size") is not None else None,
                    path=(it.get("parentReference") or {}).get("path"),
                    modified_time=str(it.get("lastModifiedDateTime") or "") or None,
                    etag=str(it.get("eTag") or "") or None,
                )
            )
        return out

    def ensure_folder_path(self, folder_path: str) -> None:
        """
        Ensure a folder path exists under the drive root, creating folders as needed.
        folder_path: e.g. "Fylorra Sync/Pictures/Sub"
        """
        folder_path = str(folder_path or "").strip().strip("/").strip("\\")
        if not folder_path:
            return

        parts = [p for p in folder_path.replace("\\", "/").split("/") if p]
        cur_path = ""
        for part in parts:
            cur_path = f"{cur_path}/{part}" if cur_path else part
            try:
                # Check existence by path
                self._get(f"{GRAPH_BASE}/me/drive/root:/{cur_path}")
                continue
            except Exception:
                pass

            # Create under parent
            parent_path = str(Path(cur_path).parent).replace("\\", "/")
            if parent_path == ".":
                parent_path = ""
            if parent_path:
                url = f"{GRAPH_BASE}/me/drive/root:/{parent_path}:/children"
            else:
                url = f"{GRAPH_BASE}/me/drive/root/children"

            self._post(
                url,
                {
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "fail",
                },
            )

    def upload_file(
        self,
        local_path: Path,
        *,
        remote_folder: str | None = None,
        remote_name: str | None = None,
        progress_cb=None,
    ) -> CloudItem:
        lp = Path(local_path)
        if not lp.exists() or not lp.is_file():
            raise FileNotFoundError(str(lp))

        name = remote_name or lp.name
        folder = (remote_folder or "").strip().strip("/")
        if folder:
            remote_path = f"/{folder}/{name}"
        else:
            remote_path = f"/{name}"

        data = lp.read_bytes()
        if callable(progress_cb):
            try:
                progress_cb(0, len(data), f"Uploading {lp.name}…")
            except Exception:
                pass
        res = self._put(f"{GRAPH_BASE}/me/drive/root:{remote_path}:/content", data)
        if callable(progress_cb):
            try:
                progress_cb(len(data), len(data), "Done")
            except Exception:
                pass
        return CloudItem(
            id=str(res.get("id") or ""),
            name=str(res.get("name") or name),
            is_folder=False,
            size=int(res.get("size") or 0) if res.get("size") is not None else None,
            path=(res.get("parentReference") or {}).get("path"),
            modified_time=str(res.get("lastModifiedDateTime") or "") or None,
            etag=str(res.get("eTag") or "") or None,
        )

    def download_file(self, item_id: str, dest_path: Path, *, progress_cb=None) -> Path:
        if not item_id:
            raise ValueError("item_id is required")
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
        r = requests.get(url, headers=headers, stream=True, timeout=300)
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        dp = Path(dest_path)
        dp.parent.mkdir(parents=True, exist_ok=True)
        done = 0
        with open(dp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if callable(progress_cb):
                    try:
                        progress_cb(done, total, f"Downloading… {done}/{total}" if total else "Downloading…")
                    except Exception:
                        pass
        return dp

    def create_folder(self, *, parent_path: str | None, name: str) -> CloudItem:
        """
        Create a folder under the given OneDrive path (under drive root).

        parent_path:
          - ""/None means root
          - otherwise a path like "Fylorra Sync/Pictures"
        """
        folder_name = str(name or "").strip()
        if not folder_name:
            raise ValueError("Folder name is required.")

        parent_path = str(parent_path or "").strip().strip("/").strip("\\")
        if parent_path:
            # Ensure parent exists first (creates intermediate folders).
            self.ensure_folder_path(parent_path)
            url = f"{GRAPH_BASE}/me/drive/root:/{parent_path}:/children"
        else:
            url = f"{GRAPH_BASE}/me/drive/root/children"

        res = self._post(
            url,
            {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            },
        )
        return CloudItem(
            id=str(res.get("id") or ""),
            name=str(res.get("name") or folder_name),
            is_folder=True,
            size=int(res.get("size") or 0) if res.get("size") is not None else None,
            path=(res.get("parentReference") or {}).get("path"),
            modified_time=str(res.get("lastModifiedDateTime") or "") or None,
            etag=str(res.get("eTag") or "") or None,
        )

    def delete_item(self, item_id: str) -> None:
        if not item_id:
            raise ValueError("item_id is required")
        self._delete(f"{GRAPH_BASE}/me/drive/items/{item_id}")

    def rename_item(self, item_id: str, new_name: str) -> CloudItem:
        if not item_id:
            raise ValueError("item_id is required")
        new_name = str(new_name or "").strip()
        if not new_name:
            raise ValueError("new_name is required")
        res = self._patch(f"{GRAPH_BASE}/me/drive/items/{item_id}", {"name": new_name})
        return CloudItem(
            id=str(res.get("id") or item_id),
            name=str(res.get("name") or new_name),
            is_folder=bool(res.get("folder") is not None),
            size=int(res.get("size") or 0) if res.get("size") is not None else None,
            path=(res.get("parentReference") or {}).get("path"),
            modified_time=str(res.get("lastModifiedDateTime") or "") or None,
            etag=str(res.get("eTag") or "") or None,
        )

    def move_item_to_path(self, item_id: str, *, dest_parent_path: str | None) -> CloudItem:
        """
        Move an item to a destination folder specified by path under root.
        """
        if not item_id:
            raise ValueError("item_id is required")
        dest_parent_path = str(dest_parent_path or "").strip().strip("/").strip("\\")
        if dest_parent_path:
            self.ensure_folder_path(dest_parent_path)
            dest = self._get(f"{GRAPH_BASE}/me/drive/root:/{dest_parent_path}")
            dest_id = str(dest.get("id") or "").strip()
            if not dest_id:
                raise RuntimeError("Failed to resolve destination folder id.")
        else:
            dest_id = "root"

        body: dict[str, Any] = {"parentReference": {"id": dest_id}}
        res = self._patch(f"{GRAPH_BASE}/me/drive/items/{item_id}", body)
        return CloudItem(
            id=str(res.get("id") or item_id),
            name=str(res.get("name") or ""),
            is_folder=bool(res.get("folder") is not None),
            size=int(res.get("size") or 0) if res.get("size") is not None else None,
            path=(res.get("parentReference") or {}).get("path"),
            modified_time=str(res.get("lastModifiedDateTime") or "") or None,
            etag=str(res.get("eTag") or "") or None,
        )

    def copy_item_to_path(self, item_id: str, *, dest_parent_path: str | None, new_name: str | None = None) -> None:
        """
        Copy an item to a destination folder path under root. OneDrive returns an async operation; we fire and forget.
        """
        if not item_id:
            raise ValueError("item_id is required")
        dest_parent_path = str(dest_parent_path or "").strip().strip("/").strip("\\")
        dest_id = None
        if dest_parent_path:
            self.ensure_folder_path(dest_parent_path)
            dest = self._get(f"{GRAPH_BASE}/me/drive/root:/{dest_parent_path}")
            dest_id = str(dest.get("id") or "").strip() or None
        body: dict[str, Any] = {}
        if dest_id:
            body["parentReference"] = {"id": dest_id}
        if new_name:
            body["name"] = str(new_name).strip()
        # /copy returns 202 Accepted (no JSON body). Fire-and-forget.
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{GRAPH_BASE}/me/drive/items/{item_id}/copy", headers=headers, json=(body or {}), timeout=60)
        if r.status_code not in (200, 202, 204):
            r.raise_for_status()
