"""
Fylorra - AI Hub Dialog
Unified interface for all AI features with pipeline support
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from core.bulk_ai_processor import BulkAIProcessor
from utils.png_icons import PNGIconLoader


class _AIHubUI:
    def _init_common(self, ai_manager, default_folder: Optional[Path] = None, *, on_close=None):
        self.ai_manager = ai_manager
        self.icon_loader = PNGIconLoader()
        self.bulk_processor = BulkAIProcessor(ai_manager)

        self.selected_folder = default_folder
        self.operation_checkboxes: Dict[str, ctk.BooleanVar] = {}
        self._filter_pills: Dict[str, ctk.CTkFrame] = {}

        self._on_close = on_close or (lambda: None)

    def _bring_to_front(self):
        win = self if isinstance(self, (ctk.CTkToplevel, tk.Toplevel)) else self.winfo_toplevel()
        try:
            win.lift()
        except Exception:
            pass
        try:
            win.attributes("-topmost", True)
            win.after(200, lambda: win.attributes("-topmost", False))
        except Exception:
            pass
        try:
            win.focus_force()
        except Exception:
            pass

    def _create_ui(self):
        # Use grid so footer buttons are always visible.
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # Header uses grid (no fixed height) to avoid font clipping on DPI scaling.
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=30, pady=(16, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        ai_icon = self.icon_loader.load_icon("analytics", size=(48, 48))
        icon_label = ctk.CTkLabel(header_frame, image=ai_icon, text="")
        icon_label.image = ai_icon
        icon_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 12), pady=(6, 0))

        title = ctk.CTkLabel(
            header_frame,
            text="Fylorra AI Hub",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
        )
        title.grid(row=0, column=1, sticky="w", pady=(2, 0))

        subtitle = ctk.CTkLabel(
            header_frame,
            text="Unified AI Operations Center • Process folders with multiple AI features",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("#a7abb3", "#a7abb3"),
        )
        subtitle.grid(row=1, column=1, sticky="w", pady=(0, 2))

        close_btn = ctk.CTkButton(
            header_frame,
            text="✕",
            width=32,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            hover_color=("#2a2e35", "#2a2e35"),
            text_color=("#ffffff", "#ffffff"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            command=self._on_close,
        )
        close_btn.grid(row=0, column=2, rowspan=2, sticky="ne")

        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 10))
        body_frame.grid_rowconfigure(0, weight=0)
        body_frame.grid_rowconfigure(1, weight=1)
        body_frame.grid_columnconfigure(0, weight=1)

        # Top panel - Target Folder + File Filters
        top_panel = ctk.CTkFrame(
            body_frame,
            fg_color=("#272b32", "#272b32"),
            corner_radius=14,
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
        )
        top_panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_panel.grid_columnconfigure(0, weight=3)
        top_panel.grid_columnconfigure(1, weight=0)
        top_panel.grid_columnconfigure(2, weight=2)

        folder_section = ctk.CTkFrame(top_panel, fg_color="transparent")
        folder_section.grid(row=0, column=0, sticky="nsew", padx=(16, 10), pady=14)

        folder_label = ctk.CTkLabel(
            folder_section,
            text="Target Folder",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        folder_label.pack(anchor="w", pady=(0, 10))

        folder_input_frame = ctk.CTkFrame(folder_section, fg_color="transparent")
        folder_input_frame.pack(fill="x", pady=(0, 10))
        folder_input_frame.grid_columnconfigure(0, weight=1)

        self.folder_entry = ctk.CTkEntry(
            folder_input_frame,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            placeholder_text="Select a folder to process...",
            fg_color=("#1f232a", "#1f232a"),
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
            corner_radius=10,
        )
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        if self.selected_folder:
            self.folder_entry.insert(0, str(self.selected_folder))

        browse_btn = ctk.CTkButton(
            folder_input_frame,
            text="Browse",
            width=130,
            height=38,
            command=self._browse_folder,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=("#0d6efd", "#0d6efd"),
            hover_color=("#0b5ed7", "#0b5ed7"),
            corner_radius=10,
        )
        browse_btn.grid(row=0, column=1, sticky="e")

        self.include_subfolders_var = ctk.BooleanVar(value=True)
        subfolder_checkbox = ctk.CTkCheckBox(
            folder_section,
            text="Include subfolders (recursive)",
            variable=self.include_subfolders_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            checkbox_width=22,
            checkbox_height=22,
            fg_color=("#0d6efd", "#0d6efd"),
            hover_color=("#0b5ed7", "#0b5ed7"),
            border_color=("#3a3f46", "#3a3f46"),
            text_color=("#d8dbe2", "#d8dbe2"),
        )
        subfolder_checkbox.pack(anchor="w")

        divider = ctk.CTkFrame(top_panel, width=1, fg_color=("#3a3f46", "#3a3f46"))
        divider.grid(row=0, column=1, sticky="ns", pady=18)

        filters_section = ctk.CTkFrame(top_panel, fg_color="transparent")
        filters_section.grid(row=0, column=2, sticky="nsew", padx=(10, 16), pady=14)

        filter_label = ctk.CTkLabel(
            filters_section,
            text="File Filters",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        filter_label.pack(anchor="w", pady=(0, 10))

        filters_grid = ctk.CTkFrame(filters_section, fg_color="transparent")
        filters_grid.pack(fill="x")
        for col in range(3):
            filters_grid.grid_columnconfigure(col, weight=1)

        self.filter_var = ctk.StringVar(value="all")
        filter_options = [
            ("All Files", "all"),
            ("Images Only", "images"),
            ("Videos Only", "videos"),
            ("Documents Only", "documents"),
            ("Code Files Only", "code"),
        ]

        for idx, (label, value) in enumerate(filter_options):
            row = 0 if idx < 3 else 1
            col = idx if idx < 3 else idx - 3
            pill = self._create_filter_pill(filters_grid, label=label, value=value)
            pill.grid(row=row, column=col, sticky="w", padx=(0, 10), pady=(0, 10))

        self._update_filter_pills()

        # AI Operations panel (scrollable body, no visible scrollbar)
        ops_panel = ctk.CTkFrame(
            body_frame,
            fg_color=("#272b32", "#272b32"),
            corner_radius=14,
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
        )
        ops_panel.grid(row=1, column=0, sticky="nsew")
        ops_panel.grid_rowconfigure(1, weight=1)
        ops_panel.grid_columnconfigure(0, weight=1)

        ops_header = ctk.CTkFrame(ops_panel, fg_color="transparent")
        ops_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        ops_title = ctk.CTkLabel(
            ops_header,
            text="AI Operations",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        ops_title.pack(side="left")

        ops_hint = ctk.CTkLabel(
            ops_header,
            text="Select one or more options",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("#a7abb3", "#a7abb3"),
        )
        ops_hint.pack(side="left", padx=(14, 0))

        cards_host = ctk.CTkFrame(ops_panel, fg_color="transparent")
        cards_host.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        cards_host.grid_rowconfigure(0, weight=1)
        cards_host.grid_columnconfigure(0, weight=1)

        scroll_wrapper, cards_container = self._create_hidden_scroll_area(cards_host, bg_color="#272b32")
        scroll_wrapper.grid(row=0, column=0, sticky="nsew")

        self._create_operation_card(
            cards_container,
            "smart_rename",
            "Smart Rename",
            "Rename files using AI vision\nanalysis and smart rules",
            "edit",
            default_checked=True,
            available=True,
            position=0,
            row=0,
        )

        self._create_operation_card(
            cards_container,
            "auto_categorize",
            "Auto-Categorize",
            "Organize files into 51\ncomprehensive categories",
            "grid",
            default_checked=True,
            available=True,
            position=1,
            row=0,
        )

        self._create_operation_card(
            cards_container,
            "duplicate_finder",
            "Duplicate Detection",
            "Find duplicate files using AI\nvision similarity (coming soon)",
            "search",
            default_checked=False,
            available=False,
            position=2,
            row=0,
        )

        self._create_operation_card(
            cards_container,
            "semantic_analysis",
            "Content Analysis",
            "Analyze and classify content\nwith AI understanding",
            "analytics",
            default_checked=False,
            available=True,
            position=0,
            row=1,
        )

        self._create_operation_card(
            cards_container,
            "security_scan",
            "Security Scan",
            "Scan folders for suspicious\nfiles and risks using AI",
            "shield",
            default_checked=False,
            available=True,
            position=1,
            row=1,
        )

        # Footer - always visible
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=2, column=0, sticky="ew", padx=30, pady=(0, 16))
        footer_frame.grid_columnconfigure(0, weight=1)

        separator = ctk.CTkFrame(footer_frame, height=1, fg_color=("#3a3a3a", "#3a3a3a"))
        separator.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        buttons_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        buttons_frame.grid(row=1, column=0, sticky="ew")

        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=150,
            height=42,
            command=self._on_close,
            fg_color=("#4f555e", "#4f555e"),
            hover_color=("#5c636e", "#5c636e"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=10,
        )
        cancel_btn.pack(side="left")

        self.start_btn = ctk.CTkButton(
            buttons_frame,
            text="Start AI Operations",
            width=240,
            height=42,
            command=self._start_operations,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=("#0d6efd", "#0d6efd"),
            hover_color=("#0b5ed7", "#0b5ed7"),
            corner_radius=10,
        )
        self.start_btn.pack(side="right")

    def _create_hidden_scroll_area(
        self,
        parent: ctk.CTkFrame,
        *,
        bg_color: str,
    ) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        """Scrollable container without a visible scrollbar (mouse-wheel only)."""
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            wrapper,
            highlightthickness=0,
            bd=0,
            bg=bg_color,
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        inner = ctk.CTkFrame(wrapper, fg_color="transparent")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_mousewheel_linux(event):
            if event.num == 4:
                canvas.yview_scroll(-3, "units")
            elif event.num == 5:
                canvas.yview_scroll(3, "units")

        for widget in (canvas, inner):
            widget.bind("<MouseWheel>", on_mousewheel)
            widget.bind("<Button-4>", on_mousewheel_linux)
            widget.bind("<Button-5>", on_mousewheel_linux)

        return wrapper, inner

    def _create_filter_pill(self, parent, *, label: str, value: str) -> ctk.CTkFrame:
        pill = ctk.CTkFrame(
            parent,
            fg_color=("#1f232a", "#1f232a"),
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
            corner_radius=18,
        )
        pill.grid_columnconfigure(1, weight=1)

        radio = ctk.CTkRadioButton(
            pill,
            text=label,
            value=value,
            variable=self.filter_var,
            command=self._update_filter_pills,
            fg_color=("#0d6efd", "#0d6efd"),
            border_color=("#6b737f", "#6b737f"),
            hover_color=("#0b5ed7", "#0b5ed7"),
            text_color=("#d8dbe2", "#d8dbe2"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        radio.pack(side="left", padx=12, pady=7)

        self._filter_pills[value] = pill
        return pill

    def _update_filter_pills(self):
        selected = self.filter_var.get()
        for value, pill in self._filter_pills.items():
            is_selected = value == selected
            pill.configure(
                fg_color=("#0d6efd", "#0d6efd") if is_selected else ("#1f232a", "#1f232a"),
                border_color=("#0b5ed7", "#0b5ed7") if is_selected else ("#3a3f46", "#3a3f46"),
            )

    def _create_operation_card(
        self,
        parent: ctk.CTkFrame,
        op_id: str,
        title: str,
        description: str,
        icon_name: str,
        *,
        default_checked: bool,
        available: bool,
        position: int,
        row: int,
    ):
        col = position % 3
        card = ctk.CTkFrame(
            parent,
            fg_color=("#1f232a", "#1f232a"),
            corner_radius=14,
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
        )
        card.grid(
            row=row,
            column=col,
            padx=(10, 10),
            pady=(0, 10) if row == 0 else (0, 0),
            sticky="nsew",
        )

        parent.grid_columnconfigure(col, weight=1)
        parent.grid_rowconfigure(row, weight=1)

        var = ctk.BooleanVar(value=default_checked)
        self.operation_checkboxes[op_id] = var

        checkbox_frame = ctk.CTkFrame(card, fg_color="transparent", height=38)
        checkbox_frame.pack(fill="x")

        checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="",
            variable=var,
            width=24,
            height=24,
            checkbox_width=24,
            checkbox_height=24,
            state="normal" if available else "disabled",
            fg_color=("#0d6efd", "#0d6efd"),
            hover_color=("#0b5ed7", "#0b5ed7"),
            border_color=("#5a616b", "#5a616b"),
            checkmark_color=("#ffffff", "#ffffff"),
        )
        checkbox.pack(side="right", padx=14, pady=8)

        icon_container = ctk.CTkFrame(
            card,
            fg_color=("#272b32", "#272b32"),
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
            corner_radius=40,
            width=68,
            height=68,
        )
        icon_container.pack(pady=(8, 10))
        icon_container.pack_propagate(False)

        icon = self.icon_loader.load_icon(icon_name, size=(30, 30))
        if icon:
            icon_label = ctk.CTkLabel(icon_container, image=icon, text="")
            icon_label.image = icon
            icon_label.pack(expand=True)

        title_label = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        title_label.pack(pady=(0, 6))

        desc_label = ctk.CTkLabel(
            card,
            text=description,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=("#a7abb3", "#a7abb3"),
            justify="center",
            wraplength=200,
        )
        desc_label.pack(pady=(0, 14))

    def _browse_folder(self):
        parent = self.winfo_toplevel()
        folder = filedialog.askdirectory(
            title="Select Folder for AI Processing",
            initialdir=str(self.selected_folder) if self.selected_folder else None,
            parent=parent,
        )

        if folder:
            self.selected_folder = Path(folder)
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, str(self.selected_folder))

        self._bring_to_front()

    def _start_operations(self):
        folder_text = self.folder_entry.get().strip()
        if not folder_text:
            messagebox.showerror("No Folder Selected", "Please select or enter a folder to process.")
            return

        try:
            folder_path = Path(folder_text)
            if not folder_path.exists() or not folder_path.is_dir():
                messagebox.showerror("Invalid Folder", f"The folder does not exist:\n{folder_text}")
                return
        except Exception as e:
            messagebox.showerror("Invalid Path", f"Invalid folder path:\n{folder_text}\n\nError: {str(e)}")
            return

        self.selected_folder = folder_path

        selected_ops = [op_id for op_id, var in self.operation_checkboxes.items() if var.get()]
        if not selected_ops:
            messagebox.showwarning("No Operations Selected", "Please select at least one AI operation to perform.")
            return

        self._launch_operations(selected_ops)

    def _launch_operations(self, operations: List[str]):
        is_toplevel = isinstance(self, (ctk.CTkToplevel, tk.Toplevel))
        launch_parent = self.master if is_toplevel else self.winfo_toplevel()
        ai_manager = self.ai_manager
        selected_folder = self.selected_folder

        if is_toplevel:
            self.destroy()
        else:
            try:
                self._on_close()
            except Exception:
                pass

        launch_parent.after(
            100,
            lambda: self._launch_next_operation(launch_parent, ai_manager, selected_folder, operations, 0),
        )

    @staticmethod
    def _launch_next_operation(parent, ai_manager, folder_path, operations, index):
        if index >= len(operations):
            messagebox.showinfo("AI Hub Complete", f"All {len(operations)} AI operation(s) have been completed!")
            return

        op_id = operations[index]

        def on_complete_wrapper(original_callback=None):
            def on_complete(*args):
                if original_callback:
                    original_callback(*args)
                parent.after(
                    100,
                    lambda: _AIHubUI._launch_next_operation(
                        parent,
                        ai_manager,
                        folder_path,
                        operations,
                        index + 1,
                    ),
                )

            return on_complete

        try:
            if op_id == "smart_rename":
                _AIHubUI._launch_smart_rename_static(parent, ai_manager, folder_path, on_complete_wrapper())
            elif op_id == "auto_categorize":
                _AIHubUI._launch_auto_categorize_static(parent, ai_manager, folder_path, on_complete_wrapper())
            elif op_id == "semantic_analysis":
                _AIHubUI._launch_semantic_analysis_static(parent, ai_manager, folder_path, on_complete_wrapper())
            elif op_id == "security_scan":
                _AIHubUI._launch_security_scan_static(parent, ai_manager, folder_path, on_complete_wrapper())
            else:
                parent.after(100, lambda: on_complete_wrapper()())
        except Exception as e:
            messagebox.showerror("Operation Failed", f"Failed to launch operation '{op_id}':\n{e}")
            parent.after(100, lambda: on_complete_wrapper()())

    @staticmethod
    def _launch_smart_rename_static(parent, ai_manager, folder_path, on_complete_callback):
        from gui.smart_rename_dialog import SmartRenameDialog

        def on_complete(renamed_count):
            messagebox.showinfo("Smart Rename Complete", f"Successfully renamed {renamed_count} files!")
            if on_complete_callback:
                on_complete_callback(renamed_count)

        try:
            dialog = SmartRenameDialog(
                parent,
                ai_manager,
                [],
                on_complete,
                folder_mode=True,
                folder_path=folder_path,
            )
            dialog.deiconify()
            dialog.lift()
            dialog.focus_force()
            dialog.attributes("-topmost", True)
            dialog.after(100, lambda: dialog.attributes("-topmost", False))
        except Exception:
            if on_complete_callback:
                on_complete_callback(0)

    @staticmethod
    def _launch_auto_categorize_static(parent, ai_manager, folder_path, on_complete_callback):
        from gui.ai_categorize_dialog import AICategorizeDialog

        dialog = AICategorizeDialog(parent, ai_manager, None, folder_path)

        def check_closed():
            try:
                if not dialog.winfo_exists():
                    if on_complete_callback:
                        on_complete_callback()
                else:
                    parent.after(500, check_closed)
            except Exception:
                if on_complete_callback:
                    on_complete_callback()

        parent.after(500, check_closed)

    @staticmethod
    def _launch_semantic_analysis_static(parent, ai_manager, folder_path, on_complete_callback):
        from core.semantic_analyzer import SemanticAnalyzer
        from gui.semantic_analysis_dialog import SemanticAnalysisDialog

        semantic_analyzer = SemanticAnalyzer(ai_manager)
        dialog = SemanticAnalysisDialog(
            parent,
            semantic_analyzer,
            folder_path,
            on_action=None,
            folder_mode=True,
        )

        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()
        dialog.attributes("-topmost", True)
        dialog.after(100, lambda: dialog.attributes("-topmost", False))

        def check_closed():
            try:
                if not dialog.winfo_exists():
                    if on_complete_callback:
                        on_complete_callback()
                else:
                    parent.after(500, check_closed)
            except Exception:
                if on_complete_callback:
                    on_complete_callback()

        parent.after(500, check_closed)

    @staticmethod
    def _launch_security_scan_static(parent, ai_manager, folder_path, on_complete_callback):
        from gui.ai_security_scan_dialog import AISecurityScanDialog

        dialog = AISecurityScanDialog(parent, ai_manager, folder_path)

        def check_closed():
            try:
                if not dialog.winfo_exists():
                    if on_complete_callback:
                        on_complete_callback()
                else:
                    parent.after(500, check_closed)
            except Exception:
                if on_complete_callback:
                    on_complete_callback()

        parent.after(500, check_closed)


class AIHubView(_AIHubUI, ctk.CTkFrame):
    """Embeddable AI Hub view (used in MainWindow)."""

    def __init__(self, parent, ai_manager, default_folder: Optional[Path] = None, *, on_close=None):
        super().__init__(parent, fg_color=("#1c1f24", "#1c1f24"))
        self._init_common(ai_manager, default_folder, on_close=on_close)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)
        self._create_ui()


class AIHubDialog(_AIHubUI, ctk.CTkToplevel):
    """Unified AI Hub - Central interface for all AI operations"""

    def __init__(self, parent, ai_manager, default_folder: Optional[Path] = None):
        super().__init__(parent)
        self._init_common(ai_manager, default_folder, on_close=self.destroy)

        self.title("Fylorra AI Hub")
        self.geometry("1024x720")
        self.resizable(True, True)
        self.minsize(980, 680)
        self.configure(fg_color=("#1c1f24", "#1c1f24"))

        self.transient(parent)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 512
        y = (self.winfo_screenheight() // 2) - 360
        self.geometry(f"1024x720+{x}+{y}")

        self._create_ui()
        self.after(10, self._bring_to_front)

        # Nothing else to do here; body/footer are built in _create_ui().

    def _create_hidden_scroll_area(
        self,
        parent: ctk.CTkFrame,
        *,
        bg_color: str,
    ) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        return _AIHubUI._create_hidden_scroll_area(self, parent, bg_color=bg_color)

    def _create_filter_pill(self, parent, *, label: str, value: str) -> ctk.CTkFrame:
        pill = ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color=("#1f232a", "#1f232a"),
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
            height=32,
        )
        pill.grid_propagate(False)

        radio = ctk.CTkRadioButton(
            pill,
            text=label,
            variable=self.filter_var,
            value=value,
            command=self._update_filter_pills,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=("#ffffff", "#ffffff"),
            border_color=("#a7abb3", "#a7abb3"),
            hover_color=("#ffffff", "#ffffff"),
            text_color=("#d8dbe2", "#d8dbe2"),
        )
        radio.pack(side="left", padx=12, pady=7)

        def on_click(_event=None, v=value):
            self.filter_var.set(v)
            self._update_filter_pills()

        pill.bind("<Button-1>", on_click)
        radio.bind("<Button-1>", on_click)

        self._filter_pills[value] = pill
        return pill

    def _update_filter_pills(self):
        selected = self.filter_var.get()
        for value, pill in self._filter_pills.items():
            is_selected = value == selected
            pill.configure(
                fg_color=("#0d6efd", "#0d6efd") if is_selected else ("#1f232a", "#1f232a"),
                border_color=("#0b5ed7", "#0b5ed7") if is_selected else ("#3a3f46", "#3a3f46"),
            )

    def _create_operation_card(
        self,
        parent,
        op_id: str,
        title: str,
        description: str,
        icon_name: str,
        *,
        default_checked: bool,
        available: bool,
        position: int,
        row: int = 0,
    ):
        parent.grid_columnconfigure(0, weight=1, uniform="cards")
        parent.grid_columnconfigure(1, weight=1, uniform="cards")
        parent.grid_columnconfigure(2, weight=1, uniform="cards")
        parent.grid_rowconfigure(0, weight=1, uniform="cards_rows")
        parent.grid_rowconfigure(1, weight=1, uniform="cards_rows")

        card = ctk.CTkFrame(
            parent,
            fg_color=("#1f232a", "#1f232a"),
            corner_radius=14,
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
        )
        card.grid(
            row=row,
            column=position,
            padx=8,
            pady=(0, 10) if row == 0 else (0, 0),
            sticky="nsew",
        )

        var = ctk.BooleanVar(value=default_checked)
        self.operation_checkboxes[op_id] = var

        checkbox_frame = ctk.CTkFrame(card, fg_color="transparent", height=38)
        checkbox_frame.pack(fill="x")

        checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="",
            variable=var,
            width=24,
            height=24,
            checkbox_width=24,
            checkbox_height=24,
            state="normal" if available else "disabled",
            fg_color=("#0d6efd", "#0d6efd"),
            hover_color=("#0b5ed7", "#0b5ed7"),
            border_color=("#5a616b", "#5a616b"),
            checkmark_color=("#ffffff", "#ffffff"),
        )
        checkbox.pack(side="right", padx=14, pady=8)

        icon_container = ctk.CTkFrame(
            card,
            fg_color=("#272b32", "#272b32"),
            border_width=1,
            border_color=("#3a3f46", "#3a3f46"),
            corner_radius=40,
            width=68,
            height=68,
        )
        icon_container.pack(pady=(8, 10))
        icon_container.pack_propagate(False)

        icon = self.icon_loader.load_icon(icon_name, size=(30, 30))
        if icon:
            icon_label = ctk.CTkLabel(icon_container, image=icon, text="")
            icon_label.image = icon
            icon_label.pack(expand=True)

        title_label = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        title_label.pack(pady=(0, 6))

        desc_label = ctk.CTkLabel(
            card,
            text=description,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=("#a7abb3", "#a7abb3"),
            justify="center",
            wraplength=200,
        )
        desc_label.pack(pady=(0, 14))

    def _browse_folder(self):
        folder = filedialog.askdirectory(
            title="Select Folder for AI Processing",
            initialdir=str(self.selected_folder) if self.selected_folder else None,
            parent=self,
        )

        if folder:
            self.selected_folder = Path(folder)
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, str(self.selected_folder))

        self._bring_to_front()

    def _start_operations(self):
        folder_text = self.folder_entry.get().strip()
        if not folder_text:
            messagebox.showerror("No Folder Selected", "Please select or enter a folder to process.")
            return

        try:
            folder_path = Path(folder_text)
            if not folder_path.exists() or not folder_path.is_dir():
                messagebox.showerror("Invalid Folder", f"The folder does not exist:\n{folder_text}")
                return
        except Exception as e:
            messagebox.showerror("Invalid Path", f"Invalid folder path:\n{folder_text}\n\nError: {str(e)}")
            return

        self.selected_folder = folder_path

        selected_ops = [op_id for op_id, var in self.operation_checkboxes.items() if var.get()]
        if not selected_ops:
            messagebox.showwarning("No Operations Selected", "Please select at least one AI operation to perform.")
            return

        self._launch_operations(selected_ops)

    def _launch_operations(self, operations: List[str]):
        is_toplevel = isinstance(self, (ctk.CTkToplevel, tk.Toplevel))
        launch_parent = self.master if is_toplevel else self.winfo_toplevel()
        ai_manager = self.ai_manager
        selected_folder = self.selected_folder

        if is_toplevel:
            self.destroy()
        else:
            try:
                self._on_close()
            except Exception:
                pass

        launch_parent.after(
            100,
            lambda: self._launch_next_operation(launch_parent, ai_manager, selected_folder, operations, 0),
        )

    @staticmethod
    def _launch_next_operation(parent, ai_manager, folder_path, operations, index):
        if index >= len(operations):
            messagebox.showinfo("AI Hub Complete", f"All {len(operations)} AI operation(s) have been completed!")
            return

        op_id = operations[index]

        def on_complete_wrapper(original_callback=None):
            def on_complete(*args):
                if original_callback:
                    original_callback(*args)
                parent.after(
                    100,
                    lambda: AIHubDialog._launch_next_operation(
                        parent,
                        ai_manager,
                        folder_path,
                        operations,
                        index + 1,
                    ),
                )

            return on_complete

        try:
            if op_id == "smart_rename":
                AIHubDialog._launch_smart_rename_static(parent, ai_manager, folder_path, on_complete_wrapper())
            elif op_id == "auto_categorize":
                AIHubDialog._launch_auto_categorize_static(parent, ai_manager, folder_path, on_complete_wrapper())
            elif op_id == "semantic_analysis":
                AIHubDialog._launch_semantic_analysis_static(parent, ai_manager, folder_path, on_complete_wrapper())
            elif op_id == "security_scan":
                AIHubDialog._launch_security_scan_static(parent, ai_manager, folder_path, on_complete_wrapper())
            else:
                parent.after(
                    100,
                    lambda: AIHubDialog._launch_next_operation(
                        parent,
                        ai_manager,
                        folder_path,
                        operations,
                        index + 1,
                    ),
                )
        except Exception:
            parent.after(
                100,
                lambda: AIHubDialog._launch_next_operation(
                    parent,
                    ai_manager,
                    folder_path,
                    operations,
                    index + 1,
                ),
            )

    @staticmethod
    def _launch_smart_rename_static(parent, ai_manager, folder_path, on_complete_callback):
        from gui.smart_rename_dialog import SmartRenameDialog

        def on_complete(renamed_count):
            messagebox.showinfo("Smart Rename Complete", f"Successfully renamed {renamed_count} files!")
            if on_complete_callback:
                on_complete_callback(renamed_count)

        try:
            dialog = SmartRenameDialog(
                parent,
                ai_manager,
                [],
                on_complete,
                folder_mode=True,
                folder_path=folder_path,
            )
            dialog.deiconify()
            dialog.lift()
            dialog.focus_force()
            dialog.attributes("-topmost", True)
            dialog.after(100, lambda: dialog.attributes("-topmost", False))
        except Exception:
            if on_complete_callback:
                on_complete_callback(0)

    @staticmethod
    def _launch_auto_categorize_static(parent, ai_manager, folder_path, on_complete_callback):
        from gui.ai_categorize_dialog import AICategorizeDialog

        dialog = AICategorizeDialog(parent, ai_manager, None, folder_path)

        def check_closed():
            try:
                if not dialog.winfo_exists():
                    if on_complete_callback:
                        on_complete_callback()
                else:
                    parent.after(500, check_closed)
            except Exception:
                if on_complete_callback:
                    on_complete_callback()

        parent.after(500, check_closed)

    @staticmethod
    def _launch_semantic_analysis_static(parent, ai_manager, folder_path, on_complete_callback):
        from core.semantic_analyzer import SemanticAnalyzer
        from gui.semantic_analysis_dialog import SemanticAnalysisDialog

        semantic_analyzer = SemanticAnalyzer(ai_manager)
        dialog = SemanticAnalysisDialog(
            parent,
            semantic_analyzer,
            folder_path,
            on_action=None,
            folder_mode=True,
        )

        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()
        dialog.attributes("-topmost", True)
        dialog.after(100, lambda: dialog.attributes("-topmost", False))

        def check_closed():
            try:
                if not dialog.winfo_exists():
                    if on_complete_callback:
                        on_complete_callback()
                else:
                    parent.after(500, check_closed)
            except Exception:
                if on_complete_callback:
                    on_complete_callback()

        parent.after(500, check_closed)

    @staticmethod
    def _launch_security_scan_static(parent, ai_manager, folder_path, on_complete_callback):
        from gui.ai_security_scan_dialog import AISecurityScanDialog

        dialog = AISecurityScanDialog(parent, ai_manager, folder_path)

        def check_closed():
            try:
                if not dialog.winfo_exists():
                    if on_complete_callback:
                        on_complete_callback()
                else:
                    parent.after(500, check_closed)
            except Exception:
                if on_complete_callback:
                    on_complete_callback()

        parent.after(500, check_closed)
