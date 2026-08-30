from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class MonitorSignals(QObject):
    monitor_event = Signal(str, str, str, object)  # monitor_id, event_type, src_path, dest_path
    monitor_state = Signal(str)  # monitor_id changed (start/stop/stats)

