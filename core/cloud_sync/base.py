from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CloudItem:
    id: str
    name: str
    is_folder: bool
    size: int | None = None
    path: str | None = None
    mime_type: str | None = None
    modified_time: str | None = None
    etag: str | None = None
    md5: str | None = None


class CloudProvider(Protocol):
    name: str

    def is_connected(self) -> bool: ...

    def connect(self) -> str | None: ...

    def disconnect(self) -> None: ...

    def test_connection(self) -> str: ...

    def list_root(self, *, limit: int = 50) -> list[CloudItem]: ...

    def upload_file(
        self,
        local_path: Path,
        *,
        remote_folder: str | None = None,
        remote_name: str | None = None,
        progress_cb=None,
    ) -> CloudItem: ...

    def download_file(
        self,
        item_id: str,
        dest_path: Path,
        *,
        progress_cb=None,
    ) -> Path: ...
