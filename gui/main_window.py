"""Main Window - Primary GUI interface"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
from typing import Dict, List
from pathlib import Path

from gui.monitor_card import MonitorCard
from gui.add_monitor_dialog import AddMonitorDialog
from gui.add_ftp_dialog import AddFTPDialog
from gui.settings_dialog import SettingsDialog
from utils.system_tray import SystemTrayManager
from utils.png_icons import PNGIconLoader
from utils.tooltip import ToolTipHelper
from core.branding import APP_NAME, APP_WINDOW_TITLE, APP_TAGLINE


class MainWindow:
    """Main application window"""

    def __init__(self, root: ctk.CTk, monitor_manager, settings_manager):
        self.root = root
        self.monitor_manager = monitor_manager
        self.settings_manager = settings_manager

        # Get AI manager from root (attached in main.py)
        self.ai_manager = getattr(root, 'ai_manager', None)

        # Configure window
        self.root.title(APP_WINDOW_TITLE)
        width = self.settings_manager.get_setting("window_width", 1200)
        height = self.settings_manager.get_setting("window_height", 700)
        self.root.geometry(f"{width}x{height}")

        # Set minimum window size
        self.root.minsize(1000, 700)

        # System tray manager
        self.tray_manager = SystemTrayManager(self.root, self.on_tray_restore)

        # Icon loader
        self.icon_loader = PNGIconLoader()

        # Monitor cards
        self.monitor_cards: Dict[str, MonitorCard] = {}

        # Current view tracking
        self.current_view = "monitors"  # monitors, ai_rules, ai_hub, settings

        # Setup GUI
        self._setup_ui()

        # Resize performance helpers (Tk/CustomTkinter can get sluggish with complex UIs).
        self._last_root_size: tuple[int, int] | None = None
        self._resize_after_id = None
        self._resize_active = False
        # Note: we no longer hide the UI during resize; we only debounce expensive work.

        # Register event callback
        self.monitor_manager.add_event_callback(self._on_monitor_event)

    def _setup_ui(self):
        """Setup the user interface"""
        # Main container (holds sidebar + content)
        self.main_container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        # Sidebar
        self._create_sidebar()

        # Right side container (top bar + content + status)
        self.right_container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.right_container.pack(side="right", fill="both", expand=True)

        # Top bar
        self._create_top_bar()

        # Main content area
        self._create_main_area()

        # Status bar
        self._create_status_bar()

    def _create_sidebar(self):
        """Create sidebar navigation (always expanded)"""
        # Sidebar frame (fixed at 200px width - always visible)
        self.sidebar = ctk.CTkFrame(
            self.main_container,
            width=200,
            corner_radius=0,
            fg_color=("#2b2b2b", "#1a1a1a")
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Top bar in sidebar (same line as navigation buttons)
        sidebar_top = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=65)
        sidebar_top.pack(fill="x")
        sidebar_top.pack_propagate(False)

        # App branding in sidebar top bar
        branding_frame = ctk.CTkFrame(sidebar_top, fg_color="transparent")
        branding_frame.pack(side="left", padx=(15, 0), pady=12)

        # Load app icon
        app_icon = self.icon_loader.load_icon("folder", size=(24, 24))

        # Icon
        icon_label = ctk.CTkLabel(
            branding_frame,
            text="",
            image=app_icon
        )
        icon_label.pack(side="left", padx=(0, 8))

        # App name and subtitle
        text_container = ctk.CTkFrame(branding_frame, fg_color="transparent")
        text_container.pack(side="left")

        app_name = ctk.CTkLabel(
            text_container,
            text=APP_NAME,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#ffffff", "#ffffff"),
            anchor="w"
        )
        app_name.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            text_container,
            text=APP_TAGLINE.title(),
            font=ctk.CTkFont(size=10),
            text_color=("#999999", "#999999"),
            anchor="w"
        )
        subtitle.pack(anchor="w")

        # Navigation buttons container
        self.nav_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_container.pack(fill="both", expand=True, pady=(0, 10))

        # Load icons - ALL same size (24x24)
        monitors_icon = self.icon_loader.load_icon("monitor_folders", size=(24, 24))
        ai_rules_icon = self.icon_loader.load_icon("brain", size=(24, 24))
        ai_hub_icon = self.icon_loader.load_icon("ai_hub", size=(24, 24))
        ai_command_icon = self.icon_loader.load_icon("ai", size=(24, 24))
        ai_search_icon = self.icon_loader.load_icon("search", size=(24, 24))
        tools_icon = self.icon_loader.load_icon("grid", size=(24, 24))
        media_editors_icon = self.icon_loader.load_icon("edit", size=(24, 24))
        scheduled_tasks_icon = self.icon_loader.load_icon("analytics", size=(24, 24))
        workspace_icon = self.icon_loader.load_icon("folder", size=(24, 24))
        settings_icon = self.icon_loader.load_icon("settings", size=(24, 24))

        # Navigation buttons
        self.nav_buttons = {}

        # Monitors button
        self.nav_buttons["monitors"] = self._create_nav_button(
            self.nav_container,
            icon=monitors_icon,
            text="Monitors",
            command=lambda: self._switch_view("monitors")
        )

        # AI Rules button
        self.nav_buttons["ai_rules"] = self._create_nav_button(
            self.nav_container,
            icon=ai_rules_icon,
            text="AI Rules",
            command=lambda: self._switch_view("ai_rules")
        )

        # Scheduled Tasks button (time-based automation)
        self.nav_buttons["scheduled_tasks"] = self._create_nav_button(
            self.nav_container,
            icon=scheduled_tasks_icon,
            text="Scheduled Tasks",
            command=lambda: self._switch_view("scheduled_tasks")
        )

        # AI Hub button
        self.nav_buttons["ai_hub"] = self._create_nav_button(
            self.nav_container,
            icon=ai_hub_icon,
            text="AI Hub",
            command=lambda: self._switch_view("ai_hub")
        )

        # AI Command button
        self.nav_buttons["ai_command"] = self._create_nav_button(
            self.nav_container,
            icon=ai_command_icon,
            text="AI Command",
            command=lambda: self._switch_view("ai_command")
        )

        # AI Search button
        self.nav_buttons["ai_search"] = self._create_nav_button(
            self.nav_container,
            icon=ai_search_icon,
            text="AI Search",
            command=lambda: self._switch_view("ai_search")
        )

        # File Tools button
        self.nav_buttons["file_tools"] = self._create_nav_button(
            self.nav_container,
            icon=tools_icon,
            text="File Tools",
            command=lambda: self._switch_view("file_tools")
        )

        # Media Editors button
        self.nav_buttons["media_editors"] = self._create_nav_button(
            self.nav_container,
            icon=media_editors_icon,
            text="Media Editors",
            command=lambda: self._switch_view("media_editors")
        )

        # Workspace button
        self.nav_buttons["workspace"] = self._create_nav_button(
            self.nav_container,
            icon=workspace_icon,
            text="Workspace",
            command=lambda: self._switch_view("workspace")
        )

        # Settings button
        self.nav_buttons["settings"] = self._create_nav_button(
            self.nav_container,
            icon=settings_icon,
            text="Settings",
            command=lambda: self._switch_view("settings")
        )

        # Highlight current view (Monitors by default)
        self._update_nav_selection()

    def _create_nav_button(self, parent, icon, text, command):
        """Create a navigation button for sidebar"""
        # Create a frame to hold the button with padding
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent", height=50)
        btn_frame.pack(fill="x", pady=2)
        btn_frame.pack_propagate(False)

        btn = ctk.CTkButton(
            btn_frame,
            text=" " + text,  # Always show text with spacing
            image=icon,
            width=180,
            height=50,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=command,
            fg_color="transparent",
            hover_color=("#3a3a3a", "#2a2a2a"),
            text_color=("#ffffff", "#ffffff"),
            corner_radius=0,
            anchor="w",
            compound="left"
        )
        btn.pack(side="left", padx=(10, 0))  # Left padding
        return btn


    def _switch_view(self, view_name: str):
        """Switch between different views"""
        self.current_view = view_name
        self._update_nav_selection()
        self._show_page(view_name)

    def _update_nav_selection(self):
        """Update visual selection state of navigation buttons"""
        for key, btn in self.nav_buttons.items():
            if key == self.current_view:
                # Selected state
                btn.configure(fg_color=("#3d5a80", "#2d4a70"))
            else:
                # Normal state
                btn.configure(fg_color="transparent")

    def _create_top_bar(self):
        """Create top navigation bar"""
        self.top_frame = ctk.CTkFrame(self.right_container, height=65, corner_radius=0, fg_color=("#f0f0f0", "#1a1a1a"))
        self.top_frame.pack(fill="x", padx=0, pady=0)
        self.top_frame.pack_propagate(False)

        # Left side - AI command bar
        ai_bar = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        ai_bar.pack(side="left", padx=20, pady=10, fill="x", expand=True)
        ai_bar.grid_columnconfigure(0, weight=1)

        self.ai_command_var = ctk.StringVar(value="")
        self.ai_command_entry = ctk.CTkEntry(
            ai_bar,
            textvariable=self.ai_command_var,
            height=40,
            placeholder_text="Ask AI: “convert docs to PDF, zip, scan for sensitive data…”",
        )
        self.ai_command_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.ai_command_entry.bind("<Return>", lambda _e: self.open_ai_command(prefill_text=self.ai_command_var.get().strip()))

        ai_btn_icon = self.icon_loader.load_icon("ai", size=(18, 18))
        self.ai_command_btn = ctk.CTkButton(
            ai_bar,
            text="Run",
            image=ai_btn_icon,
            width=90,
            height=40,
            command=lambda: self.open_ai_command(prefill_text=self.ai_command_var.get().strip()),
            fg_color=("#0d6efd", "#0d6efd"),
            hover_color=("#0b5ed7", "#0b5ed7"),
        )
        self.ai_command_btn.grid(row=0, column=1, sticky="e")

        # Right side - Action buttons (only Folder Monitor and FTP Monitor)
        self._top_right_buttons_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self._top_right_buttons_frame.pack(side="right", padx=30, pady=10)

        # Load PNG icons
        ftp_icon = self.icon_loader.load_icon("ftp", size=(20, 20))
        folder_icon = self.icon_loader.load_icon("add", size=(20, 20))

        # Add FTP monitor button
        self.add_ftp_btn = ctk.CTkButton(
            self._top_right_buttons_frame,
            text="FTP Monitor",
            image=ftp_icon,
            width=140,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            command=self.add_ftp_monitor,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=2,
            border_color=("#607D8B", "#708090"),
            corner_radius=8,
            compound="left"
        )
        self.add_ftp_btn.pack(side="right", padx=4, pady=0)

        # Add folder monitor button
        self.add_btn = ctk.CTkButton(
            self._top_right_buttons_frame,
            text="Folder Monitor",
            image=folder_icon,
            width=150,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            command=self.add_monitor,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=2,
            border_color=("#607D8B", "#708090"),
            corner_radius=8,
            compound="left"
        )
        self.add_btn.pack(side="right", padx=4, pady=0)

        # Add tooltips
        ToolTipHelper.add_tooltips_batch({
            self.add_ftp_btn: "add_ftp",
            self.add_btn: "add_monitor"
        })

    def _create_main_area(self):
        """Create main content area"""
        # Main container
        self.main_frame = ctk.CTkFrame(self.right_container, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Page container (professional app navigation: swap views instead of opening dialogs)
        self.page_container = ctk.CTkFrame(self.main_frame, corner_radius=0, fg_color="transparent")
        self.page_container.pack(fill="both", expand=True)
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self._create_pages()
        self._show_page(self.current_view or "monitors")

        # Debounce heavy layout work while resizing the main window.
        # This significantly improves perceived smoothness on Windows.
        try:
            self.root.bind("<Configure>", self._on_root_configure, add="+")
        except Exception:
            try:
                self.root.bind("<Configure>", self._on_root_configure)
            except Exception:
                pass

    def _show_resize_placeholder(self):
        if self._resize_active:
            return
        self._resize_active = True

    def _hide_resize_placeholder(self):
        if not self._resize_active:
            return
        self._resize_active = False

    def _on_root_configure(self, event):
        # Ignore child configure events.
        try:
            if event.widget is not self.root:
                return
        except Exception:
            pass

        try:
            w, h = int(event.width), int(event.height)
        except Exception:
            return

        # Only respond when size actually changes.
        if self._last_root_size == (w, h):
            return
        self._last_root_size = (w, h)

        # Start (or continue) a resize session.
        self._show_resize_placeholder()

        # Debounce: restore UI after resizing stops for a moment.
        try:
            if self._resize_after_id:
                self.root.after_cancel(self._resize_after_id)
        except Exception:
            pass

        def done():
            self._resize_after_id = None
            self._hide_resize_placeholder()
            # Persist window size only after resizing ends.
            try:
                self.settings_manager.set_setting("window_width", int(self.root.winfo_width()))
                self.settings_manager.set_setting("window_height", int(self.root.winfo_height()))
            except Exception:
                pass

        try:
            self._resize_after_id = self.root.after(160, done)
        except Exception:
            done()

    def _create_pages(self):
        def add_page(name: str):
            page = ctk.CTkFrame(self.page_container, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = page
            return page

        self._page_builders: dict[str, callable] = {}
        self._page_built: set[str] = set()
        self._page_building: set[str] = set()

        def register_lazy(name: str, builder: callable):
            page = add_page(name)
            self._page_builders[name] = builder
            # Lightweight placeholder (avoids heavy widget trees at startup)
            ctk.CTkLabel(page, text="Loading…", text_color="gray").pack(pady=40)
            return page

        # Monitors page (build immediately)
        monitors_page = add_page("monitors")
        self.scrollable_frame = ctk.CTkScrollableFrame(monitors_page, corner_radius=10, fg_color=("gray90", "gray13"))
        self.scrollable_frame.pack(fill="both", expand=True)

        self.empty_label = ctk.CTkLabel(
            self.scrollable_frame,
            text="📁 No monitors configured\n\nClick '+ Folder Monitor' for local/network folders\nClick '+ FTP Monitor' for FTP servers",
            font=ctk.CTkFont(size=16),
            text_color="gray",
        )
        self.empty_label.pack(pady=100)
        self._page_built.add("monitors")

        # Lazy pages (build only when selected)
        register_lazy(
            "scheduled_tasks",
            lambda page=None: self._mount_view("scheduled_tasks", self._build_scheduled_tasks_page),
        )
        register_lazy(
            "ai_rules",
            lambda page=None: self._mount_view("ai_rules", self._build_ai_rules_page),
        )
        register_lazy(
            "ai_hub",
            lambda page=None: self._mount_view("ai_hub", self._build_ai_hub_page),
        )
        register_lazy(
            "ai_command",
            lambda page=None: self._mount_view("ai_command", self._build_ai_command_page),
        )
        register_lazy(
            "ai_search",
            lambda page=None: self._mount_view("ai_search", self._build_ai_search_page),
        )
        register_lazy(
            "file_tools",
            lambda page=None: self._mount_view("file_tools", self._build_file_tools_page),
        )
        register_lazy(
            "media_editors",
            lambda page=None: self._mount_view("media_editors", self._build_media_editors_page),
        )
        register_lazy(
            "workspace",
            lambda page=None: self._mount_view("workspace", self._build_workspace_page),
        )
        register_lazy(
            "settings",
            lambda page=None: self._mount_view("settings", self._build_settings_page),
        )

    def _ensure_page_built(self, view_name: str):
        if view_name in getattr(self, "_page_built", set()):
            return
        if view_name in getattr(self, "_page_building", set()):
            return
        builder = getattr(self, "_page_builders", {}).get(view_name)
        if not builder:
            return
        self._page_building.add(view_name)

        def _run_builder():
            try:
                builder()
                self._page_built.add(view_name)
            except Exception:
                pass
            finally:
                try:
                    self._page_building.discard(view_name)
                except Exception:
                    pass

        # Build on next tick so the UI can paint first (prevents "hesitation" / glitches).
        try:
            self.root.after(5, _run_builder)
        except Exception:
            _run_builder()

    def _clear_page(self, page):
        for w in page.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

    def _mount_view(self, name: str, build_fn: callable):
        page = self.pages.get(name)
        if not page:
            return
        self._clear_page(page)
        build_fn(page)

    def _build_scheduled_tasks_page(self, page):
        from gui.scheduled_tasks_view import ScheduledTasksView

        ScheduledTasksView(page, self.monitor_manager).pack(fill="both", expand=True)

    def _build_ai_rules_page(self, page):
        try:
            from gui.nl_rule_dialog import NLRuleView
            from core.nl_rule_builder import NaturalLanguageRuleBuilder

            if not hasattr(self, "nl_rule_builder"):
                self.nl_rule_builder = NaturalLanguageRuleBuilder(self.ai_manager)

            def on_rule_created(rule, monitor_id=None, folder_path=None):
                if monitor_id and not folder_path:
                    self._refresh_monitor_card(monitor_id)
                elif monitor_id and folder_path:
                    self._create_monitor_card(monitor_id, folder_path, [rule])

            NLRuleView(
                page,
                self.nl_rule_builder,
                self.monitor_manager,
                current_folder=None,
                on_rule_created=on_rule_created,
                on_close=lambda: self._switch_view("monitors"),
            ).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="AI Rules",
                subtitle="Create event-based rules (created/modified/moved/deleted) and scheduled tasks.",
                primary=("Open AI Rule Builder", self.open_ai_rule_builder),
                secondary=("Open Scheduled Tasks", self.open_scheduled_tasks),
            )

    def _build_ai_hub_page(self, page):
        try:
            from gui.ai_hub_dialog import AIHubView

            AIHubView(page, self.ai_manager, on_close=lambda: self._switch_view("monitors")).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="AI Hub",
                subtitle="Unified AI operations for folders (rename, categorize, analysis).",
                primary=("Open AI Hub", self.open_ai_hub),
            )

    def _build_ai_command_page(self, page):
        try:
            from gui.ai_command_dialog import AICommandView

            AICommandView(page, ai_manager=self.ai_manager).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="AI Command",
                subtitle="Natural language → workflow plan → run locally.",
                primary=("Open AI Command Center", self.open_ai_command),
            )

    def _build_ai_search_page(self, page):
        try:
            from gui.ai_search_dialog import AISearchView

            AISearchView(page, ai_manager=self.ai_manager).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="AI Search",
                subtitle="Local semantic search over indexed files.",
                primary=("Open AI Search", self.open_ai_search),
            )

    def _build_file_tools_page(self, page):
        try:
            from gui.file_tools_dialog import FileToolsView

            FileToolsView(page, ai_manager=self.ai_manager, settings_manager=self.settings_manager).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="File Tools",
                subtitle="Convert, ZIP/7z, PDF tools, and batch operations.",
                primary=("Open File Tools", self.open_file_tools),
            )

    def _build_media_editors_page(self, page):
        try:
            from gui.media_editors_dialog import MediaEditorsView

            MediaEditorsView(page, ai_manager=self.ai_manager).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="Media Editors",
                subtitle="Open the Audio Editor and Video Editor.",
                primary=("Open Media Editors", self.open_media_editors),
            )

    def _build_workspace_page(self, page):
        try:
            from gui.workspace_dialog import WorkspaceView

            WorkspaceView(page, ai_manager=self.ai_manager).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="Workspace",
                subtitle="Unified target folder + multi-tool runs.",
                primary=("Open Workspace", self.open_workspace),
            )

    def _build_settings_page(self, page):
        try:
            from gui.settings_dialog import SettingsView

            SettingsView(page, self.settings_manager, monitor_manager=self.monitor_manager).pack(fill="both", expand=True)
        except Exception:
            self._build_launcher_page(
                page,
                title="Settings",
                subtitle="Configure AI model, tools, and preferences.",
                primary=("Open Settings", self.show_settings),
            )

    def _build_launcher_page(self, page, *, title: str, subtitle: str, primary=None, secondary=None):
        shell = ctk.CTkFrame(page, corner_radius=12, fg_color=("#f5f5f5", "#232323"))
        shell.pack(fill="both", expand=True, padx=12, pady=12)
        shell.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(shell, text=title, font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, padx=18, pady=(18, 6), sticky="w"
        )
        ctk.CTkLabel(shell, text=subtitle, text_color="gray", anchor="w").grid(row=1, column=0, padx=18, pady=(0, 18), sticky="w")

        btn_row = ctk.CTkFrame(shell, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="w")
        if primary:
            text, cmd = primary
            ctk.CTkButton(btn_row, text=text, width=220, height=40, command=cmd).pack(side="left", padx=(0, 10))
        if secondary:
            text, cmd = secondary
            ctk.CTkButton(btn_row, text=text, width=220, height=40, fg_color="#444", command=cmd).pack(side="left")

    def _show_page(self, view_name: str):
        self._ensure_page_built(view_name)
        # Important for resize performance: don't keep every page mapped.
        # With Tk/CustomTkinter, all mapped pages participate in geometry/layout on every resize
        # even if they are not on top (tkraise only changes stacking order).
        pages = (self.pages or {})
        for name, p in pages.items():
            try:
                if name == view_name:
                    # grid() with no args restores the previous grid config after grid_remove().
                    p.grid()
                else:
                    p.grid_remove()
            except Exception:
                pass

        page = pages.get(view_name) or pages.get("monitors")
        try:
            page.tkraise()
        except Exception:
            pass

        # Only show monitor creation buttons when on the Monitors page
        self._set_monitor_buttons_visible(view_name == "monitors")

    def _set_monitor_buttons_visible(self, visible: bool):
        try:
            if visible:
                if not self.add_btn.winfo_ismapped():
                    # Pack order (right): FTP then Folder monitor buttons
                    try:
                        self.add_ftp_btn.pack_forget()
                        self.add_btn.pack_forget()
                    except Exception:
                        pass
                    self.add_ftp_btn.pack(side="right", padx=4, pady=0)
                    self.add_btn.pack(side="right", padx=4, pady=0)
            else:
                if self.add_btn.winfo_ismapped():
                    self.add_ftp_btn.pack_forget()
                    self.add_btn.pack_forget()
        except Exception:
            pass

    def _create_status_bar(self):
        """Create bottom status bar"""
        self.status_frame = ctk.CTkFrame(self.right_container, height=30, corner_radius=0)
        self.status_frame.pack(fill="x", side="bottom")
        self.status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready",
            font=ctk.CTkFont(size=11)
        )
        self.status_label.pack(side="left", padx=10)

        # Active monitors count
        self.monitors_count_label = ctk.CTkLabel(
            self.status_frame,
            text="Active Monitors: 0",
            font=ctk.CTkFont(size=11)
        )
        self.monitors_count_label.pack(side="right", padx=10)

    def add_monitor(self):
        """Open dialog to add new folder monitor"""
        dialog = AddMonitorDialog(self.root, self._on_monitor_added)

    def add_ftp_monitor(self):
        """Open dialog to add new FTP monitor"""
        dialog = AddFTPDialog(self.root, self._on_ftp_monitor_added)

    def open_ai_hub(self):
        """Open AI Hub - Unified AI operations center"""
        from gui.ai_hub_dialog import AIHubDialog
        from tkinter import messagebox

        # Check if AI manager is ready
        if not hasattr(self, 'ai_manager') or not self.ai_manager:
            messagebox.showwarning(
                "AI Not Available",
                "AI features are not initialized. Please check Settings."
            )
            return

        if not self.ai_manager.is_ready:
            if self.ai_manager.model_files_exist():
                # Model exists, just load it into memory
                from gui.ai_loading_dialog import AILoadingDialog
                loading_dialog = AILoadingDialog(self.root, self.ai_manager)
                self.root.wait_window(loading_dialog)

                if not self.ai_manager.is_ready:
                    return
            else:
                # Model doesn't exist, ask to download
                result = messagebox.askyesno(
                    "AI Model Download Required",
                    "AI model needs to be downloaded first (2.4GB).\nThis is a one-time download and may take a few minutes.\n\nContinue?"
                )
                if result:
                    from gui.ai_loading_dialog import AILoadingDialog
                    loading_dialog = AILoadingDialog(self.root, self.ai_manager)
                    self.root.wait_window(loading_dialog)

                    if not self.ai_manager.is_ready:
                        return
                else:
                    return

        # Open AI Hub
        AIHubDialog(self.root, self.ai_manager)

    def open_ai_search(self):
        """Open AI Search - local semantic search over indexed files"""
        from gui.ai_search_dialog import AISearchDialog
        from tkinter import messagebox

        if not hasattr(self, 'ai_manager') or not self.ai_manager:
            messagebox.showwarning(
                "AI Not Available",
                "AI features are not initialized. Please check Settings."
            )
            return

        if not self.ai_manager.is_ready:
            if self.ai_manager.model_files_exist():
                from gui.ai_loading_dialog import AILoadingDialog
                loading_dialog = AILoadingDialog(self.root, self.ai_manager)
                self.root.wait_window(loading_dialog)
            else:
                # AI Search still works without AI summaries; allow user to proceed without downloading.
                proceed = messagebox.askyesno(
                    "AI Model Not Loaded",
                    "AI Search can work without the model (filename/text search),\n"
                    "but natural-language summaries work best with the model.\n\n"
                    "Load the model now?"
                )
                if proceed:
                    from gui.ai_loading_dialog import AILoadingDialog
                    loading_dialog = AILoadingDialog(self.root, self.ai_manager)
                    self.root.wait_window(loading_dialog)

        AISearchDialog(self.root, self.ai_manager)

    def open_ai_command(self, prefill_text: str = ""):
        """Open AI Command Center - natural language multi-step actions"""
        from gui.ai_command_dialog import AICommandDialog
        from tkinter import messagebox

        if not hasattr(self, 'ai_manager') or not self.ai_manager:
            messagebox.showwarning(
                "AI Not Available",
                "AI features are not initialized. Please check Settings."
            )
            return

        if not self.ai_manager.is_ready:
            try:
                if self.ai_manager.model_files_exist():
                    from gui.ai_loading_dialog import AILoadingDialog
                    loading_dialog = AILoadingDialog(self.root, self.ai_manager)
                    self.root.wait_window(loading_dialog)
            except Exception:
                pass

        dialog = AICommandDialog(self.root, self.ai_manager)
        if prefill_text:
            try:
                dialog.prompt.delete("1.0", "end")
                dialog.prompt.insert("1.0", prefill_text)
            except Exception:
                pass

    def open_file_tools(self):
        """Open File Tools - conversions, PDF and ZIP utilities"""
        from gui.file_tools_dialog import FileToolsDialog

        FileToolsDialog(self.root, self.ai_manager, self.settings_manager)

    def open_scheduled_tasks(self):
        """Open Scheduled Tasks manager dialog"""
        from gui.scheduled_tasks_dialog import ScheduledTasksDialog

        ScheduledTasksDialog(self.root, self.monitor_manager)

    def open_media_editors(self):
        """Open Media Editors - audio/video editors launcher"""
        from gui.media_editors_dialog import MediaEditorsDialog

        MediaEditorsDialog(self.root, self.ai_manager)

    def open_workspace(self):
        """Open Workspace - unified target folder + multi-tool runs"""
        from gui.workspace_dialog import WorkspaceDialog

        WorkspaceDialog(self.root, self.ai_manager)

    def open_ai_rule_builder(self):
        """Open AI Natural Language Rule Builder"""
        from gui.nl_rule_dialog import NLRuleDialog
        from core.nl_rule_builder import NaturalLanguageRuleBuilder
        from tkinter import messagebox

        if not hasattr(self, 'ai_manager') or not self.ai_manager:
            messagebox.showwarning(
                "AI Not Available",
                "AI features are not initialized. Please check Settings."
            )
            return

        if not self.ai_manager.is_ready:
            try:
                if self.ai_manager.model_files_exist():
                    from gui.ai_loading_dialog import AILoadingDialog
                    loading_dialog = AILoadingDialog(self.root, self.ai_manager)
                    self.root.wait_window(loading_dialog)
            except Exception:
                pass

        # Create NL rule builder if not exists
        if not hasattr(self, 'nl_rule_builder'):
            self.nl_rule_builder = NaturalLanguageRuleBuilder(self.ai_manager)

        # Open dialog
        def on_rule_created(rule, monitor_id=None, folder_path=None):
            """Handle rule creation"""
            if monitor_id and not folder_path:
                # Rule added to existing monitor - refresh UI
                self._refresh_monitor_card(monitor_id)
            elif monitor_id and folder_path:
                # New monitor created - add card
                self._create_monitor_card(monitor_id, folder_path, [rule])

        NLRuleDialog(
            self.root,
            self.nl_rule_builder,
            self.monitor_manager,
            current_folder=None,
            on_rule_created=on_rule_created
        )

    def _on_monitor_added(self, monitor_data: Dict):
        """Callback when a new folder monitor is added"""
        import uuid

        monitor_id = str(uuid.uuid4())

        # Add to monitor manager
        success = self.monitor_manager.add_monitor(
            monitor_id,
            monitor_data["path"],
            monitor_data["rules"],
            monitor_data.get("notify_created", True),
            monitor_data.get("notify_modified", True),
            monitor_data.get("notify_deleted", True),
            monitor_data.get("notify_moved", True),
            monitor_data.get("email_recipient", ""),
            monitor_data.get("min_size_kb"),
            monitor_data.get("max_size_kb"),
            monitor_data.get("modified_within_days"),
            monitor_data.get("exclude_patterns"),
            monitor_data.get("filename_regex")
        )

        if success:
            # Create monitor card
            self._create_monitor_card(
                monitor_id,
                monitor_data["path"],
                monitor_data["rules"]
            )

            # Auto-start if enabled
            if monitor_data.get("auto_start", True):
                self.monitor_manager.start_monitor(monitor_id)

            # Hide empty label
            self.empty_label.pack_forget()

            # Update status
            self._update_monitors_count()
            self.update_status("Folder monitor added successfully")
        else:
            from tkinter import messagebox

            msg = str(getattr(self.monitor_manager, "last_error", "") or "Could not add monitor.")
            messagebox.showerror("Add Monitor Failed", msg)

    def _on_ftp_monitor_added(self, monitor_data: Dict):
        """Callback when a new FTP monitor is added"""
        import uuid

        monitor_id = str(uuid.uuid4())

        # Add to FTP monitor manager
        try:
            success = self.monitor_manager.ftp_manager.add_ftp_monitor(
                monitor_id,
                monitor_data["host"],
                monitor_data["username"],
                monitor_data["password"],
                monitor_data["remote_path"],
                monitor_data["port"],
                monitor_data["use_tls"],
                monitor_data["poll_interval"],
                self._on_monitor_event
            )
        except Exception as e:
            success = False
            self.monitor_manager.ftp_manager.last_error = str(e)

        if success:
            # Create monitor card for FTP
            ftp_monitor = self.monitor_manager.ftp_manager.get_ftp_monitor(monitor_id)
            display_path = f"ftp://{monitor_data['host']}{monitor_data['remote_path']}"

            self._create_monitor_card(
                monitor_id,
                display_path,
                [],  # No rules for FTP yet
                is_ftp=True
            )

            # Auto-start if enabled
            if monitor_data.get("auto_start", True):
                started = self.monitor_manager.ftp_manager.start_ftp_monitor(monitor_id)
                if not started:
                    msg = str(getattr(self.monitor_manager.ftp_manager, "last_error", "") or "Could not start FTP monitor.")
                    messagebox.showerror("Start FTP Monitor Failed", msg)

            # Hide empty label
            self.empty_label.pack_forget()

            # Update status
            self._update_monitors_count()
            self.update_status("FTP monitor added successfully")
        else:
            msg = str(getattr(self.monitor_manager.ftp_manager, "last_error", "") or "Could not add FTP monitor.")
            messagebox.showerror("Add FTP Monitor Failed", msg)

    def _create_monitor_card(self, monitor_id: str, path: str, rules: List[Dict], is_ftp: bool = False):
        """Create a monitor card widget"""
        if is_ftp:
            monitor = self.monitor_manager.ftp_manager.get_ftp_monitor(monitor_id)
        else:
            monitor = self.monitor_manager.get_monitor(monitor_id)

        card = MonitorCard(
            self.scrollable_frame,
            monitor_id,
            path,
            rules,
            monitor,
            self._on_start_monitor,
            self._on_stop_monitor,
            self._on_remove_monitor,
            is_ftp=is_ftp,
            save_callback=self.monitor_manager.save_monitors
        )
        card.pack(fill="x", padx=10, pady=5)

        self.monitor_cards[monitor_id] = card

    def _refresh_monitor_card(self, monitor_id: str):
        """Refresh an existing monitor card after rule changes"""
        if monitor_id in self.monitor_cards:
            card = self.monitor_cards[monitor_id]
            card.destroy()
            del self.monitor_cards[monitor_id]

            # Force reload monitor from saved config
            self.monitor_manager.save_monitors()  # Ensure saved

            # Recreate the card with updated rules
            monitor = self.monitor_manager.get_monitor(monitor_id)
            if monitor:
                self._create_monitor_card(
                    monitor_id,
                    monitor.path,
                    monitor.rules
                )

                # Update status
                self.update_status(f"Monitor rules updated: {Path(monitor.path).name}")

    def _on_start_monitor(self, monitor_id: str, is_ftp: bool = False):
        """Start a monitor"""
        if is_ftp:
            success = self.monitor_manager.ftp_manager.start_ftp_monitor(monitor_id)
        else:
            success = self.monitor_manager.start_monitor(monitor_id)

        if success:
            self.update_status(f"Monitor started: {monitor_id[:8]}...")
            self._update_monitors_count()
        else:
            from tkinter import messagebox

            manager = self.monitor_manager.ftp_manager if is_ftp else self.monitor_manager
            msg = str(getattr(manager, "last_error", "") or "Could not start monitor.")
            messagebox.showerror("Start Monitor Failed", msg)

    def _on_stop_monitor(self, monitor_id: str, is_ftp: bool = False):
        """Stop a monitor"""
        if is_ftp:
            success = self.monitor_manager.ftp_manager.stop_ftp_monitor(monitor_id)
        else:
            success = self.monitor_manager.stop_monitor(monitor_id)

        if success:
            self.update_status(f"Monitor stopped: {monitor_id[:8]}...")
            self._update_monitors_count()

    def _on_remove_monitor(self, monitor_id: str, is_ftp: bool = False):
        """Remove a monitor"""
        if monitor_id in self.monitor_cards:
            self.monitor_cards[monitor_id].destroy()
            del self.monitor_cards[monitor_id]

        if is_ftp:
            self.monitor_manager.ftp_manager.remove_ftp_monitor(monitor_id)
        else:
            self.monitor_manager.remove_monitor(monitor_id)

        self.update_status(f"Monitor removed")
        self._update_monitors_count()

        # Show empty label if no monitors
        if len(self.monitor_cards) == 0:
            self.empty_label.pack(pady=100)

    def _on_monitor_event(self, monitor_id: str, event_type: str,
                          src_path: str, dest_path: str = None):
        """Handle monitor events"""
        # Avoid doing extra UI work while the user is live-resizing the window.
        if getattr(self, "_resize_active", False):
            return
        # Update monitor card with new event
        if monitor_id in self.monitor_cards:
            self.monitor_cards[monitor_id].add_event(event_type, src_path)

        # Update status bar
        file_name = Path(src_path).name
        self.update_status(f"{event_type.title()}: {file_name}")

    def _update_monitors_count(self):
        """Update active monitors count"""
        # Count folder monitors
        folder_active = sum(
            1 for m in self.monitor_manager.get_all_monitors().values()
            if m.is_running
        )
        folder_total = len(self.monitor_manager.get_all_monitors())

        # Count FTP monitors
        ftp_active = sum(
            1 for m in self.monitor_manager.ftp_manager.ftp_monitors.values()
            if m.is_running
        )
        ftp_total = len(self.monitor_manager.ftp_manager.ftp_monitors)

        active_count = folder_active + ftp_active
        total_count = folder_total + ftp_total

        self.monitors_count_label.configure(
            text=f"Active: {active_count} / {total_count}"
        )

    def update_status(self, message: str):
        """Update status bar message"""
        self.status_label.configure(text=message)

    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self.root, self.settings_manager, self.monitor_manager)
        # Wait for dialog to close, then reinitialize email notifier
        self.root.wait_window(dialog)
        self.monitor_manager._init_email_notifier()

    def minimize_to_tray(self):
        """Minimize window to system tray"""
        self.root.withdraw()
        self.tray_manager.show_tray()

    def on_tray_restore(self):
        """Restore window from system tray"""
        self.root.deiconify()
        self.tray_manager.hide_tray()

    def restore_monitors(self, loaded_monitors: List[Dict]):
        """Restore monitors from saved data"""
        for monitor_data in loaded_monitors:
            if monitor_data["type"] == "folder":
                # Create folder monitor card
                self._create_monitor_card(
                    monitor_data["id"],
                    monitor_data["path"],
                    monitor_data["rules"],
                    is_ftp=False
                )

                # Auto-start if it was running before
                if monitor_data.get("auto_start", False):
                    self.monitor_manager.start_monitor(monitor_data["id"])

            elif monitor_data["type"] == "ftp":
                # Create FTP monitor card
                ftp_monitor = self.monitor_manager.ftp_manager.get_ftp_monitor(monitor_data["id"])
                display_path = f"ftp://{monitor_data['host']}{monitor_data['remote_path']}"

                self._create_monitor_card(
                    monitor_data["id"],
                    display_path,
                    [],
                    is_ftp=True
                )

                # Auto-start if it was running before
                if monitor_data.get("auto_start", False):
                    self.monitor_manager.ftp_manager.start_ftp_monitor(monitor_data["id"])

        # Hide empty label if monitors were loaded
        if loaded_monitors:
            self.empty_label.pack_forget()

        # Update counter
        self._update_monitors_count()

        self.update_status(f"Loaded {len(loaded_monitors)} monitors from saved settings")
