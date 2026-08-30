"""
Fylorra - LibreOffice Downloader
Downloads the official LibreOffice installer with progress (best-effort).

This is intended to improve UX: users can download from inside the app and then
run the installer.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.branding import USER_AGENT


STABLE_INDEX_URL = "https://download.documentfoundation.org/libreoffice/stable/"


@dataclass(frozen=True)
class DownloadResult:
    ok: bool
    message: str
    path: str | None = None


def _parse_versions(html: str) -> list[str]:
    # Directory listing typically contains: href="25.2.1/"
    found = re.findall(r'href="(\d+\.\d+\.\d+)/"', html or "")
    return list(dict.fromkeys(found))


def _version_key(v: str) -> tuple[int, int, int]:
    parts = (v or "0.0.0").split(".")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return (0, 0, 0)


def get_latest_stable_version(timeout_s: int = 15) -> str | None:
    try:
        req = urllib.request.Request(STABLE_INDEX_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        versions = _parse_versions(html)
        if not versions:
            return None
        versions.sort(key=_version_key, reverse=True)
        return versions[0]
    except Exception:
        return None


def build_download_url(version: str, *, platform: str, arch: str) -> tuple[str, str] | None:
    """
    Returns (url, filename) for the official installer, or None if unsupported.
    """
    version = (version or "").strip()
    if not version:
        return None
    platform = (platform or "").strip().lower()
    arch = (arch or "").strip().lower()

    base = f"{STABLE_INDEX_URL}{version}/"
    if platform == "windows":
        if arch in {"x64", "x86_64", "amd64"}:
            filename = f"LibreOffice_{version}_Win_x86-64.msi"
            url = f"{base}win/x86_64/{filename}"
            return url, filename
        if arch in {"x86", "win32"}:
            filename = f"LibreOffice_{version}_Win_x86.msi"
            url = f"{base}win/x86/{filename}"
            return url, filename
        return None

    if platform == "macos":
        filename = f"LibreOffice_{version}_MacOS_x86-64.dmg"
        url = f"{base}mac/x86_64/{filename}"
        return url, filename

    if platform == "linux":
        # We don't know distro; offer a tarball-ish package would be better but LO doesn't provide a universal installer.
        return None

    return None


def download_file(
    url: str,
    dest_path: Path,
    *,
    cancel_event: threading.Event | None = None,
    progress_cb=None,  # callable(frac:float, downloaded:int, total:int, speed_bps:float) -> None
    timeout_s: int = 30,
) -> DownloadResult:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    try:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            start_t = time.time()
            last_t = start_t
            last_bytes = 0

            with tmp_path.open("wb") as out:
                while True:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("Cancelled.")
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if progress_cb and (now - last_t >= 0.2 or (total and downloaded >= total)):
                        dt = max(0.001, now - last_t)
                        speed = (downloaded - last_bytes) / dt
                        last_t = now
                        last_bytes = downloaded
                        frac = (float(downloaded) / float(total)) if total else 0.0
                        try:
                            progress_cb(max(0.0, min(1.0, frac)), downloaded, total, float(speed))
                        except Exception:
                            pass

        tmp_path.replace(dest_path)
        return DownloadResult(ok=True, message="Downloaded.", path=str(dest_path))
    except Exception as e:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return DownloadResult(ok=False, message=str(e))
