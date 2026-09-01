"""Direct device-to-device file transfer for Fylorra.

The transfer service intentionally uses only Python's standard library so it
can run on Windows, macOS, and Linux without external daemons. It provides a
small authenticated HTTP receiver plus UDP LAN discovery.
"""

from __future__ import annotations

import http.client
import json
import mimetypes
import os
import platform
import secrets
import socket
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable

from core.branding import APP_NAME


TRANSFER_PROTOCOL = "fylorra-transfer-v1"
DEFAULT_TRANSFER_PORT = 47832
DEFAULT_DISCOVERY_PORT = 47833
# urllib feeds an upload through http.client in 8KB blocks, which caps a send at
# roughly 2.5Gbps before the network is even involved. 256KB measured fastest.
UPLOAD_BLOCK_SIZE = 256 * 1024
# How long a file must look unchanged before it is considered safe to send.
STABLE_WINDOW_SECONDS = 0.35
# Closes keep-alive connections that go idle so they do not hold a thread.
RECEIVE_IDLE_TIMEOUT = 180.0
# On a rejection, read at most this much of the body first so a small upload can
# finish writing and still read the reply instead of seeing a socket reset.
REJECT_DRAIN_BYTES = 1024 * 1024
ACTIVE_DOWNLOAD_SUFFIXES = {
    ".crdownload",
    ".download",
    ".part",
    ".partial",
    ".opdownload",
    ".tmp",
}


@dataclass(frozen=True)
class TransferFile:
    path: Path
    relative_name: str
    size: int


def _now() -> float:
    return time.time()


def _safe_device_name() -> str:
    name = platform.node().strip() or socket.gethostname().strip() or "This device"
    return name[:80]


def _default_inbox_dir() -> str:
    return str(Path.home() / f"{APP_NAME} Transfers")


def _format_bytes(num: int | float) -> str:
    try:
        n = float(num)
    except Exception:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(n) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def _sanitize_relative_path(raw: str) -> Path:
    cleaned = str(raw or "").replace("\\", "/").strip().strip("/")
    parts: list[str] = []
    for part in cleaned.split("/"):
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        part = "".join(ch for ch in part if ch not in '<>:"|?*')
        part = part.rstrip(" .")
        if part:
            parts.append(part[:180])
    if not parts:
        parts = ["received_file"]
    return Path(*parts)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 10_000):
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"


def _is_active_download_artifact(path: Path) -> bool:
    name = path.name.lower()
    suffix = path.suffix.lower()
    return suffix in ACTIVE_DOWNLOAD_SUFFIXES or name.endswith(".crdownload") or name.endswith(".download")


def _file_is_stable(path: Path, wait_seconds: float = 0.35) -> bool:
    try:
        first = path.stat()
        time.sleep(max(0.05, float(wait_seconds)))
        second = path.stat()
        return first.st_size == second.st_size and int(first.st_mtime_ns) == int(second.st_mtime_ns)
    except Exception:
        return False


def _local_ip_candidates() -> list[str]:
    ips: set[str] = {"127.0.0.1"}
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM):
            ip = str(info[4][0])
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = str(sock.getsockname()[0])
            if ip:
                ips.add(ip)
        finally:
            sock.close()
    except Exception:
        pass
    return sorted(ips, key=lambda x: (x.startswith("127."), x))


