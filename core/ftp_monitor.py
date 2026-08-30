"""FTP Monitor - Monitors FTP servers for file changes"""

import ftplib
import threading
import time
from typing import Dict, List, Callable, Optional
from datetime import datetime
from pathlib import Path


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    def connect(self, host="", port=0, timeout=-999, source_address=None):  # noqa: N802
        if port == 0:
            port = 990
        super(ftplib.FTP, self).connect(host, port, timeout, source_address)
        self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)
        self.af = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        return self.welcome


class FTPMonitor:
    """Monitors FTP server directories for changes"""

    def __init__(self, monitor_id: str, host: str, username: str, password: str,
                 remote_path: str, port: int = 21, use_tls: bool = False,
                 poll_interval: int = 30, event_callback: Callable = None,
                 local_sync_dir: Optional[str] = None,
                 download_on_created: bool = True,
                 download_on_modified: bool = True,
                 delete_local_on_deleted: bool = False,
                 overwrite_local: bool = False,
                 allowed_extensions: Optional[List[str]] = None,
                 passive_mode: bool = True,
                 tls_implicit: bool = False,
                 encoding: str = "utf-8",
                 two_way_sync: bool = False,
                 sync_subfolders: bool = False):
        self.monitor_id = monitor_id
        self.host = host
        self.username = username
        self.password = password
        self.remote_path = remote_path
        self.port = port
        self.use_tls = use_tls
        self.tls_implicit = bool(tls_implicit)
        self.passive_mode = bool(passive_mode)
        self.encoding = (encoding or "").strip() or "utf-8"
        self.two_way_sync = bool(two_way_sync)
        self.sync_subfolders = bool(sync_subfolders)
        self.poll_interval = poll_interval
        self.event_callback = event_callback
        self.local_sync_dir = local_sync_dir
        self.download_on_created = bool(download_on_created)
        self.download_on_modified = bool(download_on_modified)
        self.delete_local_on_deleted = bool(delete_local_on_deleted)
        self.overwrite_local = bool(overwrite_local)
        self.allowed_extensions = [str(e).lower().strip().lstrip(".") for e in (allowed_extensions or []) if str(e).strip()]

        self.is_running = False
        self.monitor_thread = None
        self.last_error = ""
        self.recent_activity: List[Dict[str, str]] = []
        self.file_cache: Dict[str, Dict] = {}  # filename -> {size, mtime}
        self.local_cache: Dict[str, Dict] = {}  # rel path -> {size, mtime}
        self._downloaded_this_poll = set()
        self.stats = {
            "files_created": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "files_downloaded": 0,
            "files_uploaded": 0,
            "download_errors": 0,
            "upload_errors": 0,
            "total_polls": 0,
            "last_poll": None,
            "last_download": None,
            "last_upload": None,
            "connection_errors": 0,
            "last_success": None,
            "last_status": "Never polled",
            "remote_files": 0
        }

    def _record_activity(self, kind: str, message: str, *, level: str = "info") -> None:
        try:
            entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "kind": str(kind or "event"),
                "message": str(message or "").strip(),
                "level": str(level or "info"),
            }
            if not entry["message"]:
                return
            self.recent_activity.insert(0, entry)
            del self.recent_activity[60:]
        except Exception:
            pass

    def start(self):
        """Start monitoring the FTP server"""
        if self.is_running:
            return

        self.is_running = True
        self._record_activity("state", "Monitor started")
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """Stop monitoring"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self._record_activity("state", "Monitor stopped")

    def _connect(self) -> Optional[ftplib.FTP]:
        """Establish FTP connection"""
        self.last_error = ""
        try:
            if self.use_tls:
                ftp = ImplicitFTP_TLS() if self.tls_implicit else ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            try:
                ftp.encoding = self.encoding
            except Exception:
                pass
            try:
                ftp.set_pasv(self.passive_mode)
            except Exception:
                pass
            port = int(self.port or 21)
            if self.use_tls and self.tls_implicit and port in (0, 21):
                port = 990
            ftp.connect(self.host, port, timeout=10)
            ftp.login(self.username, self.password)

            try:
                ftp.set_pasv(self.passive_mode)
            except Exception:
                pass

            if self.use_tls:
                ftp.prot_p()  # Enable encryption

            return ftp

        except Exception as e:
            self.stats["connection_errors"] += 1
            self.last_error = f"FTP connection failed: {e}"
            self.stats["last_status"] = self.last_error
            self._record_activity("connection", self.last_error, level="error")
            print(f"FTP connection error: {e}")
            return None

    def _monitor_loop(self):
        """Main monitoring loop"""
        # Initial scan to populate cache
        self.poll_once()

        while self.is_running:
            time.sleep(self.poll_interval)

            if not self.is_running:
                break

            self.poll_once()

    def poll_once(self) -> bool:
        """Run a single poll cycle (scan + detect changes)."""
        ok = self._scan_directory()
        self.stats["total_polls"] += 1
        self.stats["last_poll"] = datetime.now().isoformat()
        return bool(ok)

    def _scan_directory(self) -> bool:
        """Scan FTP directory and detect changes"""
        ftp = self._connect()
        if not ftp:
            return False

        try:
            self._downloaded_this_poll = set()
            current_files = self._list_remote_files(ftp, self.remote_path, recursive=self.sync_subfolders)

            # Detect changes
            self._detect_changes(current_files, ftp)

            if self.two_way_sync and self.local_sync_dir:
                self._sync_local_changes(ftp, current_files)

            # Update cache
            self.file_cache = current_files
            if self.stats.get("last_status") != "Connected":
                self._record_activity("connection", f"Connected: {len(current_files)} remote file(s)")
            self.stats["last_status"] = "Connected"
            self.stats["last_success"] = datetime.now().isoformat()
            self.stats["remote_files"] = len(current_files)
            self.last_error = ""
            return True

        except Exception as e:
            self.last_error = f"FTP scan failed: {e}"
            self.stats["last_status"] = self.last_error
            self._record_activity("poll", self.last_error, level="error")
            print(f"Error scanning FTP directory: {e}")
            return False
        finally:
            try:
                ftp.quit()
            except:
                pass

    def _detect_changes(self, current_files: Dict, ftp: Optional[ftplib.FTP]):
        """Detect file changes between scans"""
        # Detect new files
        for filename, info in current_files.items():
            if filename not in self.file_cache:
                self.stats["files_created"] += 1
                self._record_activity("remote", f"Created: {filename}")
                self._trigger_event("created", filename)
                self._maybe_download(ftp, filename, event_type="created")

            # Detect modified files
            elif self.file_cache[filename] != info:
                self.stats["files_modified"] += 1
                self._record_activity("remote", f"Modified: {filename}")
                self._trigger_event("modified", filename)
                self._maybe_download(ftp, filename, event_type="modified")

        # Detect deleted files
        for filename in self.file_cache:
            if filename not in current_files:
                self.stats["files_deleted"] += 1
                self._record_activity("remote", f"Deleted: {filename}", level="warning")
                self._trigger_event("deleted", filename)
                self._maybe_delete_local(filename)

    def _is_allowed(self, filename: str) -> bool:
        if not self.allowed_extensions:
            return True
        suf = Path(filename).suffix.lower().lstrip(".")
        if not suf:
            return False
        return suf in self.allowed_extensions

    def _maybe_download(self, ftp: Optional[ftplib.FTP], filename: str, *, event_type: str):
        if not ftp:
            return
        if not self.local_sync_dir:
            return
        if not self._is_allowed(filename):
            return
        if event_type == "created" and not self.download_on_created:
            return
        if event_type == "modified" and not self.download_on_modified:
            return
        try:
            self._download_file(ftp, filename)
            self.stats["files_downloaded"] += 1
            self.stats["last_download"] = datetime.now().isoformat()
            self._record_activity("download", f"Downloaded: {filename}")
            try:
                self._downloaded_this_poll.add(str(filename))
            except Exception:
                pass
        except Exception as e:
            self.stats["download_errors"] += 1
            self._record_activity("download", f"Download failed for {filename}: {e}", level="error")
            print(f"FTP download error: {e}")

    def _download_file(self, ftp: ftplib.FTP, filename: str):
        out_dir = Path(self.local_sync_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        rel = self._safe_remote_rel(filename)
        if not rel:
            raise ValueError(f"Unsafe remote filename: {filename}")
        if self.sync_subfolders and rel:
            out_path = self._local_path_for_remote_rel(out_dir, rel)
        else:
            safe_name = self._safe_local_component(Path(rel).name)
            out_path = out_dir / safe_name
        try:
            if out_dir.resolve() != out_path.resolve() and out_dir.resolve() not in out_path.resolve().parents:
                raise ValueError(f"Unsafe local sync path: {out_path}")
        except ValueError:
            raise
        except Exception:
            pass
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not self.overwrite_local:
            return
        tmp = out_path.with_suffix(out_path.suffix + ".part")
        with open(tmp, "wb") as f:
            remote_path = self._remote_join(self.remote_path, rel)
            ftp.retrbinary(f"RETR {remote_path}", f.write)
        tmp.replace(out_path)

    def _maybe_delete_local(self, filename: str):
        if not self.delete_local_on_deleted:
            return
        if not self.local_sync_dir:
            return
        try:
            base = Path(self.local_sync_dir).expanduser()
            rel = self._safe_remote_rel(filename)
            if not rel:
                self._record_activity("delete", f"Skipped unsafe delete path: {filename}", level="warning")
                return
            if self.sync_subfolders and rel:
                p = self._local_path_for_remote_rel(base, rel)
            else:
                p = base / self._safe_local_component(Path(rel).name)
            if base.resolve() != p.resolve() and base.resolve() not in p.resolve().parents:
                return
            if p.exists():
                p.unlink()
                self._record_activity("delete", f"Deleted local copy: {p.name}", level="warning")
        except Exception:
            return

    def _trigger_event(self, event_type: str, filename: str):
        """Trigger event callback"""
        if self.event_callback:
            # Create virtual path for consistency
            remote = self._remote_join(self.remote_path, filename)
            virtual_path = f"ftp://{self.host}{remote}"
            self.event_callback(self.monitor_id, event_type, virtual_path, None)

    def get_connection_info(self) -> str:
        """Get connection string for display"""
        return f"ftp://{self.host}:{self.port}{self.remote_path}"

    def _sync_local_changes(self, ftp: ftplib.FTP, remote_files: Dict[str, Dict]):
        base = Path(self.local_sync_dir).expanduser()
        if not base.exists() or not base.is_dir():
            return
        local_files: Dict[str, Dict] = {}
        paths = base.rglob("*") if self.sync_subfolders else base.glob("*")
        for p in paths:
            try:
                if p.is_dir():
                    continue
                rel = p.relative_to(base).as_posix()
                if not self._is_allowed(rel):
                    continue
                st = p.stat()
                size = int(st.st_size)
                mtime = float(st.st_mtime)
                # Skip files still being written to avoid half-uploaded/locked files.
                if (time.time() - mtime) < 1.5:
                    continue
                local_files[rel] = {"size": size, "mtime": mtime}
                prev = self.local_cache.get(rel)
                changed = prev is None or prev.get("size") != size or abs(float(prev.get("mtime", 0)) - mtime) > 1.0
                if not changed:
                    continue
                if rel in self._downloaded_this_poll:
                    continue
                remote = remote_files.get(rel)
                if remote:
                    remote_ts = self._parse_mdtm(remote.get("mtime", ""))
                    if remote_ts is not None and remote_ts > mtime:
                        continue
                    if remote_ts is not None and remote.get("size") == size and abs(remote_ts - mtime) < 2.0:
                        continue
                self._upload_file(ftp, rel, p)
                self.stats["files_uploaded"] += 1
                self.stats["last_upload"] = datetime.now().isoformat()
                self._record_activity("upload", f"Uploaded: {rel}")
            except Exception as e:
                self.stats["upload_errors"] += 1
                self._record_activity("upload", f"Upload failed for {p.name}: {e}", level="error")
                print(f"FTP upload error: {e}")
                continue
        self.local_cache = local_files

    def _upload_file(self, ftp: ftplib.FTP, rel_path: str, local_path: Path):
        rel = self._safe_remote_rel(rel_path)
        if not rel:
            raise ValueError(f"Unsafe upload path: {rel_path}")
        remote_file = self._remote_join(self.remote_path, rel)
        remote_dir = "/".join(remote_file.split("/")[:-1]) or "/"
        self._ensure_remote_dir(ftp, remote_dir)
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_file}", f)
        self._apply_remote_permissions(ftp, remote_file)

    def _apply_remote_permissions(self, ftp: ftplib.FTP, remote_file: str):
        # Best-effort: make uploads readable on typical servers (vsftpd honors SITE CHMOD if enabled).
        mode = "644"
        try:
            ftp.sendcmd(f"SITE CHMOD {mode} {remote_file}")
            return
        except Exception:
            pass
        try:
            ftp.sendcmd(f'SITE CHMOD {mode} "{remote_file}"')
        except Exception:
            pass

    def _ensure_remote_dir(self, ftp: ftplib.FTP, remote_dir: str):
        target = self._norm_remote_path(remote_dir)
        if target in ("", "/"):
            return
        parts = [p for p in target.strip("/").split("/") if p]
        cur = ""
        for part in parts:
            cur = f"{cur}/{part}" if cur else f"/{part}"
            try:
                ftp.mkd(cur)
            except Exception:
                pass

    def _norm_remote_path(self, path: str) -> str:
        p = str(path or "/").replace("\\", "/").strip() or "/"
        if "\r" in p or "\n" in p:
            raise ValueError("Remote path cannot contain line breaks.")
        while "//" in p:
            p = p.replace("//", "/")
        if not p.startswith("/"):
            p = "/" + p
        if any(part in {".", ".."} for part in p.strip("/").split("/") if part):
            raise ValueError("Remote path cannot contain . or .. segments.")
        if len(p) > 1 and p.endswith("/"):
            p = p[:-1]
        return p or "/"

    def _remote_join(self, base: str, rel: str) -> str:
        base = self._norm_remote_path(base)
        rel = self._safe_remote_rel(rel)
        if not rel:
            return base
        if base == "/":
            return "/" + rel
        return base + "/" + rel

    def _parse_mdtm(self, val: str) -> Optional[float]:
        try:
            ts = str(val or "").strip()
            if " " in ts:
                ts = ts.split()[-1]
            if not ts:
                return None
            dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
            return dt.timestamp()
        except Exception:
            return None

    def _safe_remote_rel(self, rel: str) -> str:
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

    def _safe_local_component(self, name: str) -> str:
        import re

        cleaned = str(name or "").strip()
        cleaned = re.sub(r'[<>:"|?*\x00-\x1f]', "_", cleaned)
        cleaned = cleaned.strip(" .")
        reserved = {
            "con", "prn", "aux", "nul",
            "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
            "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
        }
        if cleaned.lower() in reserved:
            cleaned = f"_{cleaned}"
        return cleaned[:180] or "remote_file"

    def _local_path_for_remote_rel(self, base: Path, rel: str) -> Path:
        safe_rel = self._safe_remote_rel(rel)
        if not safe_rel:
            raise ValueError(f"Unsafe remote relative path: {rel}")
        parts = [self._safe_local_component(part) for part in safe_rel.split("/")]
        return base.joinpath(*parts)

    def _list_remote_files(self, ftp: ftplib.FTP, root_path: str, *, recursive: bool) -> Dict[str, Dict]:
        root = self._norm_remote_path(root_path)
        files: Dict[str, Dict] = {}

        def rel_from(path: str) -> str:
            if root == "/":
                return path.lstrip("/")
            prefix = root + "/"
            return path[len(prefix):] if path.startswith(prefix) else path.lstrip("/")

        def list_dir(path: str) -> bool:
            try:
                for name, facts in ftp.mlsd(path):
                    n = str(name or "").strip()
                    if not n or n in (".", ".."):
                        continue
                    pth = self._remote_join(path, n)
                    typ = str(facts.get("type", "")).lower()
                    if typ == "dir":
                        if recursive:
                            list_dir(pth)
                        continue
                    if typ not in ("file", "OS.unix=reg"):
                        continue
                    size = 0
                    try:
                        size = int(facts.get("size", 0))
                    except Exception:
                        size = 0
                    mtime = ""
                    try:
                        mtime = ftp.sendcmd(f"MDTM {pth}")
                        if " " in mtime:
                            mtime = mtime.split()[-1]
                    except Exception:
                        mtime = ""
                    rel = self._safe_remote_rel(rel_from(pth))
                    if rel:
                        files[rel] = {"size": size, "mtime": mtime}
                return True
            except Exception:
                pass

            lines: List[str] = []
            try:
                ftp.retrlines(f"LIST {path}", lines.append)
            except Exception:
                return False
            for line in lines:
                try:
                    if not line:
                        continue
                    parts = line.split(maxsplit=8)
                    if len(parts) < 9:
                        continue
                    name = parts[8]
                    if not name or name in (".", ".."):
                        continue
                    is_dir = str(parts[0] or "").startswith("d")
                    pth = self._remote_join(path, name)
                    if is_dir:
                        if recursive:
                            list_dir(pth)
                        continue
                    size = int(parts[4]) if parts[4].isdigit() else 0
                    mtime = ""
                    try:
                        mtime = ftp.sendcmd(f"MDTM {pth}")
                        if " " in mtime:
                            mtime = mtime.split()[-1]
                    except Exception:
                        mtime = ""
                    rel = self._safe_remote_rel(rel_from(pth))
                    if rel:
                        files[rel] = {"size": size, "mtime": mtime}
                except Exception:
                    continue
            return True

        if not list_dir(root):
            raise RuntimeError(f"Could not list remote FTP path: {root}")
        return files


class FTPMonitorManager:
    """Manages FTP monitors separately from file system monitors"""

    def __init__(self):
        self.ftp_monitors: Dict[str, FTPMonitor] = {}
        self.last_error = ""

    def list_remote_dirs(
        self,
        host: str,
        username: str,
        password: str,
        remote_path: str = "/",
        *,
        port: int = 21,
        use_tls: bool = False,
        timeout: int = 15,
        passive_mode: bool = True,
        tls_implicit: bool = False,
        encoding: str = "utf-8",
    ) -> List[str]:
        """
        List child directories under the given remote path.

        Used by the UI "Browse" helper when configuring an FTP monitor.
        """
        host = str(host or "").strip()
        if not host:
            raise ValueError("Host is required.")
        username = str(username or "").strip()
        password = str(password or "")
        remote_path = str(remote_path or "/").strip() or "/"

        if use_tls:
            ftp = ImplicitFTP_TLS() if tls_implicit else ftplib.FTP_TLS()
        else:
            ftp = ftplib.FTP()
        try:
            try:
                ftp.encoding = (encoding or "").strip() or "utf-8"
            except Exception:
                pass
            port_num = int(port or 21)
            if use_tls and tls_implicit and port_num in (0, 21):
                port_num = 990
            ftp.connect(host, port_num, timeout=timeout)
            ftp.login(username, password)
            if use_tls and isinstance(ftp, ftplib.FTP_TLS):
                try:
                    ftp.prot_p()
                except Exception:
                    pass
            try:
                ftp.set_pasv(bool(passive_mode))
            except Exception:
                pass
            ftp.cwd(remote_path)

            dirs: List[str] = []
            try:
                for name, facts in ftp.mlsd():
                    try:
                        if str(facts.get("type", "")).lower() == "dir" and name not in (".", ".."):
                            dirs.append(name)
                    except Exception:
                        continue
            except Exception:
                lines: List[str] = []
                try:
                    ftp.retrlines("LIST", lines.append)
                except Exception:
                    lines = []
                for line in lines:
                    try:
                        if not line or not str(line).startswith("d"):
                            continue
                        # LIST format: drwxr-xr-x 1 owner group 4096 Jan 01 12:00 dirname
                        name = str(line).split(maxsplit=8)[-1]
                        if name and name not in (".", ".."):
                            dirs.append(name)
                    except Exception:
                        continue

            # De-dup and stable sort.
            seen = set()
            out: List[str] = []
            for d in dirs:
                k = d.strip()
                if not k:
                    continue
                lk = k.lower()
                if lk in seen:
                    continue
                seen.add(lk)
                out.append(k)
            out.sort(key=lambda s: s.lower())
            return out
        finally:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass

    def add_ftp_monitor(self, monitor_id: str, host: str, username: str,
                       password: str, remote_path: str, port: int = 21,
                       use_tls: bool = False, poll_interval: int = 30,
                       event_callback: Callable = None,
                       local_sync_dir: Optional[str] = None,
                       download_on_created: bool = True,
                       download_on_modified: bool = True,
                       delete_local_on_deleted: bool = False,
                       overwrite_local: bool = False,
                       allowed_extensions: Optional[List[str]] = None,
                       passive_mode: bool = True,
                       tls_implicit: bool = False,
                       encoding: str = "utf-8",
                       two_way_sync: bool = False,
                       sync_subfolders: bool = False) -> bool:
        """Add a new FTP monitor"""
        try:
            self.last_error = ""
            problems = self.validate_ftp_config(
                host=host,
                username=username,
                password=password,
                remote_path=remote_path,
                port=port,
                poll_interval=poll_interval,
                local_sync_dir=local_sync_dir,
                allowed_extensions=allowed_extensions,
            )
            if problems:
                raise ValueError("; ".join(problems))
            monitor = FTPMonitor(
                monitor_id, host, username, password, remote_path,
                port, use_tls, poll_interval, event_callback,
                local_sync_dir=local_sync_dir,
                download_on_created=download_on_created,
                download_on_modified=download_on_modified,
                delete_local_on_deleted=delete_local_on_deleted,
                overwrite_local=overwrite_local,
                allowed_extensions=allowed_extensions,
                passive_mode=passive_mode,
                tls_implicit=tls_implicit,
                encoding=encoding,
                two_way_sync=two_way_sync,
                sync_subfolders=sync_subfolders,
            )

            self.ftp_monitors[monitor_id] = monitor
            return True

        except Exception as e:
            self.last_error = str(e)
            print(f"Error adding FTP monitor: {e}")
            return False

    def validate_ftp_config(
        self,
        *,
        host: str,
        username: str,
        password: str,
        remote_path: str,
        port: int,
        poll_interval: int,
        local_sync_dir: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
    ) -> List[str]:
        problems: List[str] = []
        if not str(host or "").strip():
            problems.append("FTP host is required.")
        if not str(username or "").strip():
            problems.append("FTP username is required.")
        if password is None or str(password) == "":
            problems.append("FTP password is required.")
        try:
            p = int(port)
            if p < 1 or p > 65535:
                problems.append("FTP port must be between 1 and 65535.")
        except Exception:
            problems.append("FTP port must be a number.")
        try:
            interval = int(poll_interval)
            if interval < 5:
                problems.append("FTP poll interval must be at least 5 seconds.")
        except Exception:
            problems.append("FTP poll interval must be a number.")
        try:
            probe = FTPMonitor(
                "_validation",
                str(host or "host"),
                str(username or "user"),
                str(password or "password"),
                str(remote_path or "/"),
            )
            probe._norm_remote_path(remote_path or "/")
        except Exception as e:
            problems.append(f"Remote path is invalid: {e}")
        if local_sync_dir:
            try:
                local = Path(str(local_sync_dir)).expanduser()
                if local.exists() and not local.is_dir():
                    problems.append("Local sync path must be a folder.")
                parts = {part.lower() for part in local.parts}
                if "$recycle.bin" in parts or "system volume information" in parts:
                    problems.append("Local sync folder cannot be a protected system folder.")
            except Exception as e:
                problems.append(f"Local sync folder is invalid: {e}")
        for ext in allowed_extensions or []:
            e = str(ext or "").strip().lstrip(".")
            if not e:
                continue
            if any(ch in e for ch in "/\\:*?\"<>|\r\n"):
                problems.append(f"File extension filter is invalid: {ext}")
        return problems

    def start_ftp_monitor(self, monitor_id: str) -> bool:
        """Start an FTP monitor"""
        self.last_error = ""
        monitor = self.ftp_monitors.get(monitor_id)
        if monitor:
            try:
                monitor.start()
                return True
            except Exception as e:
                self.last_error = str(e)
                return False
        self.last_error = f"FTP monitor not found: {monitor_id}"
        return False

    def stop_ftp_monitor(self, monitor_id: str) -> bool:
        """Stop an FTP monitor"""
        self.last_error = ""
        monitor = self.ftp_monitors.get(monitor_id)
        if monitor:
            try:
                monitor.stop()
                return True
            except Exception as e:
                self.last_error = str(e)
                return False
        self.last_error = f"FTP monitor not found: {monitor_id}"
        return False

    def remove_ftp_monitor(self, monitor_id: str) -> bool:
        """Remove an FTP monitor"""
        self.last_error = ""
        if monitor_id in self.ftp_monitors:
            if not self.stop_ftp_monitor(monitor_id):
                return False
            del self.ftp_monitors[monitor_id]
            return True
        self.last_error = f"FTP monitor not found: {monitor_id}"
        return False

    def get_ftp_monitor(self, monitor_id: str) -> Optional[FTPMonitor]:
        """Get an FTP monitor"""
        return self.ftp_monitors.get(monitor_id)

    def poll_once(self, monitor_id: str) -> bool:
        self.last_error = ""
        mon = self.ftp_monitors.get(monitor_id)
        if not mon:
            self.last_error = f"FTP monitor not found: {monitor_id}"
            return False
        ok = bool(mon.poll_once())
        if not ok:
            self.last_error = str(getattr(mon, "last_error", "") or "FTP poll failed.")
        return ok

    def stop_all(self):
        """Stop all FTP monitors"""
        for monitor in self.ftp_monitors.values():
            monitor.stop()
