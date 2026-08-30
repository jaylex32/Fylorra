"""
Analytics Dashboard Dialog for Fylorra
Shows statistics and charts for monitored folder activity
"""

import customtkinter as ctk
from typing import Dict
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk
from utils.png_icons import PNGIconLoader


class AnalyticsDashboard(ctk.CTkToplevel):
    """Analytics dashboard showing monitoring statistics"""

    def __init__(self, parent, analytics_manager, monitor_manager):
        super().__init__(parent)

        self.analytics_manager = analytics_manager
        self.monitor_manager = monitor_manager
        self.time_range = 7  # Default to 7 days
        self.icon_loader = PNGIconLoader()

        # Window setup
        self.title("Analytics Dashboard - Fylorra")
        self.geometry("900x700")
        self.resizable(True, True)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.winfo_screenheight() // 2) - (700 // 2)
        self.geometry(f"900x700+{x}+{y}")

        self._create_ui()
        self._load_statistics()

    def _create_ui(self):
        """Create the dashboard UI"""
        # Main container with padding
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent", height=50)
        header_frame.pack(fill="x", pady=(0, 20))
        header_frame.pack_propagate(False)

        # Load analytics icon
        analytics_icon = self.icon_loader.load_icon("analytics", size=(32, 32))

        # Icon positioned absolutely on the left side
        if analytics_icon:
            icon_label = ctk.CTkLabel(
                header_frame,
                text="",
                image=analytics_icon
            )
            icon_label.place(x=0, y=9)

        # Title text
        title_label = ctk.CTkLabel(
            header_frame,
            text="Analytics Dashboard",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.place(x=40, y=10)

        # Time range selector
        time_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        time_frame.pack(side="right")

        ctk.CTkLabel(
            time_frame,
            text="Time Range:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(0, 10))

        self.time_range_var = ctk.StringVar(value="7 days")
        time_selector = ctk.CTkOptionMenu(
            time_frame,
            variable=self.time_range_var,
            values=["24 hours", "7 days", "30 days", "90 days", "All time"],
            command=self._on_time_range_changed,
            width=120
        )
        time_selector.pack(side="left")

        # Scrollable content area
        self.scrollable = ctk.CTkScrollableFrame(main_container, fg_color="transparent")
        self.scrollable.pack(fill="both", expand=True)

        # Overview cards section
        self.overview_frame = ctk.CTkFrame(self.scrollable, fg_color="transparent")
        self.overview_frame.pack(fill="x", pady=(0, 20))

        # Event type breakdown section
        event_section = ctk.CTkFrame(self.scrollable, fg_color=("#f0f0f0", "#2b2b2b"), corner_radius=10)
        event_section.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            event_section,
            text="Event Type Breakdown",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.event_breakdown_frame = ctk.CTkFrame(event_section, fg_color="transparent")
        self.event_breakdown_frame.pack(fill="x", padx=20, pady=(0, 15))

        # File types section
        file_types_section = ctk.CTkFrame(self.scrollable, fg_color=("#f0f0f0", "#2b2b2b"), corner_radius=10)
        file_types_section.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            file_types_section,
            text="Top File Types",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.file_types_frame = ctk.CTkFrame(file_types_section, fg_color="transparent")
        self.file_types_frame.pack(fill="x", padx=20, pady=(0, 15))

        # Monitor activity section
        monitor_section = ctk.CTkFrame(self.scrollable, fg_color=("#f0f0f0", "#2b2b2b"), corner_radius=10)
        monitor_section.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            monitor_section,
            text="Most Active Monitors",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.monitor_activity_frame = ctk.CTkFrame(monitor_section, fg_color="transparent")
        self.monitor_activity_frame.pack(fill="x", padx=20, pady=(0, 15))

        # AI Insights section (will only show if AI is ready)
        self._create_ai_insights_section()

        # Close button
        close_btn = ctk.CTkButton(
            main_container,
            text="Close",
            command=self.destroy,
            width=120,
            height=38,
            corner_radius=8,
            fg_color=("#1976D2", "#1565C0"),
            hover_color=("#1565C0", "#0D47A1")
        )
        close_btn.pack(pady=(20, 0))

    def _on_time_range_changed(self, selection: str):
        """Handle time range selection change"""
        range_map = {
            "24 hours": 1,
            "7 days": 7,
            "30 days": 30,
            "90 days": 90,
            "All time": None
        }
        self.time_range = range_map[selection]
        self._load_statistics()

    def _load_statistics(self):
        """Load and display statistics"""
        # Get statistics from analytics manager
        if self.time_range is None:
            # All time
            stats = self.analytics_manager.get_statistics(days=999999)
        else:
            stats = self.analytics_manager.get_statistics(days=self.time_range)

        # Clear existing widgets
        for widget in self.overview_frame.winfo_children():
            widget.destroy()
        for widget in self.event_breakdown_frame.winfo_children():
            widget.destroy()
        for widget in self.file_types_frame.winfo_children():
            widget.destroy()
        for widget in self.monitor_activity_frame.winfo_children():
            widget.destroy()

        # Display overview cards
        self._create_overview_cards(stats)

        # Display event breakdown
        self._create_event_breakdown(stats.get("event_counts", {}))

        # Display file types
        self._create_file_types_chart(stats.get("file_type_counts", {}))

        # Display monitor activity
        self._create_monitor_activity(stats.get("monitor_activity", {}))

    def _create_overview_cards(self, stats: Dict):
        """Create overview statistic cards"""
        total_events = stats.get("total_events", 0)

        # Calculate events today
        today_events = 0
        daily_events = stats.get("daily_events", {})
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_events = daily_events.get(today_str, 0)

        # Calculate average daily events
        if daily_events and self.time_range:
            avg_daily = sum(daily_events.values()) / min(self.time_range, len(daily_events))
        else:
            avg_daily = 0

        # Active monitors count
        active_monitors = len(self.monitor_manager.monitors)

        cards_data = [
            ("Total Events", f"{total_events:,}", "#4CAF50"),
            ("Today's Events", f"{today_events:,}", "#2196F3"),
            ("Avg Daily Events", f"{avg_daily:.1f}", "#FF9800"),
            ("Active Monitors", f"{active_monitors}", "#9C27B0")
        ]

        for i, (title, value, color) in enumerate(cards_data):
            card = ctk.CTkFrame(
                self.overview_frame,
                fg_color=(color, color),
                corner_radius=10,
                width=200,
                height=100
            )
            card.grid(row=0, column=i, padx=10, sticky="ew")
            self.overview_frame.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=12),
                text_color="white"
            ).pack(pady=(15, 5))

            ctk.CTkLabel(
                card,
                text=value,
                font=ctk.CTkFont(size=24, weight="bold"),
                text_color="white"
            ).pack()

    def _create_event_breakdown(self, event_counts: Dict):
        """Create event type breakdown display"""
        if not event_counts:
            ctk.CTkLabel(
                self.event_breakdown_frame,
                text="No events recorded",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            ).pack(pady=20)
            return

        # Event type colors (no emojis, just text)
        event_info = {
            "created": "#4CAF50",
            "modified": "#2196F3",
            "deleted": "#F44336",
            "moved": "#FF9800"
        }

        total = sum(event_counts.values())

        for i, (event_type, count) in enumerate(event_counts.items()):
            color = event_info.get(event_type, "#9E9E9E")
            percentage = (count / total * 100) if total > 0 else 0

            row_frame = ctk.CTkFrame(self.event_breakdown_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=5)

            # Color indicator dot
            color_dot = ctk.CTkFrame(
                row_frame,
                width=12,
                height=12,
                corner_radius=6,
                fg_color=color
            )
            color_dot.pack(side="left", padx=(0, 8), pady=4)

            # Event type label
            event_label = ctk.CTkLabel(
                row_frame,
                text=event_type.capitalize(),
                font=ctk.CTkFont(family="Segoe UI", size=13),
                anchor="w",
                width=80
            )
            event_label.pack(side="left", padx=(0, 10))

            # Progress bar container with fixed size
            progress_container = ctk.CTkFrame(row_frame, fg_color="transparent", width=450, height=20)
            progress_container.pack(side="left", padx=10)
            progress_container.pack_propagate(False)

            # Progress bar background
            progress_bg = ctk.CTkFrame(
                progress_container,
                fg_color=("#e0e0e0", "#3a3a3a"),
                height=20,
                corner_radius=10
            )
            progress_bg.place(x=0, y=0, relwidth=1.0)

            # Progress bar fill (clipped inside background)
            if percentage > 0:
                fill_percentage = min(percentage / 100, 1.0)  # Cap at 100%
                progress_fill = ctk.CTkFrame(
                    progress_bg,
                    fg_color=color,
                    height=20,
                    corner_radius=10
                )
                progress_fill.place(x=0, y=0, relwidth=fill_percentage)

            # Count and percentage
            count_label = ctk.CTkLabel(
                row_frame,
                text=f"{count:,} ({percentage:.1f}%)",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                anchor="e",
                width=130
            )
            count_label.pack(side="right")

    def _create_file_types_chart(self, file_type_counts: Dict):
        """Create file types display"""
        if not file_type_counts:
            ctk.CTkLabel(
                self.file_types_frame,
                text="No file type data available",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            ).pack(pady=20)
            return

        total = sum(file_type_counts.values())

        for i, (file_type, count) in enumerate(file_type_counts.items()):
            percentage = (count / total * 100) if total > 0 else 0

            row_frame = ctk.CTkFrame(self.file_types_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=5)

            # File type label
            type_display = file_type if file_type else "No extension"
            type_label = ctk.CTkLabel(
                row_frame,
                text=type_display,
                font=ctk.CTkFont(family="Consolas", size=12),
                anchor="w",
                width=80
            )
            type_label.pack(side="left", padx=(0, 10))

            # Bar container with fixed size
            bar_container = ctk.CTkFrame(row_frame, fg_color="transparent", width=500, height=18)
            bar_container.pack(side="left", padx=10)
            bar_container.pack_propagate(False)

            # Bar background
            bar_bg = ctk.CTkFrame(
                bar_container,
                fg_color=("#e0e0e0", "#3a3a3a"),
                height=18,
                corner_radius=9
            )
            bar_bg.place(x=0, y=0, relwidth=1.0)

            # Bar fill (clipped inside background)
            if percentage > 0:
                fill_percentage = min(percentage / 100, 1.0)  # Cap at 100%
                bar_fill = ctk.CTkFrame(
                    bar_bg,
                    fg_color=("#607D8B", "#708090"),
                    height=18,
                    corner_radius=9
                )
                bar_fill.place(x=0, y=0, relwidth=fill_percentage)

            # Count
            count_label = ctk.CTkLabel(
                row_frame,
                text=f"{count:,} ({percentage:.1f}%)",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                anchor="e",
                width=130
            )
            count_label.pack(side="right")

    def _create_monitor_activity(self, monitor_activity: Dict):
        """Create monitor activity display"""
        if not monitor_activity:
            ctk.CTkLabel(
                self.monitor_activity_frame,
                text="No monitor activity data available",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            ).pack(pady=20)
            return

        total = sum(monitor_activity.values())

        for i, (monitor_id, count) in enumerate(monitor_activity.items()):
            percentage = (count / total * 100) if total > 0 else 0

            # Get monitor path
            monitor_path = "Unknown"
            if monitor_id in self.monitor_manager.monitors:
                monitor = self.monitor_manager.monitors[monitor_id]
                monitor_path = monitor.path if hasattr(monitor, 'path') else str(monitor.monitor_path) if hasattr(monitor, 'monitor_path') else "Unknown"

            row_frame = ctk.CTkFrame(self.monitor_activity_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=5)

            # Monitor path label (without emoji)
            path_display = monitor_path[:60] + "..." if len(monitor_path) > 60 else monitor_path
            path_label = ctk.CTkLabel(
                row_frame,
                text=path_display,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                anchor="w"
            )
            path_label.pack(side="left", fill="x", expand=True, padx=(0, 10))

            # Count
            ctk.CTkLabel(
                row_frame,
                text=f"{count:,} events ({percentage:.1f}%)",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                width=180,
                anchor="e"
            ).pack(side="right")

    def _create_ai_insights_section(self):
        """Create AI Insights section (if AI is available)"""
        # Check if AI manager is available
        main_window = self.master
        if not hasattr(main_window, 'ai_manager'):
            return

        ai_manager = main_window.ai_manager

        # Only show if AI is ready
        if not ai_manager.is_ready:
            return

        # Create AI Insights section
        ai_section = ctk.CTkFrame(self.scrollable, fg_color=("#e8e8e8", "#2b2b2b"), corner_radius=10)
        ai_section.pack(fill="x", pady=(0, 20))

        # Header
        header = ctk.CTkLabel(
            ai_section,
            text="🤖 AI Insights",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            anchor="w"
        )
        header.pack(anchor="w", padx=15, pady=(15, 10))

        # AI status info
        status_frame = ctk.CTkFrame(ai_section, fg_color="transparent")
        status_frame.pack(fill="x", padx=15, pady=(0, 15))

        # Model info
        info_text = f"Vision Model Active: Qwen3-VL-4B (Q4_K_M)\nCapabilities: Smart Rename, Auto-Categorize, Security Scanning"

        info_label = ctk.CTkLabel(
            status_frame,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray",
            anchor="w",
            justify="left"
        )
        info_label.pack(anchor="w")

        # Quick actions
        actions_frame = ctk.CTkFrame(ai_section, fg_color="transparent")
        actions_frame.pack(fill="x", padx=15, pady=(10, 15))

        actions_label = ctk.CTkLabel(
            actions_frame,
            text="Quick Actions:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        actions_label.pack(anchor="w", pady=(0, 10))

        # Action buttons
        btn_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkLabel(
            btn_frame,
            text="Use AI buttons (purple, orange, red) on monitor cards to:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 5))

        features = [
            "🟣 Smart Rename - AI-powered file renaming",
            "🟠 Auto-Categorize - Organize files by visual content",
            "🔴 Security Scan - Detect sensitive information"
        ]

        for feature in features:
            ctk.CTkLabel(
                btn_frame,
                text=feature,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                anchor="w"
            ).pack(anchor="w", pady=2, padx=10)
