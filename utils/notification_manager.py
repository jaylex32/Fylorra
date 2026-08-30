"""Notification manager with a Windows toast backend and cross-platform fallback."""

import inspect
import os
import threading
from pathlib import Path

try:
    from winotify import Notification, audio  # type: ignore
except Exception:
    Notification = None
    audio = None

from core.branding import APP_NAME


class NotificationManager:
    """Manages desktop notifications where a platform backend is available."""

    def __init__(self):
        self.app_id = APP_NAME
        self.icon_path = self._get_icon_path()
        self.notification_queue = []
        self.is_enabled = True

    def _get_icon_path(self) -> str:
        """Get the path to the app icon"""
        # Use a default icon or custom icon if available
        icon_path = Path(__file__).parent.parent / "assets" / "fylorra.ico"
        if icon_path.exists():
            return str(icon_path)
        return None

    def send_notification(self, title: str, message: str, duration: str = "short"):
        """
        Send a Windows toast notification

        Args:
            title: Notification title
            message: Notification message
            duration: "short" or "long"
        """
        if not self.is_enabled:
            return
        if os.name != "nt" or Notification is None:
            return

        def _send():
            try:
                notification_args = {
                    "app_id": self.app_id,
                    "title": title,
                    "msg": message,
                    "duration": duration,
                }
                if self.icon_path:
                    try:
                        if "icon" in inspect.signature(Notification).parameters:
                            notification_args["icon"] = self.icon_path
                    except Exception:
                        pass

                toast = Notification(
                    **notification_args
                )

                if self.icon_path and hasattr(toast, "set_icon"):
                    toast.set_icon(self.icon_path)

                # Set notification sound
                if audio is not None:
                    toast.set_audio(audio.Default, loop=False)

                # Show notification
                toast.show()

            except Exception as e:
                print(f"Error sending notification: {e}")

        # Send notification in a separate thread to avoid blocking
        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def send_action_notification(self, action_type: str, file_name: str,
                                 result: str = "success"):
        """Send notification for action execution"""
        emoji_map = {
            "copy": "📋",
            "move": "🚀",
            "rename": "✏️",
            "delete": "🗑️",
            "archive": "📦",
            "execute": "⚙️"
        }

        emoji = emoji_map.get(action_type, "✅")

        if result == "success":
            title = f"{emoji} Action Completed"
            message = f"{action_type.title()}: {file_name}"
        else:
            title = "❌ Action Failed"
            message = f"{action_type.title()} failed for: {file_name}"

        self.send_notification(title, message)

    def enable_notifications(self):
        """Enable notifications"""
        self.is_enabled = True

    def disable_notifications(self):
        """Disable notifications"""
        self.is_enabled = False

    def toggle_notifications(self) -> bool:
        """Toggle notifications on/off"""
        self.is_enabled = not self.is_enabled
        return self.is_enabled
