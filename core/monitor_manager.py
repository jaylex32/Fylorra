"""Monitor Manager - Handles all folder monitoring operations"""

import threading
import time
import os
from typing import Dict, List, Callable, Optional, Union
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from utils.notification_manager import NotificationManager
from core.action_engine import ActionEngine, _is_active_download_artifact
from core.ftp_monitor import FTPMonitorManager
from core.logger import ActivityLogger
from core.analytics import AnalyticsManager
from core.scheduled_tasks import ScheduledTask, ScheduledTaskManager
from core.branding import APP_DATA_DIR_NAME, DEFAULT_CLOUD_SYNC_FOLDER


def _same_or_inside(child: Path, parent: Path) -> bool:
    try:
        c = child.resolve()
        p = parent.resolve()
        return c == p or p in c.parents
    except Exception:
        c = os.path.normcase(os.path.abspath(str(child)))
        p = os.path.normcase(os.path.abspath(str(parent)))
        return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def _protected_monitor_roots() -> List[Path]:
    roots: List[Path] = []
    for value in (
        os.environ.get("WINDIR"),
        os.environ.get("SystemRoot"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if value:
            roots.append(Path(value))
    roots.append(Path.home() / APP_DATA_DIR_NAME)
    return roots


def _is_protected_monitor_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path.absolute()
    try:
        if resolved.parent == resolved:
            return True
    except Exception:
        return True
    for protected in _protected_monitor_roots():
        try:
            if resolved == protected.resolve() or protected.resolve() in resolved.parents:
                return True
        except Exception:
            continue
    try:
        parts = {p.lower() for p in resolved.parts}
        if "$recycle.bin" in parts or "system volume information" in parts:
            return True
    except Exception:
        pass
    return False


class FolderMonitor(FileSystemEventHandler):
    """Individual folder monitor with event handling"""

    def __init__(self, monitor_id: str, path: str, rules: List[Dict],
                 notification_manager: NotificationManager,
                 action_engine: ActionEngine,
                 cloud_sync_manager,
                 logger: ActivityLogger,
                 event_callback: Callable = None,
                 notify_created: bool = True,
                 notify_modified: bool = True,
                 notify_deleted: bool = True,
                 notify_moved: bool = True,
                 email_recipient: str = "",
                 email_notifier = None,
                 analytics_manager = None,
                 min_size_kb: int = None,
                 max_size_kb: int = None,
                 modified_within_days: int = None,
                 exclude_patterns: List[str] = None,
                 filename_regex: str = None,
                 action_delay_seconds: Union[int, float] = 0,
                 action_stability_seconds: Union[int, float] = 0):
        super().__init__()
        self.monitor_id = monitor_id
        self.path = path
        self.rules = rules
        self.notification_manager = notification_manager
        self.action_engine = action_engine
        self.cloud_sync_manager = cloud_sync_manager
        self.logger = logger
        self.event_callback = event_callback
        self.notify_created = notify_created
        self.notify_modified = notify_modified
        self.notify_deleted = notify_deleted
        self.notify_moved = notify_moved
        self.email_recipient = email_recipient
        self.email_notifier = email_notifier
        self.analytics_manager = analytics_manager
        # Advanced filters
        self.min_size_kb = min_size_kb
        self.max_size_kb = max_size_kb
        self.modified_within_days = modified_within_days
        self.exclude_patterns = exclude_patterns or []
        self.filename_regex = filename_regex
        try:
            self.action_delay_seconds = max(0.0, float(action_delay_seconds or 0))
        except Exception:
            self.action_delay_seconds = 0.0
        try:
            self.action_stability_seconds = max(0.0, float(action_stability_seconds or 0))
        except Exception:
            self.action_stability_seconds = 0.0
        self.is_running = False
        self.observer = None
        self._delay_lock = threading.Lock()
        self._delay_timers: Dict[str, threading.Timer] = {}
        self._recent_lock = threading.Lock()
        self._recent_events: Dict[str, tuple[float, tuple]] = {}
        self._activity_lock = threading.Lock()
        self.recent_activity: List[Dict] = []
        self.pending_actions: Dict[str, Dict] = {}
        self.stats = {
            "files_created": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "files_moved": 0,
            "actions_executed": 0,
            "files_filtered": 0
        }

    def _record_activity(self, kind: str, message: str, *, level: str = "info", **extra):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.time(),
            "kind": str(kind or "event"),
            "message": str(message or ""),
            "level": str(level or "info"),
        }
        for key, value in extra.items():
            try:
                entry[key] = value
            except Exception:
                pass
        with self._activity_lock:
            self.recent_activity.insert(0, entry)
            del self.recent_activity[120:]

    def start(self):
        """Start monitoring the folder"""
        if self.is_running:
            return

        # Support for UNC network paths (\\server\share)
        if self.path.startswith('\\\\'):
            # Network path - check if accessible
            if not os.path.exists(self.path):
                raise ValueError(f"Network path not accessible: {self.path}")
        else:
            # Local path
            local_path = Path(self.path)
            if not local_path.exists():
                raise ValueError(f"Path does not exist: {self.path}")
            if not local_path.is_dir():
                raise ValueError(f"Monitor path must be a folder: {self.path}")
            if _is_protected_monitor_path(local_path):
                raise ValueError(f"Refusing to monitor protected folder: {self.path}")

        # Start the observer first
        self.observer = Observer()
        self.observer.schedule(self, self.path, recursive=True)
        self.observer.start()
        self.is_running = True

        self.logger.log_monitor_event("started", self.monitor_id, self.path)
        delay = int(round(float(getattr(self, "action_delay_seconds", 0) or 0)))
        stable = int(round(float(getattr(self, "action_stability_seconds", 0) or 0)))
        timing = []
        if delay:
            timing.append(f"{delay}s action delay")
        if stable:
            timing.append(f"{stable}s stability check")
        timing_text = f" ({', '.join(timing)})" if timing else ""
        self._record_activity("Started", f"Monitoring started for {self.path}{timing_text}.")

        # Perform initial scan in background thread to avoid UI freeze
        scan_thread = threading.Thread(target=self._initial_scan, daemon=True)
        scan_thread.start()

    def _initial_scan(self):
        """Scan folder and log all existing files and subfolders"""
        try:
            path_obj = Path(self.path)
            file_count = 0
            folder_count = 0
            sample_files = []
            sample_limit = 100

            # Recursively scan
            for item in path_obj.rglob('*'):
                if not self.is_running:
                    break
                try:
                    if item.is_file():
                        file_count += 1
                        if len(sample_files) < sample_limit:
                            sample_files.append(str(item))
                    elif item.is_dir():
                        folder_count += 1
                except OSError:
                    continue

            # Log initial scan summary
            self.logger.log_initial_scan(
                self.monitor_id,
                self.path,
                file_count,
                folder_count
            )
            self._record_activity(
                "Initial scan",
                f"Found {file_count} existing files and {folder_count} folders. Existing files are not moved until Run automation rules now is used.",
            )

            # Log each file (limit to avoid overwhelming logs)
            if file_count <= sample_limit:
                for file_path in sample_files:
                    self.logger.log_event(
                        self.monitor_id,
                        self.path,
                        "existing",
                        file_path,
                        "Found during initial scan"
                    )
            else:
                self.logger.log_event(
                    self.monitor_id,
                    self.path,
                    "existing",
                    f"{file_count} files",
                    f"Initial scan found {file_count} files (too many to list individually)"
                )

        except Exception as e:
            self.logger.log_error("initial_scan", str(e))
            self._record_activity("Scan failed", f"Initial scan failed: {e}", level="error")

    def stop(self):
        """Stop monitoring the folder"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.is_running = False
            self.observer = None
            try:
                self._cancel_pending_actions()
            except Exception:
                pass
            self.logger.log_monitor_event("stopped", self.monitor_id, self.path)
            self._record_activity("Stopped", f"Monitoring stopped for {self.path}.", level="warning")

    def on_created(self, event: FileSystemEvent):
        """Handle file/folder creation"""
        if not event.is_directory:
            self._process_event("created", event.src_path)

    def on_modified(self, event: FileSystemEvent):
        """Handle file/folder modification"""
        if not event.is_directory:
            self._process_event("modified", event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        """Handle file/folder deletion"""
        if not event.is_directory:
            self._process_event("deleted", event.src_path)

    def on_moved(self, event: FileSystemEvent):
        """Handle file/folder move"""
        if not event.is_directory:
            self._process_event("moved", event.src_path, event.dest_path)

    def _process_event(self, event_type: str, src_path: str, dest_path: str = None) -> bool:
        """Process file system event and execute rules"""
        event_path = dest_path if event_type == "moved" and dest_path else src_path

        # Apply advanced filters - skip if file doesn't match criteria
        if not self._passes_filters(event_path):
            self.stats["files_filtered"] += 1
            self._record_activity(
                "Skipped",
                f"{Path(event_path).name}: blocked by monitor filters.",
                level="warning",
                event_type=event_type,
                path=event_path,
            )
            return False

        if self._is_duplicate_event(event_type, event_path):
            self._record_activity(
                "Ignored",
                f"{Path(event_path).name}: duplicate modified event suppressed.",
                event_type=event_type,
                path=event_path,
            )
            return False

        stat_key = {
            "created": "files_created",
            "modified": "files_modified",
            "deleted": "files_deleted",
            "moved": "files_moved",
        }.get(event_type)
        if stat_key:
            self.stats[stat_key] = int(self.stats.get(stat_key, 0) or 0) + 1

        # Log the event
        self.logger.log_event(
            self.monitor_id,
            self.path,
            event_type,
            src_path,
            f"Destination: {dest_path}" if dest_path else ""
        )

        # Record analytics
        if self.analytics_manager:
            self.analytics_manager.record_event(event_type, self.monitor_id, event_path)

        file_name = Path(event_path).name
        self._record_activity(
            "Detected",
            f"{event_type.title()} event for {file_name}.",
            event_type=event_type,
            path=event_path,
        )

        # Send Windows notification
        self._send_notification(event_type, file_name, event_path)

        # Callback to update GUI
        if self.event_callback:
            self.event_callback(self.monitor_id, event_type, src_path, dest_path)

        # Execute matching rules (with optional delay)
        delay = float(getattr(self, "action_delay_seconds", 0) or 0)
        stable_wait = float(getattr(self, "action_stability_seconds", 0) or 0)
        if delay > 0 or stable_wait > 0:
            file_ext = Path(event_path).suffix
            matched_rules = [rule for rule in self.rules if self._rule_matches(rule, event_type, file_name, file_ext)]
            if not matched_rules:
                self._record_activity(
                    "No match",
                    f"{file_name}: no automation rule matched this {event_type} event.",
                    event_type=event_type,
                    path=event_path,
                )
                return True
            self._schedule_action_execution(event_type, src_path, dest_path, delay, stable_wait, len(matched_rules))
            return True

        self._execute_actions(event_type, src_path, dest_path)
        return True

    def _is_duplicate_event(self, event_type: str, file_path: str) -> bool:
        """Suppress duplicate watchdog bursts for the same unchanged file."""
        if event_type != "modified":
            return False
        try:
            path = Path(file_path)
            stat = path.stat() if path.exists() else None
            signature = (
                event_type,
                str(path).lower() if os.name == "nt" else str(path),
                stat.st_size if stat else None,
                stat.st_mtime_ns if stat else None,
            )
        except Exception:
            signature = (event_type, str(file_path).lower() if os.name == "nt" else str(file_path))

        key = f"{event_type}:{signature[1]}"
        now = time.time()
        with self._recent_lock:
            old = self._recent_events.get(key)
            # Keep the small cache tidy.
            if len(self._recent_events) > 512:
                cutoff = now - 5.0
                self._recent_events = {k: v for k, v in self._recent_events.items() if v[0] >= cutoff}
            self._recent_events[key] = (now, signature)
        return bool(old and old[1] == signature and (now - old[0]) < 1.0)

    def _schedule_action_execution(self, event_type: str, src_path: str, dest_path: str, delay: float, stable_wait: float = 0, matched_rule_count: int = 0):
        key_path = dest_path if event_type == "moved" and dest_path else src_path
        key = f"{event_type}:{key_path}"
        due_at = time.time() + max(0.0, float(delay or 0))
        name = Path(key_path).name
        match_text = f"{matched_rule_count} rule{'s' if matched_rule_count != 1 else ''} matched"
        self.pending_actions[key] = {
            "event_type": event_type,
            "path": key_path,
            "file_name": name,
            "due_at": due_at,
            "delay_seconds": max(0.0, float(delay or 0)),
            "stable_wait_seconds": max(0.0, float(stable_wait or 0)),
            "status": "waiting" if delay > 0 else "checking stability",
            "matched_rule_count": int(matched_rule_count or 0),
        }
        if delay > 0:
            self._record_activity(
                "Waiting",
                f"{name}: {match_text}; action starts in {int(round(delay))} seconds.",
                event_type=event_type,
                path=key_path,
                due_at=due_at,
                matched_rule_count=matched_rule_count,
            )
        elif stable_wait > 0:
            self._record_activity(
                "Waiting",
                f"{name}: {match_text}; checking that the file is stable for {int(round(stable_wait))} seconds before action.",
                event_type=event_type,
                path=key_path,
                matched_rule_count=matched_rule_count,
            )

        def _run():
            try:
                if not self.is_running:
                    self._record_activity("Cancelled", f"{name}: pending action cancelled because the monitor stopped.", level="warning", event_type=event_type, path=key_path)
                    return
                self._execute_actions(event_type, src_path, dest_path)
            finally:
                try:
                    with self._delay_lock:
                        self._delay_timers.pop(key, None)
                    self.pending_actions.pop(key, None)
                except Exception:
                    pass

        with self._delay_lock:
            existing = self._delay_timers.pop(key, None)
            if existing:
                try:
                    existing.cancel()
                except Exception:
                    pass
            t = threading.Timer(delay, _run)
            t.daemon = True
            self._delay_timers[key] = t
            t.start()

    def _cancel_pending_actions(self):
        with self._delay_lock:
            timers = list(self._delay_timers.values())
            self._delay_timers.clear()
        try:
            for pending in list(self.pending_actions.values()):
                self._record_activity("Cancelled", f"{pending.get('file_name') or pending.get('path')}: pending action cancelled.", level="warning")
            self.pending_actions.clear()
        except Exception:
            pass
        for t in timers:
            try:
                t.cancel()
            except Exception:
                pass

    def _wait_for_file_stable(self, file_path: str, stable_seconds: float, max_wait_seconds: Optional[float] = None) -> bool:
        if stable_seconds <= 0:
            return True
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                return False
        except Exception:
            return False

        check_interval = 0.5 if stable_seconds < 3 else 1.0
        start = time.time()
        last_size = None
        last_change = start

        while True:
            if not self.is_running:
                return False
            try:
                size = path.stat().st_size
            except Exception:
                return False
            now = time.time()
            if last_size is None or size != last_size:
                last_size = size
                last_change = now
            else:
                if (now - last_change) >= stable_seconds:
                    return True
            if max_wait_seconds is not None and (now - start) >= max_wait_seconds:
                return True
            time.sleep(check_interval)

    def _execute_actions(self, event_type: str, src_path: str, dest_path: str = None):
        event_path = dest_path if event_type == "moved" and dest_path else src_path
        file_name = Path(event_path).name
        file_ext = Path(event_path).suffix

        stable_wait = float(getattr(self, "action_stability_seconds", 0) or 0)
        if stable_wait > 0 and event_type != "deleted":
            check_path = dest_path if event_type == "moved" and dest_path else src_path
            max_wait = max(30.0, stable_wait * 6.0)
            self._record_activity(
                "Waiting",
                f"{Path(check_path).name}: waiting until the file stays unchanged for {int(round(stable_wait))} seconds.",
                event_type=event_type,
                path=check_path,
            )
            if not self._wait_for_file_stable(check_path, stable_wait, max_wait):
                self._record_activity(
                    "Skipped",
                    f"{Path(check_path).name}: file was not ready before the stability timeout.",
                    level="warning",
                    event_type=event_type,
                    path=check_path,
                )
                return

        # Execute matching rules
        matched_rules = 0
        for rule in self.rules:
            if self._rule_matches(rule, event_type, file_name, file_ext):
                matched_rules += 1
                action_type = str(rule.get("action_type") or "").strip().lower()
                params = rule.get("action_params", {}) or {}

                # Some actions need the destination path on move events.
                exec_path = src_path
                if event_type == "moved" and dest_path:
                    exec_path = dest_path

                label = str(rule.get("interpretation") or action_type or "automation rule").strip()
                self._record_activity(
                    "Rule matched",
                    f"{file_name}: {label}.",
                    event_type=event_type,
                    action_type=action_type,
                    path=exec_path,
                )
                try:
                    previewer = getattr(self.action_engine, "preview_action", None)
                    if action_type != "cloud_upload" and callable(previewer):
                        preview = previewer(action_type, exec_path, params)
                        summary = str((preview or {}).get("summary") or "").strip()
                        if summary:
                            self._record_activity(
                                "Planned",
                                summary,
                                event_type=event_type,
                                action_type=action_type,
                                path=exec_path,
                                target=str((preview or {}).get("target") or ""),
                            )
                except Exception:
                    pass
                self._record_activity(
                    "Action started",
                    f"{action_type or 'action'} for {file_name}.",
                    event_type=event_type,
                    action_type=action_type,
                    path=exec_path,
                )

                if action_type == "cloud_upload":
                    action_result = bool(self._action_cloud_upload(exec_path, params))
                else:
                    action_result = self.action_engine.execute_action(
                        action_type,
                        exec_path,
                        params,
                    )

                result = "success" if action_result else "failed"
                detail = f"Rule matched: {event_type} event"
                extra = str(getattr(self.action_engine, "last_action_info", "") or "").strip()
                if extra:
                    detail = f"{detail}; {extra}"
                self.logger.log_action(
                    self.monitor_id,
                    action_type,
                    exec_path,
                    result,
                    detail
                )

                if action_result:
                    self.stats["actions_executed"] += 1
                    self._record_activity(
                        "Completed",
                        f"{action_type or 'Action'} completed for {file_name}." + (f" {extra}" if extra else ""),
                        event_type=event_type,
                        action_type=action_type,
                        path=exec_path,
                    )
                else:
                    self._record_activity(
                        "Failed",
                        f"{action_type or 'Action'} failed for {file_name}." + (f" {extra}" if extra else ""),
                        level="error",
                        event_type=event_type,
                        action_type=action_type,
                        path=exec_path,
                    )

        if matched_rules == 0:
            self._record_activity(
                "No match",
                f"{file_name}: no automation rule matched this {event_type} event.",
                event_type=event_type,
                path=event_path,
            )

    def _action_cloud_upload(self, file_path: str, params: Dict) -> bool:
        """
        Upload a file that changed in this monitored folder to a configured cloud provider.

        Params:
        - provider: "onedrive" | "gdrive"
        - remote_base: folder path under root (both providers; gdrive will be created under root)
        - include_subfolders: bool (default True) - whether to preserve subfolders relative to monitor root
        """
        try:
            mgr = self.cloud_sync_manager
            if mgr is None:
                return False

            p = Path(str(file_path or ""))
            if not p.exists() or not p.is_file():
                return False

            provider = str(params.get("provider") or "").strip().lower()
            if provider not in {"onedrive", "gdrive"}:
                return False

            remote_base = str(params.get("remote_base") or DEFAULT_CLOUD_SYNC_FOLDER).strip().strip("/").strip("\\")
            if not remote_base:
                remote_base = DEFAULT_CLOUD_SYNC_FOLDER

            include_subfolders = bool(params.get("include_subfolders", True))

            rel_dir = ""
            if include_subfolders:
                try:
                    rel_dir = str(p.parent.relative_to(Path(self.path))).replace("\\", "/")
                    if rel_dir == ".":
                        rel_dir = ""
                except Exception:
                    rel_dir = ""

            remote_dir = f"{remote_base}/{rel_dir}".strip("/").strip("\\") if rel_dir else remote_base

            prov = mgr.provider(provider)  # type: ignore[attr-defined]
            if not prov or not getattr(prov, "is_connected", lambda: False)():
                # Not connected; cannot upload.
                return False

            # Ensure folder exists on remote.
            if provider == "onedrive":
                try:
                    prov.ensure_folder_path(remote_dir)  # type: ignore[attr-defined]
                except Exception:
                    pass
                mgr.upload_file(provider, p, remote_folder=remote_dir, remote_name=p.name)  # type: ignore[arg-type]
                return True

            # Google Drive: remote_folder expects an id; create folders along the path.
            folder_id = None
            try:
                folder_id = mgr.ensure_gdrive_folder_path(remote_dir)  # type: ignore[attr-defined]
            except Exception:
                folder_id = None
            mgr.upload_file(provider, p, remote_folder=folder_id, remote_name=p.name)  # type: ignore[arg-type]
            return True
        except Exception:
            return False

    def _passes_filters(self, file_path: str) -> bool:
        """Check if file passes advanced filters"""
        import re
        import fnmatch
        from datetime import datetime, timedelta

        file_path_obj = Path(file_path)
        file_name = file_path_obj.name

        # Never process browser/download-manager temporary files. Wait for the
        # final rename/create event after the download completes.
        if _is_active_download_artifact(file_path_obj):
            return False

        # Always ignore Fylorra internal trash/state folders and OS recycle bins to prevent recursion/loops.
        try:
            parts_lower = {p.lower() for p in file_path_obj.parts}
            if ".fylorra_trash" in parts_lower or "$recycle.bin" in parts_lower or "system volume information" in parts_lower:
                return False
            # Ignore app-level trash folder (used when send2trash isn't available).
            app_trash = (Path.home() / APP_DATA_DIR_NAME / "trash").resolve()
            try:
                if app_trash in file_path_obj.resolve().parents:
                    return False
            except Exception:
                pass
        except Exception:
            pass

        # File size filter
        if self.min_size_kb is not None or self.max_size_kb is not None:
            try:
                if file_path_obj.exists():
                    file_size_kb = file_path_obj.stat().st_size / 1024

                    if self.min_size_kb is not None and file_size_kb < self.min_size_kb:
                        return False
                    if self.max_size_kb is not None and file_size_kb > self.max_size_kb:
                        return False
            except (OSError, IOError):
                # File might not exist yet or can't access, let it pass
                pass

        # Date filter (modified within X days)
        if self.modified_within_days is not None and self.modified_within_days > 0:
            try:
                if file_path_obj.exists():
                    modified_time = datetime.fromtimestamp(file_path_obj.stat().st_mtime)
                    cutoff_time = datetime.now() - timedelta(days=self.modified_within_days)

                    if modified_time < cutoff_time:
                        return False
            except (OSError, IOError):
                # File might not exist yet or can't access, let it pass
                pass

        # Exclude patterns (.gitignore style)
        exclude_patterns = self._normalized_exclude_patterns()
        if exclude_patterns:
            try:
                relative_path = str(file_path_obj.relative_to(Path(self.path)))
            except Exception:
                relative_path = file_name
            relative_path_posix = relative_path.replace("\\", "/")
            path_parts = {p.lower() for p in Path(relative_path).parts}

            for pattern in exclude_patterns:
                pattern_posix = pattern.replace("\\", "/")
                # Support both file name patterns and directory patterns
                if (
                    fnmatch.fnmatch(file_name, pattern)
                    or fnmatch.fnmatch(relative_path, pattern)
                    or fnmatch.fnmatch(relative_path_posix, pattern_posix)
                ):
                    return False
                # Support directory exclusions (e.g., node_modules/)
                if pattern_posix.endswith('/') and (pattern_posix[:-1].lower() in path_parts):
                    return False
                # Plain folder names such as "node_modules" should exclude that folder anywhere.
                if not any(ch in pattern for ch in "*?[]/\\") and pattern.lower() in path_parts:
                    return False

        # Filename regex pattern
        if self.filename_regex:
            try:
                if not re.search(self.filename_regex, file_name):
                    return False
            except re.error:
                # Invalid regex, ignore filter
                pass

        return True

    def _normalized_exclude_patterns(self) -> List[str]:
        raw = self.exclude_patterns or []
        if isinstance(raw, str):
            parts = []
            for chunk in raw.replace("\r", "\n").replace(",", "\n").split("\n"):
                chunk = chunk.strip()
                if chunk and not chunk.startswith("#"):
                    parts.append(chunk)
            return parts
        patterns = []
        try:
            iterator = list(raw)
        except Exception:
            iterator = []
        for item in iterator:
            value = str(item or "").strip()
            if value and not value.startswith("#"):
                patterns.append(value)
        return patterns

    def _rule_matches(self, rule: Dict, event_type: str, file_name: str, file_ext: str) -> bool:
        """Check if a rule matches the current event"""
        action_type = str(rule.get("action_type") or "").strip().lower()
        if action_type in {"move", "organize"} and event_type != "created":
            return False

        # Check event type
        if action_type not in {"move", "organize"} and rule.get("event_types") and event_type not in rule["event_types"]:
            return False

        # Check file extension filter
        if rule.get("file_extensions"):
            exts = []
            for ext in (rule.get("file_extensions") or []):
                value = str(ext or "").lower().strip()
                if value and value not in {"*", ".*"} and not value.startswith("."):
                    value = "." + value
                if value:
                    exts.append(value)
            if "*" not in exts and ".*" not in exts:
                if file_ext.lower() not in exts:
                    return False

        # Check file name pattern
        if rule.get("name_pattern"):
            import re
            try:
                if not re.search(rule["name_pattern"], file_name):
                    return False
            except re.error as e:
                try:
                    self.logger.log_error("rule_match", f"Invalid rule name pattern: {e}")
                except Exception:
                    pass
                return False

        return True

    def _send_notification(self, event_type: str, file_name: str, file_path: str):
        """Send Windows notification and email for the event"""
        # Check if this event type should trigger notifications
        should_notify = False
        if event_type == "created" and self.notify_created:
            should_notify = True
        elif event_type == "modified" and self.notify_modified:
            should_notify = True
        elif event_type == "deleted" and self.notify_deleted:
            should_notify = True
        elif event_type == "moved" and self.notify_moved:
            should_notify = True

        if not should_notify:
            return

        # Send Windows notification
        title_map = {
            "created": "📁 New File Detected",
            "modified": "✏️ File Modified",
            "deleted": "🗑️ File Deleted",
            "moved": "📦 File Moved"
        }

        title = title_map.get(event_type, "📂 File Event")
        message = f"{file_name}\n{file_path}"

        self.notification_manager.send_notification(title, message)

        # Send email notification if configured
        if self.email_recipient and self.email_notifier:
            try:
                self.email_notifier.send_notification(
                    self.email_recipient,
                    event_type,
                    file_name,
                    file_path,
                    self.path
                )
            except Exception as e:
                self.logger.log_error("email_notification", f"Failed to send email: {e}")


class MonitorManager:
    """Manages all folder monitors (local, network, and FTP)"""

    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.monitors: Dict[str, FolderMonitor] = {}
        self.ftp_manager = FTPMonitorManager()
        self.notification_manager = NotificationManager()
        self.action_engine = ActionEngine()
        self._cloud_sync_manager = None
        self.logger = ActivityLogger(settings_manager)
        self.analytics_manager = AnalyticsManager(settings_manager)
        self.event_callbacks: List[Callable] = []
        self.email_notifier = None
        self.last_error = ""
        try:
            for msg in self.settings_manager.quarantine_legacy_unsafe_cleanup_tasks():
                self.logger.log_event("safety", "Legacy FlowGuard", "quarantine", msg, "")
        except Exception:
            pass
        self._init_email_notifier()
        self.scheduled_tasks = ScheduledTaskManager(
            load_tasks=self.settings_manager.load_scheduled_tasks,
            save_tasks=self.settings_manager.save_scheduled_tasks,
            run_action=self._run_scheduled_action,
            log=lambda m: self.logger.log_event("scheduled", "Scheduled", "task", m, ""),
        )

    def _get_cloud_sync_manager(self):
        if self._cloud_sync_manager is not None:
            return self._cloud_sync_manager
        from core.cloud_sync import CloudSyncManager

        self._cloud_sync_manager = CloudSyncManager(settings_manager=self.settings_manager)
        return self._cloud_sync_manager

    def _run_scheduled_action(self, action_type: str, target_path: str, action_params: Dict) -> bool:
        """
        Router for scheduled tasks.
        - Most actions run through ActionEngine.
        - Cloud sync actions are handled here so they can run from Scheduled Tasks.
        """
        at = str(action_type or "").strip().lower()
        if at == "cloud_sync_upload_only":
            try:
                provider = str((action_params or {}).get("provider") or "").strip().lower()
                remote_base = str((action_params or {}).get("remote_base") or DEFAULT_CLOUD_SYNC_FOLDER).strip()
                include_subfolders = bool((action_params or {}).get("include_subfolders", True))
                dry_run = bool((action_params or {}).get("dry_run", False))
                max_files = int((action_params or {}).get("max_files", 200_000))

                mgr = self._get_cloud_sync_manager()
                p = mgr.provider(provider)  # type: ignore[attr-defined]
                if not p or not getattr(p, "is_connected", lambda: False)():
                    raise RuntimeError(f"{provider} is not connected.")

                from core.cloud_sync.sync_engine import sync_folder_upload_only

                def _log_status(msg: str):
                    try:
                        self.logger.log_event("scheduled", "CloudSync", "status", msg, "")
                    except Exception:
                        pass

                def _log_progress(done: int, total: int, msg: str):
                    # Keep logs light; only emit occasionally.
                    try:
                        if total and (done % 50) == 0:
                            self.logger.log_event("scheduled", "CloudSync", "progress", f"{done}/{total} {msg}", "")
                    except Exception:
                        pass

                sync_folder_upload_only(
                    p,
                    local_root=Path(str(target_path or "").strip()),
                    remote_base=remote_base,
                    include_subfolders=include_subfolders,
                    dry_run=dry_run,
                    max_files=max_files,
                    status_cb=_log_status,
                    progress_cb=_log_progress,
                )
                return True
            except Exception as e:
                try:
                    self.logger.log_error("scheduled_cloud_sync", str(e))
                except Exception:
                    pass
                return False

        if at in ("cloud_sync_download_only", "cloud_sync_two_way"):
            try:
                provider = str((action_params or {}).get("provider") or "").strip().lower()
                remote_base = str((action_params or {}).get("remote_base") or DEFAULT_CLOUD_SYNC_FOLDER).strip()
                include_subfolders = bool((action_params or {}).get("include_subfolders", True))
                dry_run = bool((action_params or {}).get("dry_run", False))
                max_files = int((action_params or {}).get("max_files", 200_000))
                delete_policy = str((action_params or {}).get("delete_policy") or "ignore").strip().lower()
                conflict_policy = str((action_params or {}).get("conflict_policy") or "keep_both").strip().lower()

                mgr = self._get_cloud_sync_manager()
                p = mgr.provider(provider)  # type: ignore[attr-defined]
                if not p or not getattr(p, "is_connected", lambda: False)():
                    raise RuntimeError(f"{provider} is not connected.")

                from core.cloud_sync.sync_engine import sync_folder_download_only, sync_folder_two_way

                def _log_status(msg: str):
                    try:
                        self.logger.log_event("scheduled", "CloudSync", "status", msg, "")
                    except Exception:
                        pass

                def _log_progress(done: int, total: int, msg: str):
                    try:
                        if total and (done % 50) == 0:
                            self.logger.log_event("scheduled", "CloudSync", "progress", f"{done}/{total} {msg}", "")
                    except Exception:
                        pass

                if at == "cloud_sync_download_only":
                    sync_folder_download_only(
                        p,
                        local_root=Path(str(target_path or "").strip()),
                        remote_base=remote_base,
                        include_subfolders=include_subfolders,
                        dry_run=dry_run,
                        max_files=max_files,
                        delete_policy=delete_policy if delete_policy in ("ignore", "mirror") else "ignore",
                        status_cb=_log_status,
                        progress_cb=_log_progress,
                    )
                else:
                    sync_folder_two_way(
                        p,
                        local_root=Path(str(target_path or "").strip()),
                        remote_base=remote_base,
                        include_subfolders=include_subfolders,
                        dry_run=dry_run,
                        max_files=max_files,
                        delete_policy=delete_policy if delete_policy in ("ignore", "mirror") else "ignore",
                        conflict_policy=conflict_policy
                        if conflict_policy in ("keep_both", "prefer_local", "prefer_remote")
                        else "keep_both",
                        status_cb=_log_status,
                        progress_cb=_log_progress,
                    )
                return True
            except Exception as e:
                try:
                    self.logger.log_error("scheduled_cloud_sync", str(e))
                except Exception:
                    pass
                return False

        params = dict(action_params or {})
        if at == "clean_folder":
            params.setdefault("use_recycle_bin", True)
            params.setdefault("include_subfolders", True)
            params.setdefault("skip_active_downloads", True)
            params.setdefault("min_age_seconds", 604800)
        return bool(self.action_engine.execute_action(at, str(target_path or ""), params))

    def start_scheduled_tasks(self):
        try:
            self.scheduled_tasks.start()
        except Exception:
            pass

    def stop_scheduled_tasks(self):
        try:
            self.scheduled_tasks.stop()
        except Exception:
            pass

    def add_scheduled_task(self, task: Dict) -> bool:
        """
        Add or update a scheduled task.
        Expected keys: title, schedule, action_type, action_params, target_path
        """
        try:
            task_id = str(task.get("task_id") or "")
            if not task_id:
                import uuid
                task_id = f"task_{uuid.uuid4().hex[:10]}"
            action_type = str(task.get("action_type") or "")
            action_params = dict(task.get("action_params") or {})
            if action_type.strip().lower() == "clean_folder":
                action_params.setdefault("use_recycle_bin", True)
                action_params.setdefault("include_subfolders", True)
                action_params.setdefault("skip_active_downloads", True)
                action_params.setdefault("min_age_seconds", 604800)
            st = ScheduledTask(
                task_id=task_id,
                title=str(task.get("title") or "Scheduled Task"),
                schedule=dict(task.get("schedule") or {}),
                action_type=action_type,
                action_params=action_params,
                target_path=str(task.get("target_path") or ""),
                enabled=bool(task.get("enabled", True)),
            )
            self.scheduled_tasks.upsert_task(st)
            return True
        except Exception as e:
            self.logger.log_error("scheduled_task", str(e))
            return False

    def _init_email_notifier(self):
        """Initialize email notifier with current SMTP settings"""
        from utils.email_notifier import EmailNotifier

        smtp_settings = {
            "smtp_server": self.settings_manager.get_setting("smtp_server", ""),
            "smtp_port": self.settings_manager.get_setting("smtp_port", 587),
            "smtp_username": self.settings_manager.get_setting("smtp_username", ""),
            "smtp_password": self.settings_manager.get_setting("smtp_password", ""),
            "sender_email": self.settings_manager.get_setting("sender_email", "")
        }

        self.email_notifier = EmailNotifier(smtp_settings)

        # Update all existing monitors with the new email notifier
        for monitor in self.monitors.values():
            monitor.email_notifier = self.email_notifier

    def validate_monitor_config(
        self,
        path: str,
        rules: List[Dict] = None,
        *,
        filename_regex: str = None,
        min_size_kb: int = None,
        max_size_kb: int = None,
        exclude_patterns: List[str] = None,
    ) -> List[str]:
        """Return user-facing problems that make a monitor unsafe or invalid."""
        problems: List[str] = []
        raw_path = str(path or "").strip()
        if not raw_path:
            return ["Choose a folder to monitor."]

        path_obj = Path(raw_path).expanduser()
        if raw_path.startswith("\\\\"):
            if not os.path.exists(raw_path):
                problems.append(f"Network path is not accessible: {raw_path}")
        else:
            if not path_obj.exists():
                problems.append(f"Folder does not exist: {path_obj}")
            elif not path_obj.is_dir():
                problems.append(f"Monitor path must be a folder: {path_obj}")

        if not problems and _is_protected_monitor_path(path_obj):
            problems.append(f"Refusing to monitor protected folder: {path_obj}")

        if filename_regex:
            try:
                import re

                re.compile(str(filename_regex))
            except Exception as e:
                problems.append(f"Filename regex is invalid: {e}")

        try:
            min_size = int(min_size_kb) if min_size_kb is not None else None
            max_size = int(max_size_kb) if max_size_kb is not None else None
            if min_size is not None and min_size < 0:
                problems.append("Minimum file size cannot be negative.")
            if max_size is not None and max_size < 0:
                problems.append("Maximum file size cannot be negative.")
            if min_size is not None and max_size is not None and min_size > max_size:
                problems.append("Minimum file size cannot be larger than maximum file size.")
        except Exception:
            problems.append("File size filters must be valid numbers.")

        for pattern in self._normalize_filter_patterns(exclude_patterns):
            if pattern in {"*", "*.*"}:
                problems.append("Exclude pattern '*' would ignore every file.")
                break

        watched = path_obj
        supported_actions = set(getattr(self.action_engine, "action_handlers", {}).keys()) | {"cloud_upload"}
        allowed_events = {"created", "modified", "deleted", "moved"}
        for idx, rule in enumerate(list(rules or []), start=1):
            if not isinstance(rule, dict):
                problems.append(f"Rule {idx} is not valid.")
                continue
            action_type = str(rule.get("action_type") or "").strip().lower()
            if not action_type:
                problems.append(f"Rule {idx} is missing an action.")
                continue
            if action_type not in supported_actions:
                problems.append(f"Rule {idx} uses an unsupported action: {action_type}")
            params = rule.get("action_params") or {}
            if not isinstance(params, dict):
                problems.append(f"Rule {idx} action settings are not valid.")
                continue
            events = rule.get("event_types") or []
            if isinstance(events, str):
                events = [events]
            try:
                bad_events = [str(e) for e in list(events) if str(e) not in allowed_events]
            except Exception:
                bad_events = ["<invalid>"]
            if bad_events:
                problems.append(f"Rule {idx} has unsupported event type(s): {', '.join(bad_events)}")
            name_pattern = str(rule.get("name_pattern") or "").strip()
            if name_pattern:
                try:
                    import re

                    re.compile(name_pattern)
                except Exception as e:
                    problems.append(f"Rule {idx} name pattern is invalid: {e}")
            file_exts = rule.get("file_extensions") or []
            if isinstance(file_exts, str):
                file_exts = [file_exts]
            try:
                for ext in list(file_exts):
                    value = str(ext or "").strip().lstrip(".")
                    if not value or value == "*":
                        continue
                    if any(ch in value for ch in "/\\:*?\"<>|\r\n"):
                        problems.append(f"Rule {idx} has an invalid file extension filter: {ext}")
                        break
            except Exception:
                problems.append(f"Rule {idx} file extension filters are not valid.")
            if action_type in {"copy", "move", "organize"}:
                dest = str(params.get("destination") or "").strip()
                if not dest and action_type in {"copy", "move"}:
                    problems.append(f"Rule {idx} needs a destination folder.")
                    continue
                if dest:
                    dest_path = Path(dest).expanduser()
                    if _same_or_inside(dest_path, watched):
                        problems.append(
                            f"Rule {idx} sends files inside the watched folder. "
                            "Choose a destination outside the monitor to prevent automation loops."
                        )
            if action_type == "execute":
                command = str(params.get("command") or "").strip()
                command_list = params.get("command_list")
                if not command and not (isinstance(command_list, list) and command_list):
                    problems.append(f"Rule {idx} needs a command to execute.")
                if bool(params.get("use_shell", False)) and not bool(params.get("allow_shell_execution", False)):
                    problems.append(
                        f"Rule {idx} uses shell execution. Turn on allow_shell_execution only for commands you fully trust."
                    )
        return problems

    def _normalize_filter_patterns(self, raw) -> List[str]:
        if not raw:
            return []
        if isinstance(raw, str):
            chunks = raw.replace("\r", "\n").replace(",", "\n").split("\n")
        else:
            try:
                chunks = list(raw)
            except Exception:
                chunks = []
        return [
            str(item or "").strip()
            for item in chunks
            if str(item or "").strip() and not str(item or "").strip().startswith("#")
        ]

    def _normalize_rules_for_runtime(self, rules: List[Dict]) -> List[Dict]:
        normalized: List[Dict] = []
        for raw in list(rules or []):
            if not isinstance(raw, dict):
                continue
            rule = dict(raw)
            action_type = str(rule.get("action_type") or "").strip().lower()
            rule["action_type"] = action_type
            if action_type in {"move", "organize"}:
                rule["event_types"] = ["created"]
            else:
                events = rule.get("event_types") or ["created"]
                if isinstance(events, str):
                    events = [events]
                allowed = {"created", "modified", "deleted", "moved"}
                clean_events = [str(e).strip().lower() for e in events if str(e).strip().lower() in allowed]
                rule["event_types"] = clean_events or ["created"]

            exts = rule.get("file_extensions") or ["*"]
            if isinstance(exts, str):
                exts = [exts]
            clean_exts = []
            seen = set()
            for ext in list(exts):
                value = str(ext or "").strip().lower()
                if not value:
                    continue
                if value in {"*", ".*"}:
                    clean_exts = ["*"]
                    break
                if not value.startswith("."):
                    value = "." + value.lstrip(".")
                if value not in seen:
                    seen.add(value)
                    clean_exts.append(value)
            rule["file_extensions"] = clean_exts or ["*"]
            params = rule.get("action_params") or {}
            rule["action_params"] = dict(params) if isinstance(params, dict) else {}
            normalized.append(rule)
        return normalized

    def add_monitor(self, monitor_id: str, path: str, rules: List[Dict],
                   notify_created: bool = True, notify_modified: bool = True,
                   notify_deleted: bool = True, notify_moved: bool = True,
                   email_recipient: str = "",
                   min_size_kb: int = None, max_size_kb: int = None,
                   modified_within_days: int = None,
                   exclude_patterns: List[str] = None,
                   filename_regex: str = None,
                   action_delay_seconds: Union[int, float] = 0,
                   action_stability_seconds: Union[int, float] = 0) -> bool:
        """Add a new folder monitor"""
        try:
            self.last_error = ""
            if monitor_id in self.monitors:
                raise ValueError(f"Monitor with ID {monitor_id} already exists")
            path = str(Path(str(path)).expanduser())
            rules = self._normalize_rules_for_runtime(rules)
            problems = self.validate_monitor_config(
                path,
                rules,
                filename_regex=filename_regex,
                min_size_kb=min_size_kb,
                max_size_kb=max_size_kb,
                exclude_patterns=exclude_patterns,
            )
            if problems:
                raise ValueError("; ".join(problems))

            monitor = FolderMonitor(
                monitor_id,
                path,
                rules,
                self.notification_manager,
                self.action_engine,
                self._get_cloud_sync_manager(),
                self.logger,
                self._on_monitor_event,
                notify_created,
                notify_modified,
                notify_deleted,
                notify_moved,
                email_recipient,
                self.email_notifier,
                self.analytics_manager,
                min_size_kb,
                max_size_kb,
                modified_within_days,
                exclude_patterns,
                filename_regex,
                action_delay_seconds,
                action_stability_seconds
            )

            self.monitors[monitor_id] = monitor
            self.logger.log_monitor_event("added", monitor_id, path,
                                         f"Rules: {len(rules)}")
            return True

        except Exception as e:
            self.last_error = str(e)
            self.logger.log_error("add_monitor", str(e))
            print(f"Error adding monitor: {e}")
            return False

    def start_monitor(self, monitor_id: str) -> bool:
        """Start a specific monitor"""
        try:
            self.last_error = ""
            if monitor_id not in self.monitors:
                self.last_error = f"Monitor not found: {monitor_id}"
                return False

            self.monitors[monitor_id].start()
            return True

        except Exception as e:
            self.last_error = str(e)
            try:
                self.logger.log_error("start_monitor", str(e))
            except Exception:
                pass
            print(f"Error starting monitor: {e}")
            return False

    def stop_monitor(self, monitor_id: str) -> bool:
        """Stop a specific monitor"""
        try:
            if monitor_id not in self.monitors:
                return False

            self.monitors[monitor_id].stop()
            return True

        except Exception as e:
            print(f"Error stopping monitor: {e}")
            return False

    def remove_monitor(self, monitor_id: str) -> bool:
        """Remove a monitor"""
        try:
            if monitor_id in self.monitors:
                path = self.monitors[monitor_id].path
                self.stop_monitor(monitor_id)
                del self.monitors[monitor_id]
                self.logger.log_monitor_event("removed", monitor_id, path)
            return True

        except Exception as e:
            self.logger.log_error("remove_monitor", str(e))
            print(f"Error removing monitor: {e}")
            return False

    def get_monitor(self, monitor_id: str) -> FolderMonitor:
        """Get a specific monitor"""
        return self.monitors.get(monitor_id)

    def get_all_monitors(self) -> Dict[str, FolderMonitor]:
        """Get all monitors"""
        return self.monitors

    def stop_all_monitors(self):
        """Stop all running monitors"""
        for monitor in self.monitors.values():
            if monitor.is_running:
                monitor.stop()

        # Stop all FTP monitors
        self.ftp_manager.stop_all()

    def add_event_callback(self, callback: Callable):
        """Add a callback for monitor events"""
        self.event_callbacks.append(callback)

    def _on_monitor_event(self, monitor_id: str, event_type: str,
                          src_path: str, dest_path: str = None):
        """Internal event handler that forwards to all callbacks"""
        for callback in self.event_callbacks:
            try:
                callback(monitor_id, event_type, src_path, dest_path)
            except Exception as e:
                print(f"Error in event callback: {e}")

    def save_monitors(self):
        """Save all monitors to settings"""
        monitors_data = []

        # Save folder monitors
        for monitor_id, monitor in self.monitors.items():
            monitors_data.append({
                "type": "folder",
                "id": monitor_id,
                "path": monitor.path,
                "rules": monitor.rules,
                "is_running": monitor.is_running,
                "stats": monitor.stats,
                "notify_created": monitor.notify_created,
                "notify_modified": monitor.notify_modified,
                "notify_deleted": monitor.notify_deleted,
                "notify_moved": monitor.notify_moved,
                "email_recipient": monitor.email_recipient,
                "action_delay_seconds": getattr(monitor, "action_delay_seconds", 0),
                "action_stability_seconds": getattr(monitor, "action_stability_seconds", 0),
                # Advanced filters
                "min_size_kb": monitor.min_size_kb,
                "max_size_kb": monitor.max_size_kb,
                "modified_within_days": monitor.modified_within_days,
                "exclude_patterns": monitor.exclude_patterns,
                "filename_regex": monitor.filename_regex
            })

        # Save FTP monitors
        for monitor_id, ftp_monitor in self.ftp_manager.ftp_monitors.items():
            monitors_data.append({
                "type": "ftp",
                "id": monitor_id,
                "host": ftp_monitor.host,
                "port": ftp_monitor.port,
                "username": ftp_monitor.username,
                "password": ftp_monitor.password,
                "remote_path": ftp_monitor.remote_path,
                "use_tls": ftp_monitor.use_tls,
                "tls_implicit": bool(getattr(ftp_monitor, "tls_implicit", False)),
                "passive_mode": bool(getattr(ftp_monitor, "passive_mode", True)),
                "encoding": getattr(ftp_monitor, "encoding", "utf-8"),
                "poll_interval": ftp_monitor.poll_interval,
                "two_way_sync": bool(getattr(ftp_monitor, "two_way_sync", False)),
                "sync_subfolders": bool(getattr(ftp_monitor, "sync_subfolders", False)),
                "local_sync_dir": getattr(ftp_monitor, "local_sync_dir", None),
                "download_on_created": bool(getattr(ftp_monitor, "download_on_created", True)),
                "download_on_modified": bool(getattr(ftp_monitor, "download_on_modified", True)),
                "delete_local_on_deleted": bool(getattr(ftp_monitor, "delete_local_on_deleted", False)),
                "overwrite_local": bool(getattr(ftp_monitor, "overwrite_local", False)),
                "allowed_extensions": list(getattr(ftp_monitor, "allowed_extensions", []) or []),
                "is_running": ftp_monitor.is_running,
                "stats": ftp_monitor.stats
            })

        self.settings_manager.save_monitors(monitors_data)
        self.logger.log_monitor_event("saved", "all", "All monitors",
                                     f"Saved {len(monitors_data)} monitors")

    def load_monitors(self):
        """Load monitors from settings and return them for UI creation"""
        monitors_data = self.settings_manager.load_monitors()
        loaded_monitors = []

        for data in monitors_data:
            try:
                monitor_type = data.get("type", "folder")
            except Exception:
                monitor_type = "folder"

            if monitor_type == "folder":
                # Add folder monitor
                mon_id = data.get("id")
                path = data.get("path")
                if not mon_id or not path:
                    try:
                        self.logger.log_error("load_monitors", f"Skipped invalid folder monitor entry: {data}")
                    except Exception:
                        pass
                    continue
                try:
                    success = self.add_monitor(
                        mon_id,
                        path,
                        data.get("rules", []),
                        data.get("notify_created", True),
                        data.get("notify_modified", True),
                        data.get("notify_deleted", True),
                        data.get("notify_moved", True),
                        data.get("email_recipient", ""),
                        data.get("min_size_kb"),
                        data.get("max_size_kb"),
                        data.get("modified_within_days"),
                        data.get("exclude_patterns"),
                        data.get("filename_regex"),
                        data.get("action_delay_seconds", 0),
                        data.get("action_stability_seconds", 0)
                    )
                except Exception as e:
                    try:
                        self.logger.log_error("load_monitors", f"Folder monitor load failed ({mon_id}): {e}")
                    except Exception:
                        pass
                    continue

                if success:
                    loaded_monitors.append({
                        "type": "folder",
                        "id": mon_id,
                        "path": path,
                        "rules": data.get("rules", []),
                        "auto_start": data.get("is_running", False),
                        "notify_created": data.get("notify_created", True),
                        "notify_modified": data.get("notify_modified", True),
                        "notify_deleted": data.get("notify_deleted", True),
                        "notify_moved": data.get("notify_moved", True),
                        "email_recipient": data.get("email_recipient", ""),
                        "action_delay_seconds": data.get("action_delay_seconds", 0),
                        "action_stability_seconds": data.get("action_stability_seconds", 0),
                        "min_size_kb": data.get("min_size_kb"),
                        "max_size_kb": data.get("max_size_kb"),
                        "modified_within_days": data.get("modified_within_days"),
                        "exclude_patterns": data.get("exclude_patterns"),
                        "filename_regex": data.get("filename_regex")
                    })

            elif monitor_type == "ftp":
                # Add FTP monitor
                mon_id = data.get("id")
                host = data.get("host")
                remote_path = data.get("remote_path")
                if not mon_id or not host or not remote_path:
                    try:
                        self.logger.log_error("load_monitors", f"Skipped invalid FTP monitor entry: {data}")
                    except Exception:
                        pass
                    continue
                try:
                    success = self.ftp_manager.add_ftp_monitor(
                        mon_id,
                        host,
                        data.get("username", ""),
                        data.get("password", ""),
                        remote_path,
                        int(data.get("port", 21) or 21),
                        data.get("use_tls", False),
                        data.get("poll_interval", 30),
                        self._on_monitor_event,
                        local_sync_dir=data.get("local_sync_dir"),
                        download_on_created=bool(data.get("download_on_created", True)),
                        download_on_modified=bool(data.get("download_on_modified", True)),
                        delete_local_on_deleted=bool(data.get("delete_local_on_deleted", False)),
                        overwrite_local=bool(data.get("overwrite_local", False)),
                        allowed_extensions=data.get("allowed_extensions") or None,
                        passive_mode=bool(data.get("passive_mode", True)),
                        tls_implicit=bool(data.get("tls_implicit", False)),
                        encoding=str(data.get("encoding", "utf-8") or "utf-8"),
                        two_way_sync=bool(data.get("two_way_sync", False)),
                        sync_subfolders=bool(data.get("sync_subfolders", False)),
                    )
                except Exception as e:
                    try:
                        self.logger.log_error("load_monitors", f"FTP monitor load failed ({mon_id}): {e}")
                    except Exception:
                        pass
                    continue

                if success:
                    loaded_monitors.append({
                        "type": "ftp",
                        "id": mon_id,
                        "host": host,
                        "port": int(data.get("port", 21) or 21),
                        "username": data.get("username", ""),
                        "password": data.get("password", ""),
                        "remote_path": remote_path,
                        "use_tls": data.get("use_tls", False),
                        "tls_implicit": data.get("tls_implicit", False),
                        "passive_mode": data.get("passive_mode", True),
                        "encoding": data.get("encoding", "utf-8"),
                        "poll_interval": data.get("poll_interval", 30),
                        "two_way_sync": bool(data.get("two_way_sync", False)),
                        "sync_subfolders": bool(data.get("sync_subfolders", False)),
                        "local_sync_dir": data.get("local_sync_dir"),
                        "auto_start": data.get("is_running", False)
                    })

        self.logger.log_monitor_event("loaded", "all", "All monitors",
                                     f"Loaded {len(loaded_monitors)} monitors")

        return loaded_monitors
