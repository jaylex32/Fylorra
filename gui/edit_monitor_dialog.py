"""Edit Monitor Dialog - Edit existing monitor settings"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List


class EditMonitorDialog(ctk.CTkToplevel):
    """Dialog for editing an existing monitor"""

    def __init__(self, parent, monitor_data: Dict, callback: Callable):
        super().__init__(parent)

        self.monitor_data = monitor_data
        self.callback = callback
        self.rules = list(monitor_data.get("rules", []))

        # Configure window
        self.title("Edit Monitor")
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
        title = ctk.CTkLabel(
            main_container,
            text="✎ Edit Monitor Settings",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(0, 15))

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

        # Folder path (read-only)
        folder_frame = ctk.CTkFrame(container, fg_color="transparent")
        folder_frame.pack(fill="x", pady=10)

        folder_label = ctk.CTkLabel(
            folder_frame,
            text="Monitor Path:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        folder_label.pack(anchor="w")

        self.path_entry = ctk.CTkEntry(
            folder_frame,
            height=35
        )
        self.path_entry.insert(0, self.monitor_data.get("path", ""))
        self.path_entry.configure(state="readonly")
        self.path_entry.pack(fill="x", pady=(5, 0))

        path_note = ctk.CTkLabel(
            folder_frame,
            text="Note: To change the path, please remove and re-add the monitor",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        path_note.pack(anchor="w", pady=(2, 0))

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

        self.notify_created_var = ctk.BooleanVar(value=self.monitor_data.get("notify_created", True))
        self.notify_modified_var = ctk.BooleanVar(value=self.monitor_data.get("notify_modified", True))
        self.notify_deleted_var = ctk.BooleanVar(value=self.monitor_data.get("notify_deleted", True))
        self.notify_moved_var = ctk.BooleanVar(value=self.monitor_data.get("notify_moved", True))

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
        self.email_entry.insert(0, self.monitor_data.get("email_recipient", ""))
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
            text="Only process files matching these criteria (leave empty for no filtering):",
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
        if self.monitor_data.get("min_size_kb"):
            self.min_size_entry.insert(0, str(self.monitor_data["min_size_kb"]))
        self.min_size_entry.pack(side="left", padx=5)

        ctk.CTkLabel(size_frame, text="Max (KB):").pack(side="left", padx=5)
        self.max_size_entry = ctk.CTkEntry(size_frame, width=80, placeholder_text="∞")
        if self.monitor_data.get("max_size_kb"):
            self.max_size_entry.insert(0, str(self.monitor_data["max_size_kb"]))
        self.max_size_entry.pack(side="left", padx=5)

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
        if self.monitor_data.get("modified_within_days"):
            self.date_filter_entry.insert(0, str(self.monitor_data["modified_within_days"]))
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

        self.exclude_patterns_text = ctk.CTkTextbox(
            exclude_frame,
            height=60,
            fg_color=("gray85", "gray20")
        )
        self.exclude_patterns_text.pack(fill="x")

        # Load existing exclude patterns
        existing_patterns = self.monitor_data.get("exclude_patterns", [])
        if existing_patterns:
            if isinstance(existing_patterns, str):
                normalized = [
                    line.strip()
                    for line in existing_patterns.replace("\r", "\n").replace(",", "\n").split("\n")
                    if line.strip() and not line.strip().startswith("#")
                ]
            else:
                normalized = [str(x).strip() for x in existing_patterns if str(x).strip()]
            self.exclude_patterns_text.insert("1.0", "\n".join(normalized))
        else:
            self.exclude_patterns_text.insert("1.0", "# Example:\n# *.tmp\n# node_modules/\n# .git/")

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
            placeholder_text="e.g., .*\\.pdf$ or report_\\d{4}\\.xlsx"
        )
        if self.monitor_data.get("filename_regex"):
            self.regex_entry.insert(0, self.monitor_data["filename_regex"])
        self.regex_entry.pack(fill="x")

        # Rules section
        rules_frame = ctk.CTkFrame(container, fg_color="transparent")
        rules_frame.pack(fill="both", expand=True, pady=10)

        rules_header = ctk.CTkFrame(rules_frame, fg_color="transparent")
        rules_header.pack(fill="x")

        rules_label = ctk.CTkLabel(
            rules_header,
            text="Automation Rules:",
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

        self._display_rules()

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

        save_btn = ctk.CTkButton(
            button_frame,
            text="Save Changes",
            width=120,
            command=self._save_changes,
            fg_color="#2fa572",
            hover_color="#106a43"
        )
        save_btn.pack(side="right", padx=5)

    def _display_rules(self):
        """Display all rules"""
        # Clear existing
        for widget in self.rules_scrollable.winfo_children():
            widget.destroy()

        if not self.rules:
            info_label = ctk.CTkLabel(
                self.rules_scrollable,
                text="No automation rules configured\n\nClick '+ Add Rule' to create rules",
                font=ctk.CTkFont(size=11),
                text_color="gray"
            )
            info_label.pack(pady=30)
        else:
            for rule in self.rules:
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

    def _add_rule(self):
        """Add a new rule"""
        from gui.add_monitor_dialog import RuleDialog
        RuleDialog(self, self._on_rule_added)

    def _on_rule_added(self, rule: Dict):
        """Callback when rule is added"""
        self.rules.append(rule)
        self._display_rules()

    def _remove_rule(self, rule: Dict, card: ctk.CTkFrame):
        """Remove a rule"""
        self.rules.remove(rule)
        card.destroy()

        # Show info message if no rules
        if len(self.rules) == 0:
            self._display_rules()

    def _save_changes(self):
        """Save changes and close"""
        # Parse filter values
        min_size = self.min_size_entry.get().strip()
        max_size = self.max_size_entry.get().strip()
        date_days = self.date_filter_entry.get().strip()

        # Get exclude patterns (filter out comments and empty lines)
        exclude_text = self.exclude_patterns_text.get("1.0", "end").strip()
        exclude_patterns = [
            line.strip() for line in exclude_text.split('\n')
            if line.strip() and not line.strip().startswith('#')
        ]

        updated_data = {
            "id": self.monitor_data["id"],
            "path": self.monitor_data["path"],
            "rules": self.rules,
            "type": self.monitor_data.get("type", "folder"),
            "notify_created": self.notify_created_var.get(),
            "notify_modified": self.notify_modified_var.get(),
            "notify_deleted": self.notify_deleted_var.get(),
            "notify_moved": self.notify_moved_var.get(),
            "email_recipient": self.email_entry.get().strip(),
            # Advanced filters
            "min_size_kb": int(min_size) if min_size.isdigit() else None,
            "max_size_kb": int(max_size) if max_size.isdigit() else None,
            "modified_within_days": int(date_days) if date_days.isdigit() else None,
            "exclude_patterns": exclude_patterns,
            "filename_regex": self.regex_entry.get().strip() or None
        }

        self.callback(updated_data)
        self.destroy()
