"""
Fylorra - Scheduled Tasks

Provides simple, cross-platform time-based automation that runs while the app is open.

Why:
- Folder monitoring is event-based (created/modified/deleted/moved).
- Some user requests are time-based (e.g., "clean temp folder every day at 12:00 AM").

This module is intentionally dependency-free (no APScheduler) to keep packaging simple.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


def _parse_daily_time(value: str) -> tuple[int, int] | None:
    """
    Accepts:
    - "00:00"
    - "0:00"
    - "12:00 AM"
    - "12:00PM"
    """
    s = (value or "").strip().lower()
    if not s:
        return None
    s = " ".join(s.split())
    ampm = None
    if s.endswith("am"):
        ampm = "am"
        s = s[:-2].strip()
    elif s.endswith("pm"):
        ampm = "pm"
        s = s[:-2].strip()

    if ":" not in s:
        return None
    hh_s, mm_s = s.split(":", 1)
    try:
        hh = int(hh_s.strip())
        mm = int(mm_s.strip())
    except Exception:
        return None
    if not (0 <= mm <= 59):
        return None
    if ampm:
        if hh == 12:
            hh = 0
        if ampm == "pm":
            hh += 12
    if not (0 <= hh <= 23):
        return None
    return hh, mm


def _next_daily_run(hh: int, mm: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    run = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if run <= now:
        run = run + timedelta(days=1)
    return run


def _parse_time_list(value: object) -> list[tuple[int, int]]:
    """
    Returns a normalized list of (hh, mm) tuples.
    Accepts:
    - "08:00"
    - "08:00, 16:00"
    - ["08:00", "16:00"]
    """
    out: list[tuple[int, int]] = []
    parts: list[str] = []
    if isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        s = str(value or "").strip()
        if s:
            parts = [p.strip() for p in s.split(",")]
    for p in parts:
        tm = _parse_daily_time(p)
        if not tm:
            continue
        if tm not in out:
            out.append(tm)
    out.sort()
    return out


def _parse_once_datetime(value: object) -> datetime | None:
    """
    Parses a one-off run datetime.
    Accepts:
    - datetime object
    - "YYYY-MM-DD HH:MM"
    - ISO strings from datetime.isoformat()
    """
    if isinstance(value, datetime):
        return value.replace(second=0, microsecond=0)
    s = str(value or "").strip()
    if not s:
        return None
    # ISO first.
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(second=0, microsecond=0)
    except Exception:
        pass
    # Friendly format.
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return dt.replace(second=0, microsecond=0)
    except Exception:
        return None


@dataclass
class ScheduledTask:
    task_id: str
    title: str
    schedule: dict[str, Any]  # {"type":"daily","time":"00:00"}
    action_type: str
    action_params: dict[str, Any]
    target_path: str
    enabled: bool = True
    last_run_iso: str | None = None

    def next_run(self, now: datetime | None = None) -> datetime | None:
        if not self.enabled:
            return None
        now = now or datetime.now()
        stype = (self.schedule.get("type") or "").strip().lower()
        if stype == "daily":
            times = _parse_time_list(self.schedule.get("times") or self.schedule.get("time") or "")
            if not times:
                return None
            candidates: list[datetime] = []
            for hh, mm in times:
                candidates.append(_next_daily_run(hh, mm, now=now))
            return min(candidates) if candidates else None
        if stype == "weekly":
            times = _parse_time_list(self.schedule.get("times") or self.schedule.get("time") or "")
            if not times:
                return None
            days = self.schedule.get("days") or []
            try:
                days_i = sorted({int(d) for d in days})
            except Exception:
                days_i = []
            days_i = [d for d in days_i if 0 <= d <= 6]
            if not days_i:
                return None
            # Find next (day,time) in the coming 7 days.
            candidates: list[datetime] = []
            for add in range(0, 8):
                dt = (now + timedelta(days=add)).replace(second=0, microsecond=0)
                if dt.weekday() not in days_i:
                    continue
                for hh, mm in times:
                    cand = dt.replace(hour=hh, minute=mm)
                    if cand > now:
                        candidates.append(cand)
                if candidates:
                    break
            return min(candidates) if candidates else None
        if stype == "once":
            dt = _parse_once_datetime(self.schedule.get("datetime") or self.schedule.get("at") or "")
            if not dt:
                return None
            return dt if dt > now else None
        return None

    def most_recent_due(self, now: datetime | None = None) -> datetime | None:
        """
        Returns the most recent scheduled run time that is <= now.
        Used by the scheduler to avoid missing runs if the app was busy/asleep.
        """
        if not self.enabled:
            return None
        now = now or datetime.now()
        stype = (self.schedule.get("type") or "").strip().lower()
        if stype == "daily":
            times = _parse_time_list(self.schedule.get("times") or self.schedule.get("time") or "")
            if not times:
                return None
            candidates: list[datetime] = []
            for hh, mm in times:
                base_today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if base_today <= now:
                    candidates.append(base_today)
                else:
                    candidates.append(base_today - timedelta(days=1))
            return max(candidates) if candidates else None
        if stype == "weekly":
            times = _parse_time_list(self.schedule.get("times") or self.schedule.get("time") or "")
            if not times:
                return None
            days = self.schedule.get("days") or []
            try:
                days_i = sorted({int(d) for d in days})
            except Exception:
                days_i = []
            days_i = [d for d in days_i if 0 <= d <= 6]
            if not days_i:
                return None
            candidates: list[datetime] = []
            # Look back up to 7 days for the most recent matching (day,time).
            for back in range(0, 8):
                dt = (now - timedelta(days=back)).replace(second=0, microsecond=0)
                if dt.weekday() not in days_i:
                    continue
                for hh, mm in times:
                    cand = dt.replace(hour=hh, minute=mm)
                    if cand <= now:
                        candidates.append(cand)
            return max(candidates) if candidates else None
        if stype == "once":
            dt = _parse_once_datetime(self.schedule.get("datetime") or self.schedule.get("at") or "")
            if not dt:
                return None
            return dt if dt <= now else None
        return None


class ScheduledTaskManager:
    def __init__(
        self,
        *,
        load_tasks: Callable[[], list[dict[str, Any]]],
        save_tasks: Callable[[list[dict[str, Any]]], None],
        run_action: Callable[[str, str, dict[str, Any]], bool],
        log: Callable[[str], None] | None = None,
    ):
        self._load_tasks = load_tasks
        self._save_tasks = save_tasks
        self._run_action = run_action
        self._log = log or (lambda _m: None)

        self._lock = threading.Lock()
        self._tasks: list[ScheduledTask] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        self.reload()

    def reload(self) -> None:
        with self._lock:
            raw = self._load_tasks() or []
            tasks: list[ScheduledTask] = []
            for d in raw:
                if not isinstance(d, dict):
                    continue
                try:
                    tasks.append(
                        ScheduledTask(
                            task_id=str(d.get("task_id") or ""),
                            title=str(d.get("title") or "Scheduled Task"),
                            schedule=dict(d.get("schedule") or {}),
                            action_type=str(d.get("action_type") or ""),
                            action_params=dict(d.get("action_params") or {}),
                            target_path=str(d.get("target_path") or ""),
                            enabled=bool(d.get("enabled", True)),
                            last_run_iso=(str(d.get("last_run_iso")) if d.get("last_run_iso") else None),
                        )
                    )
                except Exception:
                    continue
            self._tasks = [t for t in tasks if t.task_id and t.action_type and t.target_path]

    def list_tasks(self) -> list[ScheduledTask]:
        with self._lock:
            return list(self._tasks)

    def upsert_task(self, task: ScheduledTask) -> None:
        with self._lock:
            replaced = False
            for i, t in enumerate(self._tasks):
                if t.task_id == task.task_id:
                    self._tasks[i] = task
                    replaced = True
                    break
            if not replaced:
                self._tasks.append(task)
            self._persist_locked()

    def delete_task(self, task_id: str) -> None:
        with self._lock:
            self._tasks = [t for t in self._tasks if t.task_id != task_id]
            self._persist_locked()

    def run_now(self, task_id: str) -> bool:
        """
        Run a task immediately and update last_run_iso.
        Returns True if the action succeeded.
        """
        now = datetime.now()
        task: ScheduledTask | None = None
        with self._lock:
            for t in self._tasks:
                if t.task_id == task_id:
                    task = t
                    break
        if not task:
            return False
        ok = False
        try:
            ok = bool(self._run_action(task.action_type, task.target_path, dict(task.action_params)))
        except Exception:
            ok = False
        self._log(f"Scheduled task '{task.title}' run_now -> ok={ok}")
        with self._lock:
            for i, t in enumerate(self._tasks):
                if t.task_id == task_id:
                    self._tasks[i].last_run_iso = now.isoformat()
                    self._persist_locked()
                    break
        return ok

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
        except Exception:
            pass

    def _persist_locked(self) -> None:
        data: list[dict[str, Any]] = []
        for t in self._tasks:
            data.append(
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "schedule": dict(t.schedule),
                    "action_type": t.action_type,
                    "action_params": dict(t.action_params),
                    "target_path": t.target_path,
                    "enabled": bool(t.enabled),
                    "last_run_iso": t.last_run_iso,
                }
            )
        self._save_tasks(data)

    def _run_loop(self) -> None:
        self._log("ScheduledTaskManager started")
        while not self._stop.is_set():
            now = datetime.now()
            with self._lock:
                tasks = list(self._tasks)
            for task in tasks:
                if not task.enabled:
                    continue
                due = task.most_recent_due(now=now)
                if not due:
                    continue
                last_run: datetime | None = None
                if task.last_run_iso:
                    try:
                        last_run = datetime.fromisoformat(task.last_run_iso)
                    except Exception:
                        last_run = None
                if last_run is not None and last_run >= due:
                    continue

                ok = False
                err: str | None = None
                try:
                    ok = bool(self._run_action(task.action_type, task.target_path, dict(task.action_params)))
                except Exception as e:
                    ok = False
                    err = str(e)
                self._log(f"Scheduled task '{task.title}' -> ok={ok}" + (f" err={err}" if err else ""))
                with self._lock:
                    for i, t in enumerate(self._tasks):
                        if t.task_id == task.task_id:
                            self._tasks[i].last_run_iso = now.isoformat()
                            self._persist_locked()
                            break
            time.sleep(1.0)
