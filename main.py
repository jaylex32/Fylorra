"""
Fylorra - File Intake Automation
Modern, multi-threaded file system monitoring with Windows notifications.
"""

import customtkinter as ctk
import threading
import json
import os
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from gui.main_window import MainWindow
from core.monitor_manager import MonitorManager
from core.settings_manager import SettingsManager
from core.ai_manager import AIManager

try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
except Exception:
    TkinterDnD = None  # type: ignore


class FylorraApp:
    """Main application controller"""

    def __init__(self):
        # Set appearance mode and color theme
        ctk.set_appearance_mode("dark")  # "dark" or "light"
        ctk.set_default_color_theme("blue")

        # Initialize settings manager
        self.settings_manager = SettingsManager()

        # Initialize monitor manager
        self.monitor_manager = MonitorManager(self.settings_manager)

        # Initialize AI manager with settings manager for performance settings
        self.ai_manager = AIManager(self.settings_manager.app_folder, self.settings_manager)

        # Create main window
        if TkinterDnD is not None:
            # Enable drag & drop (used by Media Editors launcher and future drop zones).
            self.root = TkinterDnD.Tk()
            try:
                self.root.configure(bg="#0f0f10")
            except Exception:
                pass
        else:
            self.root = ctk.CTk()

        # Attach AI manager to root for access by child widgets
        self.root.ai_manager = self.ai_manager

        self.main_window = MainWindow(
            self.root,
            self.monitor_manager,
            self.settings_manager
        )

        # Configure window close behavior
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def run(self):
        """Start the application"""
        # Load saved monitors and pass to main window
        loaded_monitors = self.monitor_manager.load_monitors()
        self.main_window.restore_monitors(loaded_monitors)
        # Start scheduled tasks (runs while the app is open).
        self.monitor_manager.start_scheduled_tasks()

        # Start the GUI
        self.root.mainloop()

    def on_closing(self):
        """Handle application closing"""
        # ALWAYS save monitors before closing or minimizing
        self.monitor_manager.save_monitors()

        if self.settings_manager.get_setting("minimize_to_tray", True):
            # Minimize to tray instead of closing
            self.main_window.minimize_to_tray()
        else:
            self.quit_application()

    def quit_application(self):
        """Completely quit the application"""
        # Save all monitors
        self.monitor_manager.save_monitors()

        # Stop all monitors
        self.monitor_manager.stop_all_monitors()
        # Stop scheduled tasks
        self.monitor_manager.stop_scheduled_tasks()

        # Unload AI model if loaded
        if self.ai_manager.is_ready:
            self.ai_manager.unload_model()

        # Save settings
        self.settings_manager.save_settings()

        # Shutdown logger
        self.monitor_manager.logger.shutdown()

        # Destroy window
        self.root.quit()
        self.root.destroy()


if __name__ == "__main__":
    app = FylorraApp()
    app.run()
