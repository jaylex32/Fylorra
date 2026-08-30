"""Monitor Card - Widget for displaying individual monitor information"""

import customtkinter as ctk
from typing import List, Dict, Callable
from pathlib import Path
from datetime import datetime
from utils.png_icons import get_icon_loader
from utils.tooltip import ToolTipHelper


class MonitorCard(ctk.CTkFrame):
    """Individual monitor card widget"""

    def __init__(self, parent, monitor_id: str, path: str, rules: List[Dict],
                 monitor, start_callback: Callable, stop_callback: Callable,
                 remove_callback: Callable, is_ftp: bool = False,
                 save_callback: Callable | None = None):
        super().__init__(parent, corner_radius=10, fg_color=("gray85", "gray20"))

        self.monitor_id = monitor_id
        self.path = path
        self.rules = rules
        self.monitor = monitor
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.remove_callback = remove_callback
        self.is_ftp = is_ftp
        self.save_callback = save_callback

        self.recent_events = []
        self.max_events = 5

        self._setup_ui()

    def _setup_ui(self):
        """Setup card UI"""
        # Main container with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=10)

        # Header row
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        header_frame.pack(fill="x")

        # Folder/FTP icon and path
        path_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        path_frame.pack(side="left", fill="x", expand=True)

        # Use better Unicode icons
        if self.is_ftp:
            icon = "◉"  # Globe/network icon
            icon_color = "#9C27B0"
        else:
            icon = "▣"  # Folder icon
            icon_color = "#4A90E2"

        folder_label = ctk.CTkLabel(
            path_frame,
            text=icon,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=icon_color
        )
        folder_label.pack(side="left", padx=(0, 10))

        self.path_label = ctk.CTkLabel(
            path_frame,
            text=self.path,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.path_label.pack(side="left", fill="x", expand=True)

        # Control buttons
        controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_frame.pack(side="right")

        # Load icons and store as instance variables
        icon_loader = get_icon_loader()
        self.play_icon = icon_loader.load_icon("play", (20, 20))
        self.pause_icon = icon_loader.load_icon("pause", (20, 20))
        self.edit_icon = icon_loader.load_icon("edit", (20, 20))
        self.delete_icon = icon_loader.load_icon("delete", (20, 20))

        self.start_stop_btn = ctk.CTkButton(
            controls_frame,
            text="",
            image=self.play_icon,
            width=40,
            height=32,
            command=self._toggle_monitoring,
            fg_color="#2fa572",
            hover_color="#106a43"
        )
        self.start_stop_btn.pack(side="left", padx=3)

        self.edit_btn = ctk.CTkButton(
            controls_frame,
            text="",
            image=self.edit_icon,
            width=40,
            height=32,
            command=self._edit,
            fg_color="#FF9800",
            hover_color="#F57C00"
        )
        self.edit_btn.pack(side="left", padx=3)

        self.remove_btn = ctk.CTkButton(
            controls_frame,
            text="",
            image=self.delete_icon,
            width=40,
            height=32,
            command=self._remove,
            fg_color="#d32f2f",
            hover_color="#9a0007"
        )
        self.remove_btn.pack(side="left", padx=3)

        # Run AI Rules Now button (only for folder monitors with AI-created rules)
        if not self.is_ftp and self.rules and self._has_ai_rules():
            try:
                # Use custom AI icon
                from PIL import Image
                ai_icon_path = Path(__file__).parent.parent / "assets" / "icons" / "ai.png"
                ai_img = Image.open(ai_icon_path).resize((20, 20), Image.Resampling.LANCZOS)
                self.ai_rules_icon = ctk.CTkImage(light_image=ai_img, dark_image=ai_img, size=(20, 20))

                self.run_rules_btn = ctk.CTkButton(
                    controls_frame,
                    text="",
                    image=self.ai_rules_icon,
                    width=40,
                    height=32,
                    command=self._run_rules_now,
                    fg_color="#9C27B0",
                    hover_color="#7B1FA2"
                )
                self.run_rules_btn.pack(side="left", padx=3)
            except Exception as e:
                # Fallback to text if icon fails
                self.run_rules_btn = ctk.CTkButton(
                    controls_frame,
                    text="AI",
                    width=40,
                    height=32,
                    command=self._run_rules_now,
                    fg_color="#9C27B0",
                    hover_color="#7B1FA2",
                    font=ctk.CTkFont(size=10, weight="bold")
                )
                self.run_rules_btn.pack(side="left", padx=3)

        # AI buttons (only for folder monitors)
        if not self.is_ftp:
            self.ai_rename_icon = icon_loader.load_icon("brain", (20, 20))
            self.ai_rename_btn = ctk.CTkButton(
                controls_frame,
                text="",
                image=self.ai_rename_icon,
                width=40,
                height=32,
                command=self._smart_rename,
                fg_color="#9C27B0",
                hover_color="#7B1FA2"
            )
            self.ai_rename_btn.pack(side="left", padx=3)

            # AI Categorize button
            self.ai_cat_icon = icon_loader.load_icon("grid", (20, 20))
            self.ai_cat_btn = ctk.CTkButton(
                controls_frame,
                text="",
                image=self.ai_cat_icon,
                width=40,
                height=32,
                command=self._ai_categorize,
                fg_color="#FF5722",
                hover_color="#E64A19"
            )
            self.ai_cat_btn.pack(side="left", padx=3)

            # AI Security Scan button
            self.ai_sec_icon = icon_loader.load_icon("shield", (20, 20))
            self.ai_sec_btn = ctk.CTkButton(
                controls_frame,
                text="",
                image=self.ai_sec_icon,
                width=40,
                height=32,
                command=self._ai_security_scan,
                fg_color="#F44336",
                hover_color="#D32F2F"
            )
            self.ai_sec_btn.pack(side="left", padx=3)

            # NEW: Semantic Document Analyzer button
            try:
                # Use custom AI_2 icon
                from PIL import Image
                ai2_icon_path = Path(__file__).parent.parent / "assets" / "icons" / "ai_2.png"
                ai2_img = Image.open(ai2_icon_path).resize((20, 20), Image.Resampling.LANCZOS)
                self.ai_doc_icon = ctk.CTkImage(light_image=ai2_img, dark_image=ai2_img, size=(20, 20))

                self.ai_doc_btn = ctk.CTkButton(
                    controls_frame,
                    text="",
                    image=self.ai_doc_icon,
                    width=40,
                    height=32,
                    command=self._analyze_document,
                    fg_color="#00BCD4",
                    hover_color="#0097A7"
                )
                self.ai_doc_btn.pack(side="left", padx=3)
            except Exception as e:
                # Fallback to old icon if custom fails
                self.ai_doc_icon = icon_loader.load_icon("analytics", (20, 20))
                self.ai_doc_btn = ctk.CTkButton(
                    controls_frame,
                    text="",
                    image=self.ai_doc_icon,
                    width=40,
                    height=32,
                    command=self._analyze_document,
                    fg_color="#00BCD4",
                    hover_color="#0097A7"
                )
                self.ai_doc_btn.pack(side="left", padx=3)

        # Add tooltips to all buttons
        tooltips = {
            self.start_stop_btn: "start_monitor",  # Will be updated dynamically
            self.edit_btn: "edit_monitor",
            self.remove_btn: "delete_monitor",
        }

        if hasattr(self, 'run_rules_btn'):
            tooltips[self.run_rules_btn] = "run_rules"
        if hasattr(self, 'ai_rename_btn'):
            tooltips[self.ai_rename_btn] = "smart_rename"
        if hasattr(self, 'ai_cat_btn'):
            tooltips[self.ai_cat_btn] = "categorize"
        if hasattr(self, 'ai_sec_btn'):
            tooltips[self.ai_sec_btn] = "security_scan"
        if hasattr(self, 'ai_doc_btn'):
            tooltips[self.ai_doc_btn] = "semantic_analysis"

        ToolTipHelper.add_tooltips_batch(tooltips)

        # Stats row
        stats_frame = ctk.CTkFrame(container, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(10, 5))

        self.stats_label = ctk.CTkLabel(
            stats_frame,
            text="Status: Stopped | Created: 0 | Modified: 0 | Deleted: 0 | Actions: 0",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.stats_label.pack(side="left")

        # Rules info
        rules_frame = ctk.CTkFrame(container, fg_color="transparent")
        rules_frame.pack(fill="x", pady=(5, 5))

        rules_count = len(self.rules)
        self.rules_label = ctk.CTkLabel(
            rules_frame,
            text=f"⚙️ {rules_count} automation rule{'s' if rules_count != 1 else ''} configured",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70")
        )
        self.rules_label.pack(side="left")

        # Recent activity section
        self.activity_frame = ctk.CTkFrame(
            container,
            fg_color=("gray75", "gray25"),
            corner_radius=5
        )
        self.activity_frame.pack(fill="x", pady=(10, 0))

        activity_title = ctk.CTkLabel(
            self.activity_frame,
            text="📊 Recent Activity",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        activity_title.pack(anchor="w", padx=10, pady=(5, 2))

        self.activity_text = ctk.CTkTextbox(
            self.activity_frame,
            height=60,
            font=ctk.CTkFont(size=10),
            fg_color="transparent"
        )
        self.activity_text.pack(fill="x", padx=10, pady=(0, 5))
        self.activity_text.configure(state="disabled")

        self._update_ui()

    def _toggle_monitoring(self):
        """Toggle monitoring on/off"""
        if self.monitor.is_running:
            self.stop_callback(self.monitor_id, self.is_ftp)
        else:
            self.start_callback(self.monitor_id, self.is_ftp)

        self._update_ui()

    def _edit(self):
        """Edit this monitor"""
        from gui.edit_monitor_dialog import EditMonitorDialog

        monitor_data = {
            "id": self.monitor_id,
            "path": self.path,
            "rules": self.rules,
            "type": "ftp" if self.is_ftp else "folder",
            "notify_created": getattr(self.monitor, 'notify_created', True),
            "notify_modified": getattr(self.monitor, 'notify_modified', True),
            "notify_deleted": getattr(self.monitor, 'notify_deleted', True),
            "notify_moved": getattr(self.monitor, 'notify_moved', True),
            "email_recipient": getattr(self.monitor, 'email_recipient', ""),
            # Advanced filters
            "min_size_kb": getattr(self.monitor, 'min_size_kb', None),
            "max_size_kb": getattr(self.monitor, 'max_size_kb', None),
            "modified_within_days": getattr(self.monitor, 'modified_within_days', None),
            "exclude_patterns": getattr(self.monitor, 'exclude_patterns', []),
            "filename_regex": getattr(self.monitor, 'filename_regex', None)
        }

        def on_save(updated_data):
            # Update rules
            self.rules = updated_data["rules"]
            self.monitor.rules = updated_data["rules"]

            # Update notification settings
            if hasattr(self.monitor, 'notify_created'):
                self.monitor.notify_created = updated_data.get("notify_created", True)
                self.monitor.notify_modified = updated_data.get("notify_modified", True)
                self.monitor.notify_deleted = updated_data.get("notify_deleted", True)
                self.monitor.notify_moved = updated_data.get("notify_moved", True)
                self.monitor.email_recipient = updated_data.get("email_recipient", "")

            # Update advanced filters
            if hasattr(self.monitor, 'min_size_kb'):
                self.monitor.min_size_kb = updated_data.get("min_size_kb")
                self.monitor.max_size_kb = updated_data.get("max_size_kb")
                self.monitor.modified_within_days = updated_data.get("modified_within_days")
                self.monitor.exclude_patterns = updated_data.get("exclude_patterns", [])
                self.monitor.filename_regex = updated_data.get("filename_regex")

            # Update rules label
            rules_count = len(self.rules)
            self.rules_label.configure(
                text=f"⚙ {rules_count} automation rule{'s' if rules_count != 1 else ''} configured"
            )
            if callable(self.save_callback):
                try:
                    self.save_callback()
                except Exception:
                    pass

        EditMonitorDialog(self.winfo_toplevel(), monitor_data, on_save)

    def _has_ai_rules(self) -> bool:
        """Check if monitor has AI-created rules (not manual rules)"""
        if not self.rules:
            return False

        # AI-created rules MUST have either:
        # 1. name_pattern field (AI uses this for filtering by filename)
        # 2. organize action with organize_by parameter
        # 3. handle_duplicates parameter (AI always sets this)

        # Manual rules typically just have event_types, file_extensions, action_type
        # without the AI-specific fields

        for rule in self.rules:
            # Check for AI-specific markers
            if "name_pattern" in rule and rule["name_pattern"]:
                return True

            if rule.get("action_type") == "organize" and "organize_by" in rule.get("action_params", {}):
                return True

            # AI always sets handle_duplicates for move/copy
            if rule.get("action_type") in ["move", "copy"]:
                if "handle_duplicates" in rule.get("action_params", {}):
                    return True

        return False

    def _remove(self):
        """Remove this monitor"""
        from tkinter import messagebox

        monitor_type = "FTP monitor" if self.is_ftp else "folder monitor"
        result = messagebox.askyesno(
            "Remove Monitor",
            f"Are you sure you want to remove this {monitor_type}?\n{self.path}"
        )

        if result:
            self.remove_callback(self.monitor_id, self.is_ftp)

    def _run_rules_now(self):
        """Run all rules on existing files in folder RIGHT NOW"""
        from tkinter import messagebox
        from pathlib import Path
        import threading

        if not self.rules:
            messagebox.showinfo("No Rules", "This monitor has no rules configured.")
            return

        folder_path = Path(self.path)
        if not folder_path.exists():
            messagebox.showerror("Error", "Folder does not exist")
            return

        # CRITICAL: Count files first and exclude destination folders
        destination_paths = set()
        for rule in self.rules:
            if rule.get("action_type") in ["move", "copy"]:
                dest = rule.get("action_params", {}).get("destination", "")
                if dest:
                    try:
                        dest_path = Path(dest).resolve()
                        destination_paths.add(dest_path)
                    except:
                        pass

        # Count files that will be processed
        file_count = 0
        for item in folder_path.rglob("*"):
            if item.is_file():
                # Skip files in destination folders
                skip = False
                try:
                    item_resolved = item.resolve()
                    for dest_path in destination_paths:
                        if dest_path in item_resolved.parents or item_resolved.parent == dest_path:
                            skip = True
                            break
                except:
                    pass

                if not skip:
                    file_count += 1

        # Show warning with file count
        rule_count = len(self.rules)

        # Build warning message
        warning_msg = (
            f"⚠️ WARNING: This will apply {rule_count} rule(s) to {file_count} existing files in:\n\n"
            f"{self.path}\n\n"
        )

        if file_count > 100:
            warning_msg += f"⚠️ LARGE OPERATION: {file_count} files will be processed!\n\n"

        warning_msg += (
            "The monitor will be temporarily stopped during this operation\n"
            "to prevent infinite loops from file events.\n\n"
            "⚠️ IMPORTANT SAFETY NOTE:\n"
            "• Files will be MOVED or COPIED (safe operations)\n"
            "• NO files will be renamed, deleted, or modified\n"
            "• Original file contents are never changed\n\n"
            "Do you want to see a preview first?"
        )

        # Ask if user wants preview
        response = messagebox.askyesnocancel(
            "Run Rules Now?",
            warning_msg + "\n\nYes = Show Preview\nNo = Run Now\nCancel = Go Back"
        )

        if response is None:  # Cancel
            return
        elif response is True:  # Show preview
            self._show_preview(folder_path)
        else:  # Run now
            from gui.run_rules_dialog import RunRulesDialog
            RunRulesDialog(self.winfo_toplevel(), self.monitor, folder_path, self.rules)

    def _show_preview(self, folder_path: Path):
        """Show preview of what will happen before running rules"""
        from tkinter import messagebox

        # Collect files that will match
        matching_files = []

        # Get destination paths to exclude
        destination_paths = set()
        for rule in self.rules:
            if rule.get("action_type") in ["move", "copy"]:
                dest = rule.get("action_params", {}).get("destination", "")
                if dest:
                    try:
                        destination_paths.add(Path(dest).resolve())
                    except:
                        pass

        # Find matching files
        for item in folder_path.rglob("*"):
            if item.is_file():
                # Skip files in destination
                skip = False
                try:
                    item_resolved = item.resolve()
                    for dest_path in destination_paths:
                        if dest_path in item_resolved.parents or item_resolved.parent == dest_path:
                            skip = True
                            break
                except:
                    pass

                if skip:
                    continue

                # Check if any rule matches
                for rule in self.rules:
                    # Check extensions
                    extensions = rule.get("file_extensions", ["*"])
                    if "*" not in extensions and item.suffix.lower() not in [e.lower() for e in extensions]:
                        continue

                    # Check name pattern
                    name_pattern = rule.get("name_pattern")
                    if name_pattern:
                        import re
                        try:
                            if not re.search(name_pattern, item.name, re.IGNORECASE):
                                continue
                        except:
                            continue

                    # Match found
                    action = rule.get("action_type", "").upper()
                    dest = rule.get("action_params", {}).get("destination", "N/A")
                    matching_files.append(f"• {item.name}\n  → {action} to: {dest}")
                    break

        # Show preview
        if not matching_files:
            messagebox.showinfo("Preview", "No files match the current rules.")
            return

        preview_msg = f"PREVIEW: {len(matching_files)} files will be affected:\n\n"
        preview_msg += "\n".join(matching_files[:20])  # Show first 20

        if len(matching_files) > 20:
            preview_msg += f"\n\n...and {len(matching_files) - 20} more files"

        preview_msg += "\n\n⚠️ Files will be MOVED or COPIED (no deletion/modification)\n\nProceed?"

        if messagebox.askyesno("Preview - Run Rules?", preview_msg):
            from gui.run_rules_dialog import RunRulesDialog
            RunRulesDialog(self.winfo_toplevel(), self.monitor, folder_path, self.rules)

    def _smart_rename(self):
        """Open AI Smart Rename Assistant for this folder with bulk options"""
        from gui.smart_rename_dialog import SmartRenameDialog
        from pathlib import Path

        # Get AI manager from parent window
        main_window = self.winfo_toplevel()
        if not hasattr(main_window, 'ai_manager'):
            from tkinter import messagebox
            messagebox.showwarning(
                "AI Not Available",
                "AI features are not initialized. Please check Settings."
            )
            return

        ai_manager = main_window.ai_manager

        # Check if AI is ready
        if not ai_manager.is_ready:
            # Check if model files exist
            if ai_manager.model_files_exist():
                # Model exists, just needs to be loaded into memory
                from gui.ai_loading_dialog import AILoadingDialog
                loading_dialog = AILoadingDialog(self.winfo_toplevel(), ai_manager)
                self.winfo_toplevel().wait_window(loading_dialog)

                if not ai_manager.is_ready:
                    return
            else:
                # Model doesn't exist, needs download
                from tkinter import messagebox
                result = messagebox.askyesno(
                    "AI Model Download Required",
                    "AI model needs to be downloaded first (2.4GB).\nThis is a one-time download and may take a few minutes.\n\nContinue?"
                )
                if result:
                    self._show_ai_loading(ai_manager)
                return

        # Get folder path
        folder_path = Path(self.path)
        if not folder_path.exists():
            from tkinter import messagebox
            messagebox.showerror("Error", "Monitored folder does not exist")
            return

        def on_complete(renamed_count):
            from tkinter import messagebox
            messagebox.showinfo(
                "Smart Rename Complete",
                f"Successfully renamed {renamed_count} files!"
            )

        # Open Smart Rename dialog in folder mode
        # The dialog will handle scanning with options (subfolders, filters, etc.)
        SmartRenameDialog(
            self.winfo_toplevel(),
            ai_manager,
            [],  # Empty files list - dialog will scan based on options
            on_complete,
            folder_mode=True,
            folder_path=folder_path
        )

    def _show_ai_loading(self, ai_manager):
        """Show AI model loading progress dialog"""
        loading_dialog = ctk.CTkToplevel(self.winfo_toplevel())
        loading_dialog.title("Loading AI Model")
        loading_dialog.geometry("450x280")
        loading_dialog.resizable(False, False)

        # Center
        loading_dialog.update_idletasks()
        x = (loading_dialog.winfo_screenwidth() // 2) - 225
        y = (loading_dialog.winfo_screenheight() // 2) - 140
        loading_dialog.geometry(f"450x280+{x}+{y}")

        ctk.CTkLabel(
            loading_dialog,
            text="Loading AI Model",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        ).pack(pady=20)

        status_label = ctk.CTkLabel(
            loading_dialog,
            text="Initializing...",
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        status_label.pack(pady=10)

        progress = ctk.CTkProgressBar(loading_dialog, width=410)
        progress.pack(pady=10)
        progress.set(0)

        # Download stats
        downloaded_label = ctk.CTkLabel(
            loading_dialog,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        downloaded_label.pack(pady=5)

        speed_label = ctk.CTkLabel(
            loading_dialog,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        speed_label.pack(pady=5)

        info_label = ctk.CTkLabel(
            loading_dialog,
            text="First run: ~2.5GB download required",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        info_label.pack(pady=10)

        dialog_destroyed = [False]  # Use list to allow modification in nested function

        def update_progress(message, value, downloaded_str, speed_str):
            if dialog_destroyed[0]:
                return

            try:
                if not loading_dialog.winfo_exists():
                    dialog_destroyed[0] = True
                    return

                status_label.configure(text=message)
                progress.set(value)

                if downloaded_str:
                    downloaded_label.configure(text=downloaded_str)

                if speed_str:
                    speed_label.configure(text=speed_str)

                if value >= 1.0:
                    dialog_destroyed[0] = True
                    loading_dialog.after(500, loading_dialog.destroy)  # Delay destroy
            except Exception:
                dialog_destroyed[0] = True

        # Handle manual close
        def on_close():
            dialog_destroyed[0] = True
            loading_dialog.destroy()

        loading_dialog.protocol("WM_DELETE_WINDOW", on_close)

        # Start loading in background
        ai_manager.load_model_async(update_progress)

    def _ai_categorize(self):
        """Open AI Auto-Categorize dialog (non-blocking)"""
        from pathlib import Path

        # Get AI manager
        main_window = self.winfo_toplevel()
        if not hasattr(main_window, 'ai_manager'):
            from tkinter import messagebox
            messagebox.showwarning("AI Not Available", "AI features are not initialized")
            return

        ai_manager = main_window.ai_manager

        # Check folder exists first (fast check)
        folder_path = Path(self.path)
        if not folder_path.exists():
            from tkinter import messagebox
            messagebox.showerror("Error", "Monitored folder does not exist")
            return

        # Check if AI ready
        if not ai_manager.is_ready:
            if ai_manager.model_files_exist():
                from gui.ai_loading_dialog import AILoadingDialog
                loading_dialog = AILoadingDialog(self.winfo_toplevel(), ai_manager)
                self.winfo_toplevel().wait_window(loading_dialog)
                if not ai_manager.is_ready:
                    return
            else:
                from tkinter import messagebox
                result = messagebox.askyesno(
                    "AI Model Download Required",
                    "AI model needs to be downloaded first (2.4GB).\nThis is a one-time download and may take a few minutes.\n\nContinue?"
                )
                if result:
                    self._show_ai_loading(ai_manager)
                return

        # Schedule dialog creation to avoid blocking the UI
        self.after(10, lambda: self._open_categorize_dialog(ai_manager, folder_path))

    def _open_categorize_dialog(self, ai_manager, folder_path):
        """Actually open the dialog (called after UI update)"""
        from gui.ai_categorize_dialog import AICategorizeDialog
        from core.ai_categorizer import AICategorizer

        # Create categorizer
        categorizer = AICategorizer(ai_manager)

        # Open dialog (handles threading internally)
        AICategorizeDialog(self.winfo_toplevel(), ai_manager, categorizer, folder_path)

    def _ai_security_scan(self):
        """Open AI Security Scanner dialog"""
        from gui.ai_security_scan_dialog import AISecurityScanDialog
        from core.ai_categorizer import AICategorizer
        from pathlib import Path

        # Get AI manager
        main_window = self.winfo_toplevel()
        if not hasattr(main_window, 'ai_manager'):
            from tkinter import messagebox
            messagebox.showwarning("AI Not Available", "AI features are not initialized")
            return

        ai_manager = main_window.ai_manager

        # Check if ready
        if not ai_manager.is_ready:
            if ai_manager.model_files_exist():
                from gui.ai_loading_dialog import AILoadingDialog
                loading_dialog = AILoadingDialog(self.winfo_toplevel(), ai_manager)
                self.winfo_toplevel().wait_window(loading_dialog)
                if not ai_manager.is_ready:
                    return
            else:
                from tkinter import messagebox
                result = messagebox.askyesno(
                    "AI Model Download Required",
                    "AI model needs to be downloaded first (2.4GB).\nThis is a one-time download and may take a few minutes.\n\nContinue?"
                )
                if result:
                    self._show_ai_loading(ai_manager)
                return

        # Check folder exists
        folder_path = Path(self.path)
        if not folder_path.exists():
            from tkinter import messagebox
            messagebox.showerror("Error", "Monitored folder does not exist")
            return

        # Create categorizer (for scanning)
        categorizer = AICategorizer(ai_manager)

        # Open scanner dialog
        AISecurityScanDialog(self.winfo_toplevel(), ai_manager, categorizer, folder_path)

    def _analyze_document(self):
        """Open Semantic Document Analyzer - analyze single file or bulk folder"""
        from gui.semantic_analysis_dialog import SemanticAnalysisDialog
        from core.semantic_analyzer import SemanticAnalyzer
        from pathlib import Path
        from tkinter import filedialog, messagebox
        import customtkinter as ctk

        # Get AI manager
        main_window = self.winfo_toplevel()
        if not hasattr(main_window, 'ai_manager'):
            messagebox.showwarning("AI Not Available", "AI features are not initialized")
            return

        ai_manager = main_window.ai_manager

        # Check if ready
        if not ai_manager.is_ready:
            if ai_manager.model_files_exist():
                from gui.ai_loading_dialog import AILoadingDialog
                loading_dialog = AILoadingDialog(self.winfo_toplevel(), ai_manager)
                self.winfo_toplevel().wait_window(loading_dialog)
                if not ai_manager.is_ready:
                    return
            else:
                result = messagebox.askyesno(
                    "AI Model Download Required",
                    "AI model needs to be downloaded first (2.4GB).\nThis is a one-time download and may take a few minutes.\n\nContinue?"
                )
                if result:
                    self._show_ai_loading(ai_manager)
                return

        # Show professional mode selector
        self._show_semantic_mode_selector(ai_manager)

    def _show_semantic_mode_selector(self, ai_manager):
        """Show professional semantic analysis mode selector"""
        import customtkinter as ctk

        mode_dialog = ctk.CTkToplevel(self.winfo_toplevel())
        mode_dialog.title("Semantic Analysis")
        mode_dialog.geometry("480x300")
        mode_dialog.resizable(False, False)
        mode_dialog.grab_set()

        # Center
        mode_dialog.update_idletasks()
        x = (mode_dialog.winfo_screenwidth() // 2) - 240
        y = (mode_dialog.winfo_screenheight() // 2) - 150
        mode_dialog.geometry(f"480x300+{x}+{y}")

        # Header
        ctk.CTkLabel(
            mode_dialog,
            text="📄 Semantic Document Analysis",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        ).pack(pady=(25, 5))

        ctk.CTkLabel(
            mode_dialog,
            text="Choose analysis mode",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray"
        ).pack(pady=(0, 25))

        # Mode buttons
        button_container = ctk.CTkFrame(mode_dialog, fg_color="transparent")
        button_container.pack(expand=True, pady=20)

        def single_mode():
            mode_dialog.destroy()
            self._launch_single_analysis(ai_manager)

        def bulk_mode():
            mode_dialog.destroy()
            self._launch_bulk_analysis(ai_manager)

        # Single File button
        single_btn = ctk.CTkButton(
            button_container,
            text="📄 Single File\nAnalyze one document",
            width=180,
            height=80,
            command=single_mode,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="#4CAF50",
            hover_color="#388E3C"
        )
        single_btn.pack(side="left", padx=15)

        # Bulk Folder button
        bulk_btn = ctk.CTkButton(
            button_container,
            text="📁 Bulk Folder\nAnalyze all documents (recursive)",
            width=180,
            height=80,
            command=bulk_mode,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="#9C27B0",
            hover_color="#7B1FA2"
        )
        bulk_btn.pack(side="left", padx=15)

        # Cancel
        ctk.CTkButton(
            mode_dialog,
            text="Cancel",
            width=100,
            command=mode_dialog.destroy,
            fg_color="gray",
            hover_color="#505050"
        ).pack(pady=(0, 20))

    def _launch_single_analysis(self, ai_manager):
        """Launch single file semantic analysis"""
        from gui.semantic_analysis_dialog import SemanticAnalysisDialog
        from core.semantic_analyzer import SemanticAnalyzer
        from pathlib import Path
        from tkinter import filedialog

        file_path = filedialog.askopenfilename(
            title="Select Document for AI Analysis",
            initialdir=str(Path(self.path)),
            filetypes=[
                ("All Documents", "*.pdf;*.docx;*.doc;*.txt;*.xlsx;*.pptx"),
                ("PDF Files", "*.pdf"),
                ("Word Documents", "*.docx;*.doc"),
                ("All Files", "*.*")
            ]
        )

        if not file_path:
            return

        main_window = self.winfo_toplevel()
        if not hasattr(main_window, 'semantic_analyzer'):
            main_window.semantic_analyzer = SemanticAnalyzer(ai_manager)

        SemanticAnalysisDialog(
            self.winfo_toplevel(),
            main_window.semantic_analyzer,
            Path(file_path),
            folder_mode=False
        )

    def _launch_bulk_analysis(self, ai_manager):
        """Launch bulk folder semantic analysis"""
        from gui.semantic_analysis_dialog import SemanticAnalysisDialog
        from core.semantic_analyzer import SemanticAnalyzer
        from pathlib import Path
        from tkinter import filedialog

        folder_path = filedialog.askdirectory(
            title="Select Folder for Bulk Analysis (Recursive)",
            initialdir=str(Path(self.path))
        )

        if not folder_path:
            return

        main_window = self.winfo_toplevel()
        if not hasattr(main_window, 'semantic_analyzer'):
            main_window.semantic_analyzer = SemanticAnalyzer(ai_manager)

        SemanticAnalysisDialog(
            self.winfo_toplevel(),
            main_window.semantic_analyzer,
            Path(folder_path),
            folder_mode=True
        )

    def _update_ui(self):
        """Update UI based on monitor state"""
        if self.monitor.is_running:
            self.start_stop_btn.configure(
                text="",
                image=self.pause_icon,
                fg_color="#d32f2f",
                hover_color="#9a0007"
            )
        else:
            self.start_stop_btn.configure(
                text="",
                image=self.play_icon,
                fg_color="#2fa572",
                hover_color="#106a43"
            )

        # Update stats
        stats = self.monitor.stats
        status = "Running" if self.monitor.is_running else "Stopped"
        status_color = "#2fa572" if self.monitor.is_running else "#d32f2f"

        self.stats_label.configure(
            text=f"Status: {status} | Created: {stats['files_created']} | "
                 f"Modified: {stats['files_modified']} | Deleted: {stats['files_deleted']} | "
                 f"Actions: {stats['actions_executed']}"
        )

    def add_event(self, event_type: str, file_path: str):
        """Add a new event to recent activity"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        file_name = Path(file_path).name

        event_text = f"[{timestamp}] {event_type.upper()}: {file_name}\n"

        self.recent_events.append(event_text)

        # Keep only recent events
        if len(self.recent_events) > self.max_events:
            self.recent_events.pop(0)

        # Update activity display
        self.activity_text.configure(state="normal")
        self.activity_text.delete("1.0", "end")
        self.activity_text.insert("1.0", "".join(self.recent_events))
        self.activity_text.configure(state="disabled")

        # Update stats
        self._update_ui()