class _TransferRequestHandler(BaseHTTPRequestHandler):
    server_version = "FylorraTransfer/1.0"
    # HTTP/1.1 keeps the connection open between uploads, so a run of files no
    # longer pays a TCP handshake and a fresh slow-start ramp for every file.
    protocol_version = "HTTP/1.1"
    timeout = RECEIVE_IDLE_TIMEOUT

    def log_message(self, _format: str, *args: Any) -> None:
        return

    @property
    def transfer_service(self) -> "DeviceTransferService":
        return self.server.transfer_service  # type: ignore[attr-defined]

    def _reject(self, status: HTTPStatus, error: str, *, drain: bool = True) -> None:
        """Reject an upload and close, since the rest of the body is never read.

        A little of the body is read first: without that the sender is still
        writing when the socket closes and it reports a connection reset instead
        of the actual reason, which is useless when the access code is simply wrong.
        """
        if drain:
            try:
                remaining = min(int(self.headers.get("Content-Length") or 0), REJECT_DRAIN_BYTES)
            except Exception:
                remaining = 0
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        self.close_connection = True
        self._send_json(status, {"ok": False, "error": error})

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token_ok(self) -> bool:
        expected = str(self.transfer_service.config.get("access_code") or "")
        supplied = str(self.headers.get("X-Fylorra-Token") or "")
        if not supplied:
            parsed = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(parsed.query)
            supplied = str((q.get("token") or [""])[0])
        return bool(expected) and secrets.compare_digest(supplied, expected)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/v1/ping":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Unknown endpoint"})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "app": APP_NAME,
                "protocol": TRANSFER_PROTOCOL,
                "device_id": self.transfer_service.device_id,
                "device_name": self.transfer_service.device_name,
                "platform": platform.system(),
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/v1/upload":
            self._reject(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        if not self._token_ok():
            self._reject(HTTPStatus.UNAUTHORIZED, "Invalid access code")
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except Exception:
            length = 0
        if length <= 0:
            self._reject(HTTPStatus.BAD_REQUEST, "Empty upload")
            return

        max_bytes = int(self.transfer_service.config.get("max_file_bytes") or 0)
        if max_bytes > 0 and length > max_bytes:
            self._reject(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "File is larger than receiver limit")
            return

        rel_header = self.headers.get("X-Fylorra-Relative-Path") or self.headers.get("X-Fylorra-Filename") or ""
        rel = _sanitize_relative_path(urllib.parse.unquote(rel_header))
        try:
            final_path = self.transfer_service.prepare_receive_path(rel)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = final_path.with_name(f".{final_path.name}.fylorra-{uuid.uuid4().hex}.part")
            written = 0
            with open(temp_path, "wb") as out:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            if written != length:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                self._reject(HTTPStatus.BAD_REQUEST, "Upload ended before all bytes were received", drain=False)
                return
            os.replace(temp_path, final_path)
            self.transfer_service.record_activity(
                "received",
                f"Received {final_path.name} ({_format_bytes(written)})",
                path=str(final_path),
                bytes=written,
                peer=self.client_address[0] if self.client_address else "",
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "path": str(final_path), "bytes": written})
        except Exception as e:
            self.transfer_service.record_activity("error", f"Receive failed: {e}")
            self._reject(HTTPStatus.INTERNAL_SERVER_ERROR, str(e), drain=False)


class _TransferHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler, transfer_service: "DeviceTransferService"):
        super().__init__(server_address, handler)
        self.transfer_service = transfer_service


class _UploadSession:
    """Sends files over a single reused HTTP connection.

    The previous implementation handed each file to urllib, which opened a fresh
    connection every time. On a fast link that meant paying a TCP handshake and a
    new slow-start ramp per file, so short transfers finished before the window
    ever opened up. Holding one warm connection and reading the file in larger
    blocks removes both costs. Falls back cleanly when the receiver is an older
    build that closes after each response.
    """

    UPLOAD_PATH = "/api/v1/upload"

    def __init__(self, *, host: str, port: int, timeout: float = 60.0, blocksize: int = UPLOAD_BLOCK_SIZE):
        self.host = str(host or "").strip()
        self.port = int(port or 0)
        self.timeout = float(timeout)
        self.blocksize = int(blocksize)
        self._conn: http.client.HTTPConnection | None = None

    def _connection(self) -> tuple[http.client.HTTPConnection, bool]:
        """Return the live connection plus whether it was carried over."""
        if self._conn is not None:
            return self._conn, True
        self._conn = http.client.HTTPConnection(
            self.host, self.port, timeout=self.timeout, blocksize=self.blocksize
        )
        return self._conn, False

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def upload(self, *, access_code: str, item: TransferFile) -> None:
        quoted = urllib.parse.quote(item.relative_name.replace("\\", "/"))
        headers = {
            "X-Fylorra-Token": access_code,
            "X-Fylorra-Relative-Path": quoted,
            "Content-Length": str(item.size),
            "Content-Type": mimetypes.guess_type(item.path.name)[0] or "application/octet-stream",
        }

        retried = False
        while True:
            conn, reused = self._connection()
            try:
                with open(item.path, "rb") as fh:
                    conn.request("POST", self.UPLOAD_PATH, body=fh, headers=headers)
                    resp = conn.getresponse()
                    raw = resp.read()
                    status = int(resp.status)
                    will_close = bool(resp.will_close)
            except (http.client.HTTPException, OSError) as e:
                self.close()
                # A carried-over connection can be dropped by the peer while idle.
                # That fails before any body is sent, so retrying once is safe;
                # a freshly opened connection failing is a real error.
                if reused and not retried:
                    retried = True
                    continue
                raise RuntimeError(str(e)) from e

            if will_close:
                # Older receivers answer with HTTP/1.0 and hang up after each file.
                self.close()

            try:
                payload = json.loads(raw.decode("utf-8", errors="ignore"))
            except Exception:
                payload = {}
            if status >= 300 or not bool(payload.get("ok", True)):
                raise RuntimeError(str(payload.get("error") or f"HTTP {status}"))
            return


