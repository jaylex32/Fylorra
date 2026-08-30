from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CloudTokenStore:
    """
    Simple JSON token store under ~/.fylorra/cloud_tokens.json.

    Notes:
    - This is NOT a secure store; it's "good enough" for an MVP.
    - We keep it separate from settings.json to reduce accidental sharing.
    """

    def __init__(self, app_folder: Path | None = None):
        self._app_folder = app_folder or (Path.home() / ".fylorra")
        self._app_folder.mkdir(exist_ok=True)
        self._path = self._app_folder / "cloud_tokens.json"

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

    def get(self, provider: str, key: str, default=None):
        data = self._read()
        return (data.get(provider, {}) or {}).get(key, default)

    def set(self, provider: str, key: str, value) -> None:
        data = self._read()
        p = data.get(provider) or {}
        p[key] = value
        data[provider] = p
        self._write(data)

    def clear_provider(self, provider: str) -> None:
        data = self._read()
        if provider in data:
            data.pop(provider, None)
            self._write(data)

