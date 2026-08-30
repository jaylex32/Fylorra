"""Analytics Module - Tracks and analyzes file system events"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict


class AnalyticsManager:
    """Manages analytics data collection and reporting"""

    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.analytics_file = settings_manager.app_folder / "analytics.json"
        self.events = self._load_events()

    def _load_events(self) -> List[Dict]:
        """Load analytics events from file"""
        if not self.analytics_file.exists():
            return []

        try:
            with open(self.analytics_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading analytics: {e}")
            return []

    def _save_events(self):
        """Save analytics events to file"""
        try:
            # Keep only last 10,000 events to prevent file from getting too large
            if len(self.events) > 10000:
                self.events = self.events[-10000:]

            with open(self.analytics_file, 'w') as f:
                json.dump(self.events, f)
        except Exception as e:
            print(f"Error saving analytics: {e}")

    def record_event(self, event_type: str, monitor_id: str, file_path: str = None):
        """
        Record a file system event

        Args:
            event_type: Type of event (created, modified, deleted, moved)
            monitor_id: ID of the monitor
            file_path: Path to the file (optional)
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "monitor_id": monitor_id,
            "file_path": file_path,
            "file_extension": Path(file_path).suffix.lower() if file_path else None
        }

        self.events.append(event)
        self._save_events()

    def get_statistics(self, days: int = 7) -> Dict:
        """
        Get statistics for the last N days

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with statistics
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_events = [
            e for e in self.events
            if datetime.fromisoformat(e['timestamp']) >= cutoff_date
        ]

        # Count events by type
        event_counts = defaultdict(int)
        for event in recent_events:
            event_counts[event['event_type']] += 1

        # Count file types
        file_type_counts = defaultdict(int)
        for event in recent_events:
            if event.get('file_extension'):
                file_type_counts[event['file_extension']] += 1

        # Events per day
        daily_events = defaultdict(int)
        for event in recent_events:
            date_key = datetime.fromisoformat(event['timestamp']).strftime('%Y-%m-%d')
            daily_events[date_key] += 1

        # Most active monitors
        monitor_activity = defaultdict(int)
        for event in recent_events:
            monitor_activity[event['monitor_id']] += 1

        return {
            "total_events": len(recent_events),
            "event_counts": dict(event_counts),
            "file_type_counts": dict(sorted(file_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            "daily_events": dict(sorted(daily_events.items())),
            "monitor_activity": dict(sorted(monitor_activity.items(), key=lambda x: x[1], reverse=True)[:5]),
            "period_days": days
        }

    def get_total_events(self) -> int:
        """Get total number of events tracked"""
        return len(self.events)

    def get_events_today(self) -> int:
        """Get number of events today"""
        today = datetime.now().date()
        count = 0
        for event in self.events:
            event_date = datetime.fromisoformat(event['timestamp']).date()
            if event_date == today:
                count += 1
        return count

    def clear_old_data(self, days: int = 30):
        """
        Clear analytics data older than specified days

        Args:
            days: Keep data from last N days
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        self.events = [
            e for e in self.events
            if datetime.fromisoformat(e['timestamp']) >= cutoff_date
        ]
        self._save_events()
