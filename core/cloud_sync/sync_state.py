from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileStamp:
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class RemoteStamp:
    size: int
    mtime_ns: int
    token: str


@dataclass(frozen=True)
class SyncRecord:
    local: FileStamp | None
    remote: RemoteStamp | None


class CloudSyncStateStore:
    """
    Stores last-synced file stamps to avoid re-uploading unchanged files.

    File: ~/.fylorra/cloud_sync_state.json
    Layout:
      {
        "<provider>:<sync_id>": {
          "remote_base": "...",
          "files": { "rel/path.ext": {"size": 123, "mtime_ns": 999}, ... }
        }
      }
    """

    def __init__(self, app_folder: Path | None = None):
        self._app_folder = app_folder or (Path.home() / ".fylorra")
        self._app_folder.mkdir(exist_ok=True)
        self._path = self._app_folder / "cloud_sync_state.json"

    @property
    def path(self) -> Path:
        return self._path

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        try:
            self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def make_sync_id(local_root: Path) -> str:
        # Stable id based on absolute path
        p = str(Path(local_root).resolve()).lower().encode("utf-8", errors="ignore")
        return sha1(p).hexdigest()[:12]

    def load(self, *, provider: str, sync_id: str) -> tuple[str, dict[str, FileStamp]]:
        key = f"{provider}:{sync_id}"
        data = self._read().get(key) or {}
        remote_base = str(data.get("remote_base") or "")
        raw_files = data.get("files") or {}
        out: dict[str, FileStamp] = {}
        if isinstance(raw_files, dict):
            for rel, v in raw_files.items():
                try:
                    if isinstance(v, dict) and "local" in v:
                        lv = v.get("local") or {}
                        if isinstance(lv, dict):
                            out[str(rel)] = FileStamp(size=int(lv.get("size") or 0), mtime_ns=int(lv.get("mtime_ns") or 0))
                        continue
                    out[str(rel)] = FileStamp(size=int(v.get("size") or 0), mtime_ns=int(v.get("mtime_ns") or 0))
                except Exception:
                    continue
        return remote_base, out

    def save(self, *, provider: str, sync_id: str, remote_base: str, files: dict[str, FileStamp]) -> None:
        key = f"{provider}:{sync_id}"
        data = self._read()
        data[key] = {
            "remote_base": str(remote_base or ""),
            "files": {k: {"size": int(v.size), "mtime_ns": int(v.mtime_ns)} for k, v in files.items()},
        }
        self._write(data)

    def load_records(self, *, provider: str, sync_id: str) -> tuple[str, dict[str, SyncRecord]]:
        """
        Extended state for full-sync:
        - tracks last local stamp
        - tracks last remote stamp (modified/token) to detect remote-side changes and deletions.

        Backward-compatible: if the stored schema is "flat", it is treated as local-only stamps.
        """
        key = f"{provider}:{sync_id}"
        data = self._read().get(key) or {}
        remote_base = str(data.get("remote_base") or "")
        raw_files = data.get("files") or {}
        out: dict[str, SyncRecord] = {}
        if isinstance(raw_files, dict):
            for rel, v in raw_files.items():
                rel_s = str(rel)
                try:
                    if isinstance(v, dict) and ("local" in v or "remote" in v):
                        lv = v.get("local")
                        rv = v.get("remote")
                        local = None
                        remote = None
                        if isinstance(lv, dict):
                            local = FileStamp(size=int(lv.get("size") or 0), mtime_ns=int(lv.get("mtime_ns") or 0))
                        if isinstance(rv, dict):
                            remote = RemoteStamp(
                                size=int(rv.get("size") or 0),
                                mtime_ns=int(rv.get("mtime_ns") or 0),
                                token=str(rv.get("token") or ""),
                            )
                        out[rel_s] = SyncRecord(local=local, remote=remote)
                        continue

                    if isinstance(v, dict):
                        local = FileStamp(size=int(v.get("size") or 0), mtime_ns=int(v.get("mtime_ns") or 0))
                        out[rel_s] = SyncRecord(local=local, remote=None)
                except Exception:
                    continue
        return remote_base, out

    def save_records(self, *, provider: str, sync_id: str, remote_base: str, files: dict[str, SyncRecord]) -> None:
        key = f"{provider}:{sync_id}"
        data = self._read()

        def _enc_local(v: FileStamp | None):
            if v is None:
                return None
            return {"size": int(v.size), "mtime_ns": int(v.mtime_ns)}

        def _enc_remote(v: RemoteStamp | None):
            if v is None:
                return None
            return {"size": int(v.size), "mtime_ns": int(v.mtime_ns), "token": str(v.token or "")}

        data[key] = {
            "remote_base": str(remote_base or ""),
            "files": {k: {"local": _enc_local(v.local), "remote": _enc_remote(v.remote)} for k, v in files.items()},
        }
        self._write(data)