class DeviceTransferService:
    """Authenticated direct transfer service with optional LAN discovery."""

    def __init__(self, settings_manager: Any):
        self.settings_manager = settings_manager
        self.config = self._load_config()
        self.device_id = str(self.config.get("device_id") or uuid.uuid4())
        self.device_name = str(self.config.get("device_name") or _safe_device_name())
        self.config["device_id"] = self.device_id
        self.config["device_name"] = self.device_name
        self._save_config()

        self._server: _TransferHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._discovery_socket: socket.socket | None = None
        self._discovery_thread: threading.Thread | None = None
        self._announce_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._peers: dict[str, dict[str, Any]] = {}
        self._activity: list[dict[str, Any]] = []

    def _load_config(self) -> dict[str, Any]:
        saved = {}
        try:
            saved = self.settings_manager.get_setting("device_transfer", {}) or {}
        except Exception:
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        defaults = {
            "enabled": False,
            "device_id": str(uuid.uuid4()),
            "device_name": _safe_device_name(),
            "inbox_dir": _default_inbox_dir(),
            "port": DEFAULT_TRANSFER_PORT,
            "discovery_port": DEFAULT_DISCOVERY_PORT,
            "access_code": secrets.token_urlsafe(18),
            "skip_active_downloads": True,
            "require_stable_files": True,
            "max_file_bytes": 0,
        }
        defaults.update(saved)
        return defaults

    def _save_config(self) -> None:
        try:
            self.settings_manager.set_setting("device_transfer", dict(self.config))
        except Exception:
            pass

    def update_config(self, **changes: Any) -> dict[str, Any]:
        with self._lock:
            for key, value in changes.items():
                if key in {"device_name", "inbox_dir"}:
                    self.config[key] = str(value or "").strip()
                elif key in {"port", "discovery_port", "max_file_bytes"}:
                    self.config[key] = int(value or 0)
                elif key in {"enabled", "skip_active_downloads", "require_stable_files"}:
                    self.config[key] = bool(value)
                elif key == "access_code":
                    self.config[key] = str(value or "").strip()
            self.device_name = str(self.config.get("device_name") or self.device_name)
            self._save_config()
            return dict(self.config)

    def rotate_access_code(self) -> str:
        code = secrets.token_urlsafe(18)
        self.update_config(access_code=code)
        self.record_activity("security", "Access code changed.")
        return code

    def start(self) -> None:
        with self._lock:
            if self._server is not None:
                return
            inbox = Path(str(self.config.get("inbox_dir") or _default_inbox_dir())).expanduser()
            inbox.mkdir(parents=True, exist_ok=True)
            self.config["inbox_dir"] = str(inbox)

            port = int(self.config.get("port") or DEFAULT_TRANSFER_PORT)
            server = _TransferHTTPServer(("0.0.0.0", port), _TransferRequestHandler, self)
            self._server = server
            self.config["port"] = int(server.server_address[1])
            self.config["enabled"] = True
            self._save_config()
            self._stop_event.clear()
            self._server_thread = threading.Thread(target=server.serve_forever, name="FylorraTransferHTTP", daemon=True)
            self._server_thread.start()
            self._start_discovery_locked()
            self.record_activity("service", f"Receiving is on at port {self.config['port']}.")

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            sock = self._discovery_socket
            self._discovery_socket = None
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            server = self._server
            self._server = None
            if server is not None:
                try:
                    server.shutdown()
                    server.server_close()
                except Exception:
                    pass
            self.config["enabled"] = False
            self._save_config()
            self.record_activity("service", "Receiving is off.")

    def _start_discovery_locked(self) -> None:
        if self._discovery_thread and self._discovery_thread.is_alive():
            return
        disc_port = int(self.config.get("discovery_port") or DEFAULT_DISCOVERY_PORT)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(("", disc_port))
        except OSError:
            sock.close()
            self.record_activity("warning", f"LAN discovery unavailable on port {disc_port}. Direct address still works.")
            return
        self._discovery_socket = sock
        self._discovery_thread = threading.Thread(target=self._discovery_loop, name="FylorraTransferDiscovery", daemon=True)
        self._announce_thread = threading.Thread(target=self._announce_loop, name="FylorraTransferAnnounce", daemon=True)
        self._discovery_thread.start()
        self._announce_thread.start()

    def _discovery_loop(self) -> None:
        while not self._stop_event.is_set():
            sock = self._discovery_socket
            if sock is None:
                return
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                payload = json.loads(data.decode("utf-8", errors="ignore"))
            except Exception:
                continue
            if payload.get("protocol") != TRANSFER_PROTOCOL:
                continue
            peer_id = str(payload.get("device_id") or "")
            if not peer_id or peer_id == self.device_id:
                continue
            peer = {
                "device_id": peer_id,
                "device_name": str(payload.get("device_name") or "Unknown device"),
                "host": str(addr[0]),
                "port": int(payload.get("port") or 0),
                "platform": str(payload.get("platform") or ""),
                "last_seen": _now(),
            }
            if peer["port"] <= 0:
                continue
            with self._lock:
                self._peers[peer_id] = peer

    def _announce_loop(self) -> None:
        disc_port = int(self.config.get("discovery_port") or DEFAULT_DISCOVERY_PORT)
        while not self._stop_event.is_set():
            try:
                payload = {
                    "app": APP_NAME,
                    "protocol": TRANSFER_PROTOCOL,
                    "device_id": self.device_id,
                    "device_name": self.device_name,
                    "platform": platform.system(),
                    "port": int(self.config.get("port") or DEFAULT_TRANSFER_PORT),
                    "time": int(_now()),
                }
                data = json.dumps(payload).encode("utf-8")
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.sendto(data, ("255.255.255.255", disc_port))
                finally:
                    sock.close()
            except Exception:
                pass
            self._stop_event.wait(3.0)

    def status(self) -> dict[str, Any]:
        with self._lock:
            port = int(self.config.get("port") or DEFAULT_TRANSFER_PORT)
            return {
                "running": self._server is not None,
                "device_id": self.device_id,
                "device_name": self.device_name,
                "inbox_dir": str(self.config.get("inbox_dir") or _default_inbox_dir()),
                "port": port,
                "discovery_port": int(self.config.get("discovery_port") or DEFAULT_DISCOVERY_PORT),
                "access_code": str(self.config.get("access_code") or ""),
                "local_addresses": [f"{ip}:{port}" for ip in _local_ip_candidates()],
                "skip_active_downloads": bool(self.config.get("skip_active_downloads", True)),
                "require_stable_files": bool(self.config.get("require_stable_files", True)),
            }

    def peers(self, max_age_seconds: int = 45) -> list[dict[str, Any]]:
        cutoff = _now() - max(5, int(max_age_seconds))
        with self._lock:
            stale = [pid for pid, peer in self._peers.items() if float(peer.get("last_seen") or 0) < cutoff]
            for pid in stale:
                self._peers.pop(pid, None)
            return sorted((dict(p) for p in self._peers.values()), key=lambda p: str(p.get("device_name") or "").lower())

    def activity(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._activity)

    def record_activity(self, kind: str, message: str, **extra: Any) -> None:
        entry = {"time": _now(), "kind": str(kind), "message": str(message)}
        entry.update(extra)
        with self._lock:
            self._activity.insert(0, entry)
            del self._activity[200:]

    def prepare_receive_path(self, relative_path: Path) -> Path:
        inbox = Path(str(self.config.get("inbox_dir") or _default_inbox_dir())).expanduser().resolve()
        target = (inbox / relative_path).resolve()
        try:
            target.relative_to(inbox)
        except ValueError:
            raise ValueError("Invalid destination path")
        return _unique_path(target)

    def iter_transfer_files(self, paths: Iterable[str | Path]) -> list[TransferFile]:
        files: list[TransferFile] = []
        for raw in paths:
            p = Path(raw).expanduser()
            if not p.exists():
                continue
            if p.is_file():
                files.append(TransferFile(path=p, relative_name=p.name, size=p.stat().st_size))
                continue
            if p.is_dir():
                base = p.parent
                for child in p.rglob("*"):
                    if child.is_file():
                        rel = str(child.relative_to(base)).replace("\\", "/")
                        files.append(TransferFile(path=child, relative_name=rel, size=child.stat().st_size))
        return files

    def send_paths(
        self,
        *,
        host: str,
        port: int,
        access_code: str,
        paths: Iterable[str | Path],
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        host = str(host or "").strip()
        if not host:
            raise ValueError("Enter the receiving device address.")
        port = int(port or 0)
        if port <= 0:
            raise ValueError("Enter the receiving device port.")
        token = str(access_code or "").strip()
        if not token:
            raise ValueError("Enter the receiving device access code.")

        files = self.iter_transfer_files(paths)
        if not files:
            raise ValueError("Choose at least one existing file or folder.")

        sent = 0
        skipped = 0
        failed: list[str] = []
        total = len(files)

        skip_active = bool(self.config.get("skip_active_downloads", True))
        require_stable = bool(self.config.get("require_stable_files", True))
        # Stat every file up front. The stability window then elapses while earlier
        # files are already on the wire, instead of costing a fresh wait per file.
        stable_snapshot = self._stat_snapshot(files) if require_stable else {}

        # One connection for the whole run: no per-file handshake or slow-start restart.
        session = _UploadSession(host=host, port=port)
        try:
            for index, item in enumerate(files, start=1):
                if skip_active and _is_active_download_artifact(item.path):
                    skipped += 1
                    if progress:
                        progress({"event": "skipped", "file": str(item.path), "index": index, "total": total, "reason": "active download file"})
                    continue
                if require_stable and not self._file_is_stable_since(item.path, stable_snapshot):
                    skipped += 1
                    if progress:
                        progress({"event": "skipped", "file": str(item.path), "index": index, "total": total, "reason": "file changed while preparing"})
                    continue
                if progress:
                    progress({"event": "sending", "file": str(item.path), "index": index, "total": total, "bytes": item.size})
                try:
                    self._send_one(host=host, port=port, access_code=token, item=item, session=session)
                    sent += 1
                    self.record_activity("sent", f"Sent {item.path.name} to {host}:{port} ({_format_bytes(item.size)})", path=str(item.path), bytes=item.size)
                    if progress:
                        progress({"event": "sent", "file": str(item.path), "index": index, "total": total})
                except Exception as e:
                    failed.append(f"{item.path}: {e}")
                    self.record_activity("error", f"Send failed for {item.path.name}: {e}", path=str(item.path))
                    if progress:
                        progress({"event": "failed", "file": str(item.path), "index": index, "total": total, "error": str(e)})
        finally:
            session.close()

        return {"sent": sent, "skipped": skipped, "failed": failed, "total": total}

    def _stat_snapshot(self, files: Iterable[TransferFile]) -> dict[str, tuple[int, int, float]]:
        """Record size/mtime for every file so the stability wait can be shared."""
        taken_at = _now()
        snapshot: dict[str, tuple[int, int, float]] = {}
        for item in files:
            try:
                st = item.path.stat()
            except Exception:
                continue
            snapshot[str(item.path)] = (st.st_size, int(st.st_mtime_ns), taken_at)
        return snapshot

    def _file_is_stable_since(
        self,
        path: Path,
        snapshot: dict[str, tuple[int, int, float]],
        wait_seconds: float = STABLE_WINDOW_SECONDS,
    ) -> bool:
        """Same check as _file_is_stable, but reusing the up-front stat.

        The file still has to look identical across a window of at least
        `wait_seconds` ending right now, so a file being written is caught exactly
        as before. Only the first file can still have to wait.
        """
        first = snapshot.get(str(path))
        if first is None:
            return _file_is_stable(path, wait_seconds)
        size, mtime_ns, taken_at = first
        remaining = float(wait_seconds) - (_now() - taken_at)
        if remaining > 0:
            time.sleep(remaining)
        try:
            second = path.stat()
        except Exception:
            return False
        return second.st_size == size and int(second.st_mtime_ns) == mtime_ns

    def _send_one(
        self,
        *,
        host: str,
        port: int,
        access_code: str,
        item: TransferFile,
        session: "_UploadSession | None" = None,
    ) -> None:
        """Upload one file, reusing `session`'s connection when one is supplied."""
        own_session = session is None
        active = session if session is not None else _UploadSession(host=host, port=port)
        try:
            active.upload(access_code=access_code, item=item)
        finally:
            if own_session:
                active.close()
