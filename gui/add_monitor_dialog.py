"""Add Monitor Dialog - Dialog for adding new folder monitors"""

import customtkinter as ctk
import re
from tkinter import filedialog
from typing import Callable, Dict, List
from pathlib import Path
from utils.png_icons import PNGIconLoader


class AddMonitorDialog(ctk.CTkToplevel):
    """Dialog for adding new monitor"""

    def __init__(self, parent, callback: Callable):
        super().__init__(parent)

        self.callback = callback
        self.rules = []
        self.icon_loader = PNGIconLoader()

        # Configure window
        self.title("Add New Monitor")
        self.geometry("700x750")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.winfo_screenheight() // 2) - (750 // 2)
        self.geometry(f"700x750+{x}+{y}")

    def _setup_ui(self):
        """Setup dialog UI"""
        # Main container
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title (fixed at top)
        title_frame = ctk.CTkFrame(main_container, fg_color="transparent", height=40)
        title_frame.pack(pady=(0, 15), fill="x")
        title_frame.pack_propagate(False)

        # Load folder icon
        folder_icon = self.icon_loader.load_icon("folder", size=(28, 28))

        # Icon positioned absolutely
        if folder_icon:
            icon_label = ctk.CTkLabel(
                title_frame,
                text="",
                image=folder_icon
            )
            icon_label.place(x=220, y=6)

        # Title text
        title = ctk.CTkLabel(
            title_frame,
            text="Add Folder Monitor",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.place(x=255, y=8)

        # Scrollable content area (hide scrollbar)
        scrollable_container = ctk.CTkScrollableFrame(
            main_container,
            fg_color="transparent"
        )
        scrollable_container.pack(fill="both", expand=True, pady=(0, 15))

        # Hide the scrollbar
        scrollable_container._scrollbar.grid_forget()

        # Use scrollable_container instead of container for all content
        container = scrollable_container

        # Folder selection
        folder_frame = ctk.CTkFrame(container, fg_color="transparent")
        folder_frame.pack(fill="x", pady=10)

        folder_label = ctk.CTkLabel(
            folder_frame,
            text="Folder to Monitor:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        folder_label.pack(anchor="w")

        path_frame = ctk.CTkFrame(folder_frame, fg_color="transparent")
        path_frame.pack(fill="x", pady=(5, 0))

        self.path_entry = ctk.CTkEntry(
            path_frame,
            placeholder_text="Select a folder to monitor...",
            height=35
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=100,
            command=self._browse_folder
        )
        browse_btn.pack(side="right")

        # Options
        options_frame = ctk.CTkFrame(container, fg_color="transparent")
        options_frame.pack(fill="x", pady=10)

        options_label = ctk.CTkLabel(
            options_frame,
            text="Options:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        options_label.pack(anchor="w")

        self.auto_start_var = ctk.BooleanVar(value=True)
        auto_start_cb = ctk.CTkCheckBox(
            options_frame,
            text="Start monitoring immediately",
            variable=self.auto_start_var
        )
        auto_start_cb.pack(anchor="w", pady=5)

        # Notification filters
        notif_frame = ctk.CTkFrame(container, fg_color="transparent")
        notif_frame.pack(fill="x", pady=10)

        notif_label = ctk.CTkLabel(
            notif_frame,
            text="Windows Notifications:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        notif_label.pack(anchor="w")

        notif_info = ctk.CTkLabel(
            notif_frame,
            text="Select which events should trigger Windows notifications:",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        notif_info.pack(anchor="w", pady=(2, 5))

        self.notify_created_var = ctk.BooleanVar(value=True)
        self.notify_modified_var = ctk.BooleanVar(value=True)
        self.notify_deleted_var = ctk.BooleanVar(value=True)
        self.notify_moved_var = ctk.BooleanVar(value=True)

        notif_checkboxes = ctk.CTkFrame(notif_frame, fg_color="transparent")
        notif_checkboxes.pack(fill="x", pady=5)

        notif_grid = ctk.CTkFrame(notif_checkboxes, fg_color="transparent")
        notif_grid.pack(anchor="w")

        ctk.CTkCheckBox(notif_grid, text="Created", variable=self.notify_created_var).grid(row=0, column=0, padx=10, sticky="w")
        ctk.CTkCheckBox(notif_grid, text="Modified", variable=self.notify_modified_var).grid(row=0, column=1, padx=10, sticky="w")
        ctk.CTkCheckBox(notif_grid, text="Deleted", variable=self.notify_deleted_var).grid(row=0, column=2, padx=10, sticky="w")
        ctk.CTkCheckBox(notif_grid, text="Moved", variable=self.notify_moved_var).grid(row=0, column=3, padx=10, sticky="w")

        # Email notification
        email_frame = ctk.CTkFrame(container, fg_color="transparent")
        email_frame.pack(fill="x", pady=10)

        email_label = ctk.CTkLabel(
            email_frame,
            text="Email Notifications (Optional):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        email_label.pack(anchor="w")

        email_info = ctk.CTkLabel(
            email_frame,
            text="Receive email alerts for events (configure SMTP in Settings first):",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        email_info.pack(anchor="w", pady=(2, 5))

        self.email_entry = ctk.CTkEntry(
            email_frame,
            placeholder_text="recipient@example.com (leave empty to disable)",
            height=35
        )
        self.email_entry.pack(fill="x", pady=5)

        # Advanced Filters section
        filters_frame = ctk.CTkFrame(container, fg_color="transparent")
        filters_frame.pack(fill="x", pady=10)

        filters_label = ctk.CTkLabel(
            filters_frame,
            text="Advanced Filters (Optional):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        filters_label.pack(anchor="w")

        filters_info = ctk.CTkLabel(
            filters_frame,
            text=(
                "Filters run before notifications and rules. Leave fields empty or 0 to disable them.\n"
                "Use Exclude for folders/files to ignore. Use Regex only for advanced filename matching."
            ),
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        filters_info.pack(anchor="w", pady=(2, 5))

        # File size filters
        size_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        size_frame.pack(fill="x", pady=5)

        size_label = ctk.CTkLabel(
            size_frame,
            text="File Size:",
            font=ctk.CTkFont(size=11)
        )
        size_label.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(size_frame, text="Min (KB):").pack(side="left", padx=5)
        self.min_size_entry = ctk.CTkEntry(size_frame, width=80, placeholder_text="0")
        self.min_size_entry.insert(0, "0")
        self.min_size_entry.pack(side="left", padx=5)

        ctk.CTkLabel(size_frame, text="Max (KB):").pack(side="left", padx=5)
        self.max_size_entry = ctk.CTkEntry(size_frame, width=80, placeholder_text="∞")
        self.max_size_entry.insert(0, "0")
        self.max_size_entry.pack(side="left", padx=5)
        ctk.CTkLabel(size_frame, text="0 = disabled").pack(side="left", padx=5)

        # Date filter
        date_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        date_frame.pack(fill="x", pady=5)

        date_label = ctk.CTkLabel(
            date_frame,
            text="Modified Within:",
            font=ctk.CTkFont(size=11)
        )
        date_label.pack(side="left", padx=(0, 10))

        self.date_filter_entry = ctk.CTkEntry(date_frame, width=80, placeholder_text="0")
        self.date_filter_entry.insert(0, "0")
        self.date_filter_entry.pack(side="left", padx=5)

        ctk.CTkLabel(date_frame, text="days (0 = disabled)").pack(side="left", padx=5)

        # Exclude patterns
        exclude_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        exclude_frame.pack(fill="x", pady=5)

        exclude_label = ctk.CTkLabel(
            exclude_frame,
            text="Exclude Patterns (.gitignore syntax, one per line):",
            font=ctk.CTkFont(size=11)
        )
        exclude_label.pack(anchor="w", pady=(0, 5))
        exclude_hint = ctk.CTkLabel(
            exclude_frame,
            text="Examples: *.tmp ignores temp files, node_modules/ ignores that folder, */cache/* ignores cache paths.",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        exclude_hint.pack(anchor="w", pady=(0, 5))

        self.exclude_patterns_text = ctk.CTkTextbox(
            exclude_frame,
            height=60,
            fg_color=("gray85", "gray20")
        )
        self.exclude_patterns_text.pack(fill="x")
        self.exclude_patterns_text.insert("1.0", "# Examples:\n# *.tmp\n# node_modules/\n# .git/\n# */cache/*")

        # Regex pattern
        regex_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        regex_frame.pack(fill="x", pady=5)

        regex_label = ctk.CTkLabel(
            regex_frame,
            text="Filename Regex (only match files matching this pattern):",
            font=ctk.CTkFont(size=11)
        )
        regex_label.pack(anchor="w", pady=(0, 5))

        self.regex_entry = ctk.CTkEntry(
            regex_frame,
            placeholder_text=r"Advanced: ^invoice_.*\.pdf$ or ^client_[0-9]+\.docx$"
        )
        self.regex_entry.pack(fill="x")
        regex_hint = ctk.CTkLabel(
            regex_frame,
            text="Regex matches only the filename, not the folder path. Most users should leave this blank.",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        regex_hint.pack(anchor="w", pady=(4, 0))

        # Quick rules section
        rules_frame = ctk.CTkFrame(container, fg_color="transparent")
        rules_frame.pack(fill="both", expand=True, pady=10)

        rules_header = ctk.CTkFrame(rules_frame, fg_color="transparent")
        rules_header.pack(fill="x")

        rules_label = ctk.CTkLabel(
            rules_header,
            text="Quick Automation Rules:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        rules_label.pack(side="left")

        add_rule_btn = ctk.CTkButton(
            rules_header,
            text="+ Add Rule",
            width=100,
            command=self._add_rule
        )
        add_rule_btn.pack(side="right")

        # Rules list
        self.rules_scrollable = ctk.CTkScrollableFrame(
            rules_frame,
            height=150,
            fg_color=("gray85", "gray20")
        )
        self.rules_scrollable.pack(fill="x", pady=(10, 0))

        # Initial rule templates
        self._show_rule_templates()

        # Buttons (fixed at bottom, outside scrollable area)
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(0, 0))

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=120,
            command=self.destroy,
            fg_color="transparent",
            border_width=2
        )
        cancel_btn.pack(side="right", padx=5)

        add_btn = ctk.CTkButton(
            button_frame,
            text="Add Monitor",
            width=120,
            command=self._add_monitor,
            fg_color="#2fa572",
            hover_color="#106a43"
        )
        add_btn.pack(side="right", padx=5)

    def _browse_folder(self):
        """Browse for folder"""
        folder = filedialog.askdirectory(title="Select Folder to Monitor")
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def _show_rule_templates(self):
        """Show rule templates"""
        info_label = ctk.CTkLabel(
            self.rules_scrollable,
            text="Click '+ Add Rule' to create automation rules\n"
                 "You can add rules later from the settings",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.pack(pady=30)

    def _add_rule(self):
        """Add a new rule"""
        RuleDialog(self, self._on_rule_added)

    def _on_rule_added(self, rule: Dict):
        """Callback when rule is added"""
        self.rules.append(rule)

        # Clear templates if first rule
        if len(self.rules) == 1:
            for widget in self.rules_scrollable.winfo_children():
                widget.destroy()

        # Add rule card
        self._create_rule_card(rule)

    def _create_rule_card(self, rule: Dict):
        """Create a rule display card"""
        card = ctk.CTkFrame(self.rules_scrollable, fg_color=("gray75", "gray25"))
        card.pack(fill="x", padx=5, pady=5)

        content_frame = ctk.CTkFrame(card, fg_color="transparent")
        content_frame.pack(fill="x", padx=10, pady=8)

        # Rule description
        desc = f"When: {', '.join(rule.get('event_types', ['any']))} | "
        desc += f"Action: {rule['action_type']}"

        if rule.get('file_extensions'):
            desc += f" | Files: {', '.join(rule['file_extensions'])}"

        label = ctk.CTkLabel(
            content_frame,
            text=desc,
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        label.pack(side="left", fill="x", expand=True)

        remove_btn = ctk.CTkButton(
            content_frame,
            text="✕",
            width=30,
            command=lambda: self._remove_rule(rule, card),
            fg_color="#d32f2f"
        )
        remove_btn.pack(side="right")

    def _remove_rule(self, rule: Dict, card: ctk.CTkFrame):
        """Remove a rule"""
        self.rules.remove(rule)
        card.destroy()

        # Show templates if no rules
        if len(self.rules) == 0:
            self._show_rule_templates()

    def _add_monitor(self):
        """Add the monitor"""
        path = self.path_entry.get().strip()

        if not path:
            from tkinter import messagebox
            messagebox.showerror("Error", "Please select a folder to monitor")
            return

        if not Path(path).exists():
            from tkinter import messagebox
            messagebox.showerror("Error", "Selected folder does not exist")
            return
        if not Path(path).is_dir():
            from tkinter import messagebox
            messagebox.showerror("Error", "Selected path must be a folder")
            return

        # Parse filter values
        min_size = self.min_size_entry.get().strip()
        max_size = self.max_size_entry.get().strip()
        date_days = self.date_filter_entry.get().strip()

        def parse_optional_int(value: str, label: str):
            if not value or value == "0":
                return None
            try:
                number = int(value)
            except ValueError:
                raise ValueError(f"{label} must be a whole number.")
            if number < 0:
                raise ValueError(f"{label} cannot be negative.")
            return number

        try:
            min_size_value = parse_optional_int(min_size, "Minimum size")
            max_size_value = parse_optional_int(max_size, "Maximum size")
            date_days_value = parse_optional_int(date_days, "Modified within days")
            if min_size_value is not None and max_size_value is not None and min_size_value > max_size_value:
                raise ValueError("Minimum size cannot be larger than maximum size.")
        except ValueError as e:
            from tkinter import messagebox
            messagebox.showerror("Invalid Filters", str(e))
            return

        regex_value = self.regex_entry.get().strip() or None
        if regex_value:
            try:
                re.compile(regex_value)
            except re.error as e:
                from tkinter import messagebox
                messagebox.showerror("Invalid Filename Regex", f"Filename regex is invalid:\n{e}")
                return

        # Get exclude patterns (filter out comments and empty lines)
        exclude_text = self.exclude_patterns_text.get("1.0", "end").strip()
        exclude_patterns = [
            part.strip()
            for part in exclude_text.replace("\r", "\n").replace(",", "\n").split("\n")
            if part.strip() and not part.strip().startswith('#')
        ]
        if any(p in {"*", "*.*"} for p in exclude_patterns):
            from tkinter import messagebox
            messagebox.showerror("Invalid Filters", "Exclude pattern '*' would ignore every file.")
            return

        monitor_data = {
            "path": path,
            "rules": self.rules,
            "auto_start": self.auto_start_var.get(),
            "notify_created": self.notify_created_var.get(),
            "notify_modified": self.notify_modified_var.get(),
            "notify_deleted": self.notify_deleted_var.get(),
            "notify_moved": self.notify_moved_var.get(),
            "email_recipient": self.email_entry.get().strip(),
            # Advanced filters
            "min_size_kb": min_size_value,
            "max_size_kb": max_size_value,
            "modified_within_days": date_days_value,
            "exclude_patterns": exclude_patterns,
            "filename_regex": regex_value
        }

        self.callback(monitor_data)
        self.destroy()


class RuleDialog(ctk.CTkToplevel):
    """Dialog for creating automation rules"""

    def __init__(self, parent, callback: Callable):
        super().__init__(parent)

        self.callback = callback

        # Configure window
        self.title("Add Automation Rule")
        self.geometry("600x500")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (500 // 2)
        self.geometry(f"600x500+{x}+{y}")

    def _setup_ui(self):
        """Setup dialog UI"""
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title = ctk.CTkLabel(
            container,
            text="⚙️ Create Automation Rule",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(pady=(0, 20))

        # Event types
        event_frame = ctk.CTkFrame(container, fg_color="transparent")
        event_frame.pack(fill="x", pady=10)

        event_label = ctk.CTkLabel(
            event_frame,
            text="Trigger Events:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        event_label.pack(anchor="w")

        self.event_vars = {
            "created": ctk.BooleanVar(value=True),
            "modified": ctk.BooleanVar(value=False),
            "deleted": ctk.BooleanVar(value=False),
            "moved": ctk.BooleanVar(value=False)
        }

        events_grid = ctk.CTkFrame(event_frame, fg_color="transparent")
        events_grid.pack(fill="x", pady=5)

        for i, (event, var) in enumerate(self.event_vars.items()):
            cb = ctk.CTkCheckBox(events_grid, text=event.title(), variable=var)
            cb.grid(row=0, column=i, padx=10, sticky="w")

        # File filter
        filter_frame = ctk.CTkFrame(container, fg_color="transparent")
        filter_frame.pack(fill="x", pady=10)

        filter_label = ctk.CTkLabel(
            filter_frame,
            text="Rule File Extensions (optional):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        filter_label.pack(anchor="w")
        filter_hint = ctk.CTkLabel(
            filter_frame,
            text="This rule only runs for these extensions. Leave blank for all files. Use pdf or .pdf.",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        filter_hint.pack(anchor="w", pady=(2, 5))

        self.ext_entry = ctk.CTkEntry(
            filter_frame,
            placeholder_text="e.g., .pdf, .docx, .jpg (comma-separated)"
        )
        self.ext_entry.pack(fill="x", pady=5)

        # Action type
        action_frame = ctk.CTkFrame(container, fg_color="transparent")
        action_frame.pack(fill="x", pady=10)

        action_label = ctk.CTkLabel(
            action_frame,
            text="Action:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        action_label.pack(anchor="w")

        self.action_var = ctk.StringVar(value="copy")
        action_menu = ctk.CTkOptionMenu(
            action_frame,
            variable=self.action_var,
            values=["copy", "move", "rename", "archive", "organize", "execute"],
            command=self._on_action_changed
        )
        action_menu.pack(fill="x", pady=5)

        # Action parameters
        self.params_frame = ctk.CTkFrame(container, fg_color="transparent")
        self.params_frame.pack(fill="x", pady=10)

        self._update_params_ui()

        # Buttons
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            command=self.destroy,
            fg_color="transparent",
            border_width=2
        )
        cancel_btn.pack(side="right", padx=5)

        add_btn = ctk.CTkButton(
            button_frame,
            text="Add Rule",
            width=100,
            command=self._add_rule,
            fg_color="#2fa572"
        )
        add_btn.pack(side="right", padx=5)

    def _on_action_changed(self, value):
        """Handle action type change"""
        self._update_params_ui()

    def _update_params_ui(self):
        """Update parameters UI based on action type"""
        # Clear existing params
        for widget in self.params_frame.winfo_children():
            widget.destroy()

        action = self.action_var.get()

        if action in ["copy", "move"]:
            label = ctk.CTkLabel(
                self.params_frame,
                text="Destination Folder:",
                font=ctk.CTkFont(size=12)
            )
            label.pack(anchor="w")

            path_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
            path_frame.pack(fill="x", pady=5)

            self.dest_entry = ctk.CTkEntry(path_frame)
            self.dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

            browse_btn = ctk.CTkButton(
                path_frame,
                text="Browse",
                width=80,
                command=self._browse_dest
            )
            browse_btn.pack(side="right")

        elif action == "organize":
            label = ctk.CTkLabel(
                self.params_frame,
                text="Organize By:",
                font=ctk.CTkFont(size=12)
            )
            label.pack(anchor="w")

            self.organize_var = ctk.StringVar(value="extension")
            menu = ctk.CTkOptionMenu(
                self.params_frame,
                variable=self.organize_var,
                values=["extension", "date", "type"]
            )
            menu.pack(fill="x", pady=5)

    def _browse_dest(self):
        """Browse for destination folder"""
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, folder)

    def _add_rule(self):
        """Add the rule"""
        # Get selected events
        events = [event for event, var in self.event_vars.items() if var.get()]

        if not events:
            from tkinter import messagebox
            messagebox.showerror("Error", "Please select at least one trigger event")
            return

        # Get file extensions
        extensions = []
        ext_text = self.ext_entry.get().strip()
        if ext_text:
            for ext in [ext.strip() for ext in ext_text.split(',') if ext.strip()]:
                cleaned = ext.lower().lstrip(".")
                if cleaned != "*" and any(ch in cleaned for ch in "/\\:*?\"<>|\r\n"):
                    from tkinter import messagebox
                    messagebox.showerror("Invalid Extension", f"Extension filter is invalid: {ext}")
                    return
                extensions.append("*" if cleaned == "*" else f".{cleaned}")

        # Get action parameters
        action = self.action_var.get()
        params = {}

        if action in ["copy", "move"]:
            dest = getattr(self, 'dest_entry', None)
            if dest:
                dest_path = dest.get().strip()
                if not dest_path:
                    from tkinter import messagebox
                    messagebox.showerror("Error", "Please specify destination folder")
                    return
                params["destination"] = dest_path

        elif action == "organize":
            params["organize_by"] = self.organize_var.get()

        # Create rule
        rule = {
            "event_types": events,
            "file_extensions": extensions,
            "action_type": action,
            "action_params": params
        }

        self.callback(rule)
        self.destroy()
