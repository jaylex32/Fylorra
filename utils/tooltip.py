"""
Fylorra - Tooltip Helper
Provides hover tooltips for all UI widgets
"""

import tkinter as tk
from typing import Optional


class ToolTip:
    """
    Create a tooltip for a given widget with hover delay

    Usage:
        button = ctk.CTkButton(parent, text="Click me")
        ToolTip(button, "This button does something cool")
    """

    def __init__(
        self,
        widget,
        text: str,
        delay: int = 500,
        wrap_length: int = 300,
        bg_color: str = "#2B2B2B",
        text_color: str = "#FFFFFF",
        border_color: str = "#1F6AA5"
    ):
        """
        Create tooltip for widget

        Args:
            widget: The widget to attach tooltip to
            text: Tooltip text to display
            delay: Delay in ms before showing tooltip
            wrap_length: Maximum width before text wraps
            bg_color: Background color (dark gray)
            text_color: Text color (white)
            border_color: Border color (blue accent)
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wrap_length = wrap_length
        self.bg_color = bg_color
        self.text_color = text_color
        self.border_color = border_color

        self.tooltip_window: Optional[tk.Toplevel] = None
        self.schedule_id: Optional[str] = None

        # Bind hover events
        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        """Mouse entered widget - schedule tooltip"""
        self._cancel_scheduled()
        self.schedule_id = self.widget.after(self.delay, self._show_tooltip)

    def _on_leave(self, event=None):
        """Mouse left widget - hide tooltip"""
        self._cancel_scheduled()
        self._hide_tooltip()

    def _cancel_scheduled(self):
        """Cancel scheduled tooltip show"""
        if self.schedule_id:
            try:
                self.widget.after_cancel(self.schedule_id)
            except:
                pass
            self.schedule_id = None

    def _show_tooltip(self):
        """Display the tooltip"""
        if self.tooltip_window or not self.text:
            return

        # Get widget position
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        except:
            return

        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)  # Remove window decorations
        self.tooltip_window.wm_attributes("-topmost", True)  # Always on top

        # Create label with text
        label = tk.Label(
            self.tooltip_window,
            text=self.text,
            justify=tk.LEFT,
            background=self.bg_color,
            foreground=self.text_color,
            relief=tk.SOLID,
            borderwidth=1,
            wraplength=self.wrap_length,
            font=("Segoe UI", 9),
            padx=8,
            pady=6
        )
        label.pack()

        # Configure border color
        self.tooltip_window.configure(background=self.border_color)

        # Position tooltip
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

    def _hide_tooltip(self):
        """Hide the tooltip"""
        if self.tooltip_window:
            try:
                self.tooltip_window.destroy()
            except:
                pass
            self.tooltip_window = None

    def update_text(self, new_text: str):
        """Update tooltip text"""
        self.text = new_text
        if self.tooltip_window:
            self._hide_tooltip()


class ToolTipHelper:
    """Helper class for managing multiple tooltips"""

    # Tooltip text definitions for common buttons
    TOOLTIPS = {
        # Main window buttons
        "add_monitor": "Create a new folder monitor with custom automation rules",
        "add_ftp": "Monitor a remote FTP/SFTP server for file changes",
        "settings": "Configure application settings, AI models, and preferences",
        "ai_rule_builder": "Use natural language to create automation rules\n(e.g., 'Move all PDFs to Documents folder')",

        # Monitor card buttons
        "start_monitor": "Start monitoring this folder for file changes",
        "stop_monitor": "Stop monitoring this folder",
        "pause_monitor": "Temporarily pause monitoring without stopping",
        "edit_monitor": "Edit monitor settings and rules",
        "delete_monitor": "Delete this monitor (cannot be undone)",
        "run_rules": "Manually run automation rules on existing files",
        "smart_rename": "Rename files using AI vision analysis\n(Analyzes images and suggests descriptive names)",
        "categorize": "Organize files into category folders using AI",
        "security_scan": "Scan files for security risks and malware",
        "semantic_analysis": "Analyze file content and extract insights",
        "view_logs": "View event history and automation logs",
        "export_logs": "Export logs to CSV or JSON format",

        # Settings dialog buttons
        "load_ai_model": "Download and load AI model into memory\n(~2.4GB, first time may take several minutes)",
        "unload_ai_model": "Unload AI model to free ~2.5GB of RAM",
        "reload_ai_model": "Reload AI model with new settings",
        "test_email": "Send a test email notification",
        "save_settings": "Save all changes and close settings",
        "cancel_settings": "Discard changes and close",

        # AI dialogs
        "start_rename": "Begin AI-powered renaming process",
        "approve_all": "Approve all suggested names",
        "skip": "Skip this file",
        "apply_changes": "Apply approved changes to files",
        "cancel_operation": "Cancel operation (no changes will be made)",

        # Common actions
        "browse": "Browse for folder",
        "refresh": "Refresh list",
        "clear": "Clear all items",
        "select_all": "Select all items",
        "deselect_all": "Deselect all items",
    }

    @staticmethod
    def add_tooltip(widget, text: str, **kwargs):
        """
        Add tooltip to a widget

        Args:
            widget: Widget to add tooltip to
            text: Tooltip text
            **kwargs: Additional ToolTip parameters
        """
        return ToolTip(widget, text, **kwargs)

    @staticmethod
    def add_standard_tooltip(widget, tooltip_key: str, **kwargs):
        """
        Add tooltip using predefined text from TOOLTIPS dict

        Args:
            widget: Widget to add tooltip to
            tooltip_key: Key from TOOLTIPS dict
            **kwargs: Additional ToolTip parameters
        """
        text = ToolTipHelper.TOOLTIPS.get(tooltip_key, "")
        if text:
            return ToolTip(widget, text, **kwargs)
        return None

    @staticmethod
    def add_tooltips_batch(widgets_config: dict):
        """
        Add tooltips to multiple widgets from config

        Args:
            widgets_config: Dict of {widget: "tooltip_key" or "direct text"}

        Example:
            ToolTipHelper.add_tooltips_batch({
                add_btn: "add_monitor",
                settings_btn: "settings",
                custom_btn: "This is a custom tooltip"
            })
        """
        tooltips = []
        for widget, text_or_key in widgets_config.items():
            # Check if it's a key from TOOLTIPS dict
            if text_or_key in ToolTipHelper.TOOLTIPS:
                tooltip = ToolTipHelper.add_standard_tooltip(widget, text_or_key)
            else:
                # Use as direct text
                tooltip = ToolTip(widget, text_or_key)

            if tooltip:
                tooltips.append(tooltip)

        return tooltips
