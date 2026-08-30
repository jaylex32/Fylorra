"""Comprehensive Logging System - Records all monitoring activity"""

import logging
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import json
import csv

from core.branding import APP_NAME, APP_DATA_DIR_NAME, APP_LOG_PREFIX


class ActivityLogger:
    """Advanced logging system for all monitoring activities"""

    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.log_folder = Path.home() / APP_DATA_DIR_NAME / "logs"
        self.log_file: Optional[Path] = None
        try:
            self.log_folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.log_folder = Path.cwd()

        # Setup logging
        self._setup_logging()

        # In-memory activity log (for UI display)
        self.activity_buffer: List[Dict] = []
        self.max_buffer_size = 1000

    def _setup_logging(self):
        """Setup file-based logging"""
        # Create log file with date
        log_file = self.log_folder / f"{APP_LOG_PREFIX}_{datetime.now().strftime('%Y%m%d')}.log"
        self.log_file = log_file

        fmt = logging.Formatter(
            fmt='%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        self.logger = logging.getLogger(APP_NAME)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        for handler in list(self.logger.handlers):
            try:
                self.logger.removeHandler(handler)
                handler.close()
            except Exception:
                pass

        handlers: List[logging.Handler] = []
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(fmt)
            handlers.append(file_handler)
        except Exception as e:
            self.log_file = None
            fallback = logging.StreamHandler()
            fallback.setFormatter(fmt)
            handlers.append(fallback)
            self.logger.addHandler(fallback)
            self.logger.warning("File logging disabled: %s", e)
            handlers = []

        if handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(fmt)
            handlers.append(stream_handler)
            for handler in handlers:
                self.logger.addHandler(handler)

        self.logger.info("=" * 80)
        self.logger.info("%s Started", APP_NAME)
        self.logger.info("=" * 80)

    def log_event(self, monitor_id: str, monitor_path: str, event_type: str,
                  file_path: str, additional_info: str = ""):
        """Log a file system event"""
        message = f"[{monitor_path}] {event_type.upper()}: {file_path}"
        if additional_info:
            message += f" | {additional_info}"

        self.logger.info(message)

        # Add to activity buffer
        activity = {
            "timestamp": datetime.now().isoformat(),
            "monitor_id": monitor_id,
            "monitor_path": monitor_path,
            "event_type": event_type,
            "file_path": file_path,
            "additional_info": additional_info
        }

        self.activity_buffer.append(activity)

        # Trim buffer if too large
        if len(self.activity_buffer) > self.max_buffer_size:
            self.activity_buffer = self.activity_buffer[-self.max_buffer_size:]

    def log_action(self, monitor_id: str, action_type: str, file_path: str,
                   result: str, details: str = ""):
        """Log an automation action"""
        message = f"ACTION: {action_type.upper()} on {file_path} - {result.upper()}"
        if details:
            message += f" | {details}"

        if result == "success":
            self.logger.info(message)
        else:
            self.logger.error(message)

        # Add to activity buffer
        activity = {
            "timestamp": datetime.now().isoformat(),
            "monitor_id": monitor_id,
            "type": "action",
            "action_type": action_type,
            "file_path": file_path,
            "result": result,
            "details": details
        }

        self.activity_buffer.append(activity)

        if len(self.activity_buffer) > self.max_buffer_size:
            self.activity_buffer = self.activity_buffer[-self.max_buffer_size:]

    def log_monitor_event(self, event_type: str, monitor_id: str, monitor_path: str,
                         details: str = ""):
        """Log monitor lifecycle events (start, stop, add, remove)"""
        message = f"MONITOR {event_type.upper()}: {monitor_path} (ID: {monitor_id[:8]}...)"
        if details:
            message += f" | {details}"

        self.logger.info(message)

        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "monitor_event",
            "event_type": event_type,
            "monitor_id": monitor_id,
            "monitor_path": monitor_path,
            "details": details
        }

        self.activity_buffer.append(activity)

        if len(self.activity_buffer) > self.max_buffer_size:
            self.activity_buffer = self.activity_buffer[-self.max_buffer_size:]

    def log_initial_scan(self, monitor_id: str, monitor_path: str,
                        file_count: int, folder_count: int):
        """Log initial folder scan results"""
        message = (f"INITIAL SCAN: {monitor_path} | "
                  f"Files: {file_count} | Folders: {folder_count}")

        self.logger.info(message)

        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "initial_scan",
            "monitor_id": monitor_id,
            "monitor_path": monitor_path,
            "file_count": file_count,
            "folder_count": folder_count
        }

        self.activity_buffer.append(activity)

        if len(self.activity_buffer) > self.max_buffer_size:
            self.activity_buffer = self.activity_buffer[-self.max_buffer_size:]

    def log_error(self, context: str, error_message: str):
        """Log an error"""
        message = f"ERROR in {context}: {error_message}"
        self.logger.error(message)

        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": "error",
            "context": context,
            "error_message": error_message
        }

        self.activity_buffer.append(activity)

        if len(self.activity_buffer) > self.max_buffer_size:
            self.activity_buffer = self.activity_buffer[-self.max_buffer_size:]

    def get_recent_activity(self, count: int = 100) -> List[Dict]:
        """Get recent activity entries"""
        return self.activity_buffer[-count:]

    def export_logs_json(self, file_path: str) -> bool:
        """Export all logs to JSON file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.activity_buffer, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Logs exported to JSON: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export logs to JSON: {e}")
            return False

    def export_logs_csv(self, file_path: str) -> bool:
        """Export all logs to CSV file"""
        try:
            if not self.activity_buffer:
                return False

            # Get all unique keys
            all_keys = set()
            for activity in self.activity_buffer:
                all_keys.update(activity.keys())

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
                writer.writeheader()
                writer.writerows(self.activity_buffer)

            self.logger.info(f"Logs exported to CSV: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export logs to CSV: {e}")
            return False

    def export_logs_text(self, file_path: str) -> bool:
        """Export all logs to readable text file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"{APP_NAME} - Activity Log\n")
                f.write("=" * 80 + "\n\n")

                for activity in self.activity_buffer:
                    timestamp = activity.get('timestamp', 'N/A')
                    f.write(f"[{timestamp}]\n")

                    for key, value in activity.items():
                        if key != 'timestamp':
                            f.write(f"  {key}: {value}\n")

                    f.write("\n")

            self.logger.info(f"Logs exported to text: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export logs to text: {e}")
            return False

    def clear_old_logs(self, days_to_keep: int = 30):
        """Clear log files older than specified days"""
        try:
            cutoff_date = datetime.now().timestamp() - (days_to_keep * 86400)

            for pattern in (f"{APP_LOG_PREFIX}_*.log", "fylorra_*.log"):
                for log_file in self.log_folder.glob(pattern):
                    if log_file.stat().st_mtime < cutoff_date:
                        log_file.unlink()
                        self.logger.info(f"Deleted old log file: {log_file.name}")

        except Exception as e:
            self.logger.error(f"Error clearing old logs: {e}")

    def get_log_folder(self) -> Path:
        """Get the log folder path"""
        return self.log_folder

    def shutdown(self):
        """Shutdown logger"""
        self.logger.info("=" * 80)
        self.logger.info("%s Stopped", APP_NAME)
        self.logger.info("=" * 80)
        logging.shutdown()
