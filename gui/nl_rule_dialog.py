"""
Fylorra - Natural Language Rule Builder Dialog
AI-powered rule creation from plain English
"""

import customtkinter as ctk
from pathlib import Path
from typing import Optional, Callable
import threading
from utils.png_icons import PNGIconLoader
from core.nl_rule_builder import RuleGenerationResult


class _NLRuleUI:
    """Shared UI/logic for NL Rule Builder (dialog + embedded view)."""

    EXAMPLE_PROMPTS = [
        "Move all PDFs to Documents folder",
        "Copy new images to Backup drive",
        "Organize videos by date",
        "Move invoices with 'paid' in name to Archive folder",
        "Copy work documents to Projects folder",
        "Organize music files by file type"
    ]

    def _init_common(
        self,
        parent,
        nl_rule_builder,
        monitor_manager,
        current_folder: Optional[Path] = None,
        on_rule_created: Optional[Callable] = None,
        *,
        on_close=None,
        embedded: bool = False,
    ):
        self._app_root = parent
        self._on_close = on_close or (lambda: None)
        self._embedded = bool(embedded)

        self.nl_rule_builder = nl_rule_builder
        self.monitor_manager = monitor_manager
        self.current_folder = current_folder
        self.on_rule_created = on_rule_created
        self.icon_loader = PNGIconLoader()

        self.result: Optional[RuleGenerationResult] = None
        self.processing = False
        self.cancelled = False
        self.selected_monitor_id = None

        self._create_ui()

    def _top(self):
        try:
            return self.winfo_toplevel()
        except Exception:
            return self

    def _bring_to_front(self):
        """Bring dialog to front"""
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()

    def _create_ui(self):
        """Create the dialog UI"""
        # Header - COMPACT
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=70)
        header_frame.pack(fill="x", padx=20, pady=(15, 5))
        header_frame.pack_propagate(False)

        # AI Icon
        ai_icon = self.icon_loader.load_icon("analytics", size=(48, 48))
        icon_label = ctk.CTkLabel(header_frame, image=ai_icon, text="")
        icon_label.image = ai_icon
        icon_label.place(x=0, y=16)

        # Title
        title = ctk.CTkLabel(
            header_frame,
            text="Natural Language Rule Builder",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        )
        title.place(x=60, y=10)

        # Subtitle
        subtitle = ctk.CTkLabel(
            header_frame,
            text="Describe what you want in plain English - AI will create the automation rule",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="gray"
        )
        subtitle.place(x=60, y=45)

        # Existing AI Rules section - AT THE TOP (best place!)
        existing_container = ctk.CTkFrame(self, fg_color="transparent")
        existing_container.pack(fill="x", padx=20, pady=(5, 10))

        # Title with collapse toggle
        existing_header = ctk.CTkFrame(existing_container, fg_color="transparent")
        existing_header.pack(fill="x")

        self.existing_rules_visible = True
        self.toggle_btn = ctk.CTkButton(
            existing_header,
            text="▼ Existing Rules & Tasks",
            width=230,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
            anchor="w",
            command=self._toggle_existing_rules
        )
        self.toggle_btn.pack(side="left")

        # Quick access to scheduled tasks (time-based rules)
        try:
            from gui.scheduled_tasks_dialog import ScheduledTasksDialog

            def _open_scheduled_tasks():
                ScheduledTasksDialog(self, self.monitor_manager)

            ctk.CTkButton(
                existing_header,
                text="Scheduled Tasks",
                width=160,
                height=28,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color="#3a3a3a",
                hover_color="#4a4a4a",
                command=_open_scheduled_tasks,
            ).pack(side="left", padx=(10, 0))
        except Exception:
            pass

        # Scrollable frame for existing rules (compact)
        self.existing_rules_scroll = ctk.CTkScrollableFrame(
            existing_container,
            height=100,
            width=1040,
            fg_color="transparent",
            scrollbar_button_color="#2b2b2b",
            scrollbar_button_hover_color="#3a3a3a"
        )
        self.existing_rules_scroll.pack(fill="x", pady=(5, 0))

        self._show_existing_rules()

        # Input section - COMPACT
        input_frame = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=10)
        input_frame.pack(fill="x", padx=20, pady=(5, 10))

        input_label = ctk.CTkLabel(
            input_frame,
            text="What do you want to automate?",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w"
        )
        input_label.pack(anchor="w", padx=15, pady=(15, 10))

        # Text input - SMALLER
        self.input_text = ctk.CTkTextbox(
            input_frame,
            width=1040,
            height=60,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wrap="word"
        )
        self.input_text.pack(padx=15, pady=(0, 10))
        self.input_text.focus()

        # Quick examples
        examples_label = ctk.CTkLabel(
            input_frame,
            text="Try these examples:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray",
            anchor="w"
        )
        examples_label.pack(anchor="w", padx=15, pady=(5, 5))

        # Example buttons - 3 per row, COMPACT
        examples_row1 = ctk.CTkFrame(input_frame, fg_color="transparent", height=30)
        examples_row1.pack(fill="x", padx=15, pady=(0, 3))
        examples_row1.pack_propagate(False)

        examples_row2 = ctk.CTkFrame(input_frame, fg_color="transparent", height=30)
        examples_row2.pack(fill="x", padx=15, pady=(0, 10))
        examples_row2.pack_propagate(False)

        # Row 1 - First 3 examples - WIDER BUTTONS
        btn1 = ctk.CTkButton(
            examples_row1,
            text=self.EXAMPLE_PROMPTS[0],
            width=330,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._use_example(self.EXAMPLE_PROMPTS[0])
        )
        btn1.pack(side="left", padx=(0, 10))

        btn2 = ctk.CTkButton(
            examples_row1,
            text=self.EXAMPLE_PROMPTS[1],
            width=330,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._use_example(self.EXAMPLE_PROMPTS[1])
        )
        btn2.pack(side="left", padx=(0, 10))

        btn3 = ctk.CTkButton(
            examples_row1,
            text=self.EXAMPLE_PROMPTS[2],
            width=330,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._use_example(self.EXAMPLE_PROMPTS[2])
        )
        btn3.pack(side="left")

        # Row 2 - Last 3 examples - WIDER BUTTONS
        btn4 = ctk.CTkButton(
            examples_row2,
            text=self.EXAMPLE_PROMPTS[3],
            width=330,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._use_example(self.EXAMPLE_PROMPTS[3])
        )
        btn4.pack(side="left", padx=(0, 10))

        btn5 = ctk.CTkButton(
            examples_row2,
            text=self.EXAMPLE_PROMPTS[4],
            width=330,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._use_example(self.EXAMPLE_PROMPTS[4])
        )
        btn5.pack(side="left", padx=(0, 10))

        btn6 = ctk.CTkButton(
            examples_row2,
            text=self.EXAMPLE_PROMPTS[5],
            width=330,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._use_example(self.EXAMPLE_PROMPTS[5])
        )
        btn6.pack(side="left")

        # Results area
        self.results_frame = ctk.CTkScrollableFrame(self, width=860, height=350)
        # Don't pack yet - shown after generation

        # Bottom controls - Three buttons centered together
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", padx=20, pady=(10, 20))

        # Center container for buttons
        button_container = ctk.CTkFrame(controls_frame, fg_color="transparent")
        button_container.pack(expand=True)

        # Add Rule button - LEFT
        self.add_rule_btn = ctk.CTkButton(
            button_container,
            text="✓ Add This Rule",
            width=180,
            height=45,
            command=self._add_rule,
            state="disabled",
            fg_color="#424242",
            hover_color="#505050",
            font=ctk.CTkFont(family="Segoe UI", size=13)
        )
        self.add_rule_btn.pack(side="left", padx=(0, 10))

        # Generate button - CENTER (primary action, most prominent)
        self.generate_btn = ctk.CTkButton(
            button_container,
            text="✨ Generate Rule with AI",
            width=280,
            height=45,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#4CAF50",
            hover_color="#388E3C",
            command=self._generate_rule
        )
        self.generate_btn.pack(side="left", padx=10)

        # Close button - RIGHT
        self.close_btn = ctk.CTkButton(
            button_container,
            text="✖ Close",
            width=120,
            height=45,
            command=self._close,
            fg_color="#424242",
            hover_color="#505050",
            font=ctk.CTkFont(family="Segoe UI", size=13)
        )
        self.close_btn.pack(side="left", padx=(10, 0))

    def _use_example(self, example: str):
        """Fill input with example"""
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", example)

    def _generate_rule(self):
        """Generate rule from natural language"""
        user_input = self.input_text.get("1.0", "end").strip()

        if not user_input:
            from tkinter import messagebox
            messagebox.showwarning("Input Required", "Please describe what you want to automate")
            return

        # Disable button and show processing
        self.generate_btn.configure(state="disabled", text="🤖 AI is thinking...")

        # Process in background
        self.processing = True
        thread = threading.Thread(target=self._process_generation, args=(user_input,), daemon=True)
        thread.start()

    def _process_generation(self, user_input: str):
        """Process rule generation in background"""
        try:
            # Build context
            context = {}
            if self.current_folder:
                context["current_folder"] = str(self.current_folder)

            # Generate rule
            self.result = self.nl_rule_builder.generate_rule(user_input, context)

            # Show results
            if not self.cancelled and self.winfo_exists():
                self.after(0, self._show_results)

        except Exception as e:
            print(f"Generation error: {e}")
            import traceback
            traceback.print_exc()

            if not self.cancelled and self.winfo_exists():
                self.after(0, lambda: self._show_error(str(e)))

    def _show_results(self):
        """Display generated rule"""
        self.processing = False

        # Re-enable Generate button
        self.generate_btn.configure(state="normal", text="✨ Generate Rule with AI")

        # Enable Add Rule button with green color
        self.add_rule_btn.configure(
            state="normal",
            fg_color="#4CAF50",
            hover_color="#388E3C"
        )

        # Show results frame
        self.results_frame.pack(padx=20, pady=(10, 10), fill="both", expand=True)

        # Clear previous results
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        if not self.result:
            self._show_error_inline("Failed to generate rule")
            return

        # Confidence indicator
        conf_value = self.result.confidence
        if self.result.is_high_confidence():
            conf_color = "#4CAF50"
            conf_text = "HIGH CONFIDENCE"
            conf_icon = "✓"
        elif self.result.is_medium_confidence():
            conf_color = "#FF9800"
            conf_text = "MEDIUM CONFIDENCE"
            conf_icon = "!"
        else:
            conf_color = "#F44336"
            conf_text = "LOW CONFIDENCE"
            conf_icon = "⚠"

        conf_frame = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        conf_frame.pack(fill="x", pady=(10, 20))

        conf_label = ctk.CTkLabel(
            conf_frame,
            text=f"{conf_icon} {conf_text} ({conf_value:.0%})",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=conf_color
        )
        conf_label.pack()

        # Visual confidence bar
        conf_bar_bg = ctk.CTkFrame(conf_frame, height=8, fg_color="#2b2b2b", corner_radius=4)
        conf_bar_bg.pack(fill="x", pady=(10, 0), padx=150)

        conf_bar_fill = ctk.CTkFrame(
            conf_bar_bg,
            height=8,
            width=int(550 * conf_value),
            fg_color=conf_color,
            corner_radius=4
        )
        conf_bar_fill.place(x=0, y=0)

        # AI Interpretation
        self._add_section("🤖 AI Understanding", [
            ("Interpretation", self.result.interpretation)
        ], explanation_style=True)

        # Generated Rule (if successful)
        if self.result.rule:
            rule_items = [
                ("Trigger Events", ", ".join(self.result.rule["event_types"])),
                ("File Types", ", ".join(self.result.rule["file_extensions"][:10])),
                ("Action", self.result.rule["action_type"].title()),
            ]

            # Add action-specific params
            params = self.result.rule["action_params"]
            for key, value in params.items():
                rule_items.append((key.replace("_", " ").title(), str(value)))

            self._add_section("⚙️ Generated Rule", rule_items, highlight=True)

        # Explanation
        self._add_section("💡 AI Reasoning", [
            ("Explanation", self.result.explanation)
        ], explanation_style=True)

        # Warnings
        if self.result.warnings:
            warning_items = [(f"Warning {i+1}", warn) for i, warn in enumerate(self.result.warnings)]
            self._add_section("⚠️ Important Warnings", warning_items, warning_style=True)

        # Monitor Selection: always show for event-based rules so users know where it will be applied.
        # Scheduled tasks are time-based and do not attach to a monitor.
        if self.result.rule:
            try:
                if isinstance(self.result.rule.get("schedule"), dict) and self.result.rule.get("target_path"):
                    self._add_section(
                        "⏰ Scheduled Task Target",
                        [
                            ("Runs", str(self.result.rule.get("schedule"))),
                            ("Target", str(self.result.rule.get("target_path"))),
                        ],
                        highlight=True,
                    )
                else:
                    self._add_monitor_selection()
            except Exception:
                pass

        # Enable add button if confidence is acceptable
        if self.result.rule and not self.result.is_low_confidence():
            self.add_rule_btn.configure(state="normal")
        else:
            self.add_rule_btn.configure(state="disabled")

    def _add_section(self, title: str, items: list, highlight: bool = False, explanation_style: bool = False, warning_style: bool = False):
        """Add a section to results"""
        if warning_style:
            fg_color = "#4a2020"
        elif highlight:
            fg_color = "#1a4d2e"
        else:
            fg_color = "#2b2b2b"

        section_frame = ctk.CTkFrame(self.results_frame, fg_color=fg_color, corner_radius=8)
        section_frame.pack(fill="x", pady=8, padx=10)

        # Section title
        title_label = ctk.CTkLabel(
            section_frame,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w"
        )
        title_label.pack(anchor="w", padx=15, pady=(12, 8))

        # Items
        for label, value in items:
            item_frame = ctk.CTkFrame(section_frame, fg_color="transparent")
            item_frame.pack(fill="x", padx=15, pady=3)

            if explanation_style:
                # Multi-line explanation
                value_label = ctk.CTkLabel(
                    item_frame,
                    text=value,
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color="#e0e0e0",
                    anchor="w",
                    justify="left",
                    wraplength=780
                )
                value_label.pack(anchor="w", pady=(0, 10))
            else:
                # Label: Value format
                label_text = ctk.CTkLabel(
                    item_frame,
                    text=f"{label}:",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color="gray",
                    width=150,
                    anchor="w"
                )
                label_text.pack(side="left")

                value_text = ctk.CTkLabel(
                    item_frame,
                    text=value,
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#e0e0e0",
                    anchor="w",
                    wraplength=600
                )
                value_text.pack(side="left", fill="x", expand=True)

    def _show_error_inline(self, error_msg: str):
        """Show error in results area"""
        error_frame = ctk.CTkFrame(self.results_frame, fg_color="#2b2b2b", corner_radius=8)
        error_frame.pack(fill="both", expand=True, pady=50, padx=50)

        error_icon = ctk.CTkLabel(
            error_frame,
            text="❌",
            font=ctk.CTkFont(size=48),
            text_color="#F44336"
        )
        error_icon.pack(pady=(30, 10))

        error_label = ctk.CTkLabel(
            error_frame,
            text="Failed to Generate Rule",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#F44336"
        )
        error_label.pack(pady=10)

        error_desc = ctk.CTkLabel(
            error_frame,
            text=error_msg,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray",
            wraplength=600
        )
        error_desc.pack(pady=(0, 30))

    def _show_error(self, error_msg: str):
        """Show error dialog"""
        self.generate_btn.configure(state="normal", text="✨ Generate Rule with AI")

        from tkinter import messagebox
        messagebox.showerror("Generation Failed", f"Could not generate rule:\n\n{error_msg}")

    def _add_monitor_selection(self):
        """Add monitor selection section"""
        section_frame = ctk.CTkFrame(self.results_frame, fg_color="#2b2b2b", corner_radius=8)
        section_frame.pack(fill="x", pady=8, padx=10)

        # Section title
        title_label = ctk.CTkLabel(
            section_frame,
            text="📌 Where to Add This Rule?",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w"
        )
        title_label.pack(anchor="w", padx=15, pady=(12, 8))

        # Description
        desc_label = ctk.CTkLabel(
            section_frame,
            text="Choose an existing monitor or create a new one",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray",
            anchor="w"
        )
        desc_label.pack(anchor="w", padx=15, pady=(0, 10))

        # Get active monitors
        monitors = self.monitor_manager.monitors
        monitor_options = []

        if monitors:
            for monitor_id, monitor in monitors.items():
                # Skip FTP monitors
                if not hasattr(monitor, 'path'):
                    continue
                path_name = Path(monitor.path).name if hasattr(monitor, 'path') else "Unknown"
                monitor_options.append(f"{path_name} ({monitor.path[:50]}...)")

        # Add "Create New Monitor" option
        monitor_options.insert(0, "➕ Create New Monitor")

        # Dropdown
        self.monitor_dropdown = ctk.CTkOptionMenu(
            section_frame,
            values=monitor_options,
            width=820,
            height=35,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._on_monitor_selected
        )
        self.monitor_dropdown.pack(padx=15, pady=(0, 15))
        self.monitor_dropdown.set(monitor_options[0])

        # Store monitor IDs for reference
        self.monitor_ids = list(monitors.keys()) if monitors else []

    def _on_monitor_selected(self, choice: str):
        """Handle monitor selection"""
        if choice.startswith("➕"):
            self.selected_monitor_id = None  # Create new
        else:
            # Get index (subtract 1 for "Create New" option)
            monitor_options = self.monitor_dropdown.cget("values")
            index = monitor_options.index(choice) - 1
            if 0 <= index < len(self.monitor_ids):
                self.selected_monitor_id = self.monitor_ids[index]

    def _add_rule(self):
        """Add the generated rule"""
        if not self.result or not self.result.rule:
            return

        # Scheduled task rule (time-based, not event monitoring)
        if isinstance(self.result.rule.get("schedule"), dict) and self.result.rule.get("target_path"):
            from tkinter import messagebox
            schedule = self.result.rule.get("schedule") or {}
            title = self.result.interpretation or "Scheduled Task"
            confirm_msg = f"{title}\n\n"
            confirm_msg += f"Schedule: {schedule}\n"
            confirm_msg += f"Target: {self.result.rule.get('target_path')}\n"
            confirm_msg += f"Action: {self.result.rule.get('action_type')}\n\n"
            if self.result.warnings:
                confirm_msg += "Warnings:\n" + "\n".join(f"• {w}" for w in self.result.warnings[:6]) + "\n\n"
            confirm_msg += "Add this scheduled task?\n(Tasks run only while Fylorra is open.)"
            if not messagebox.askyesno("Add Scheduled Task?", confirm_msg, parent=self):
                return
            ok = self.monitor_manager.add_scheduled_task(
                {
                    "title": title,
                    "schedule": dict(schedule),
                    "action_type": str(self.result.rule.get("action_type") or ""),
                    "action_params": dict(self.result.rule.get("action_params") or {}),
                    "target_path": str(self.result.rule.get("target_path") or ""),
                    "enabled": True,
                }
            )
            if ok:
                saved_to = ""
                try:
                    p = getattr(self.monitor_manager.settings_manager, "scheduled_tasks_file", None)
                    if p:
                        saved_to = f"\n\nSaved to:\n{p}"
                except Exception:
                    saved_to = ""
                try:
                    messagebox.showinfo(
                        "Scheduled Task Added",
                        "Scheduled task saved.\n\nRuns only while Fylorra is open." + saved_to,
                        parent=self,
                    )
                except Exception:
                    pass
                try:
                    if callable(self.on_rule_created):
                        self.on_rule_created(self.result.rule)
                except Exception:
                    pass
                # Keep dialog open; refresh Existing Rules & Tasks so it's visible immediately.
                try:
                    if not self.existing_rules_visible:
                        self._toggle_existing_rules()
                    self._show_existing_rules()
                except Exception:
                    pass
                try:
                    self.input_text.delete("1.0", "end")
                except Exception:
                    pass
                try:
                    self.plan_text.configure(state="normal")
                    self.plan_text.delete("1.0", "end")
                    self.plan_text.configure(state="disabled")
                except Exception:
                    pass
                self.result = None
            else:
                try:
                    messagebox.showerror("Error", "Failed to add scheduled task.", parent=self)
                except Exception:
                    pass
            return

        # Check for placeholder values that need user input
        params = self.result.rule["action_params"]
        needs_input = any("{{NEEDS_USER_INPUT}}" in str(v) or "{{CURRENT_FOLDER}}" in str(v) for v in params.values())

        if needs_input:
            from tkinter import messagebox, filedialog

            # Ask user to specify paths
            if "destination" in params:
                current_dest = params["destination"]
                if "{{NEEDS_USER_INPUT}}" in current_dest or "{{CURRENT_FOLDER}}" in current_dest:
                    folder = filedialog.askdirectory(title="Select Destination Folder", parent=self)
                    # Bring dialog back to front
                    self._bring_to_front()
                    if not folder:
                        return
                    params["destination"] = folder

        # Confirm with user - allow editing destination
        from tkinter import messagebox, filedialog
        confirm_msg = f"{self.result.interpretation}\n\n"
        confirm_msg += f"Confidence: {self.result.confidence:.0%}\n\n"

        # Show destination if it's a move/copy action
        if self.result.rule.get("action_type") in ["move", "copy"]:
            dest = params.get("destination", "")
            confirm_msg += f"Destination: {dest}\n\n"

        if self.result.warnings:
            confirm_msg += "Warnings:\n" + "\n".join(f"• {w}" for w in self.result.warnings[:3]) + "\n\n"

        # Ask: Add, Edit, or Cancel
        response = messagebox.askyesnocancel(
            "Add Rule?",
            confirm_msg + "Yes = Add Rule\nNo = Edit Destination\nCancel = Go Back",
            icon='question'
        )

        if response is None:  # Cancel
            return
        elif response is False:  # Edit destination
            new_dest = filedialog.askdirectory(
                title="Select New Destination Folder",
                initialdir=params.get("destination", ""),
                parent=self
            )
            # Bring dialog back to front
            self._bring_to_front()
            if new_dest:
                params["destination"] = new_dest
                # Ask again to confirm
                self._add_rule()
            return
        # else response is True - continue to add rule

        # Add to existing monitor or create new
        if self.selected_monitor_id:
            # Add to existing monitor
            self._add_to_existing_monitor()
        else:
            # Create new monitor
            self._create_new_monitor()

    def _add_to_existing_monitor(self):
        """Add rule to existing monitor"""
        from tkinter import messagebox

        if not self.selected_monitor_id or not self.result.rule:
            return

        try:
            monitor = self.monitor_manager.monitors.get(self.selected_monitor_id)
            if not monitor:
                messagebox.showerror("Error", "Selected monitor not found")
                return

            # CRITICAL: Check for infinite loop (source = EXACT same destination, not subfolder)
            if self.result.rule.get("action_type") in ["move", "copy"]:
                dest = self.result.rule.get("action_params", {}).get("destination", "")
                source = Path(monitor.path).resolve()
                dest_resolved = Path(dest).resolve() if dest else None

                # Only block if EXACT same path (subfolders are OK)
                if dest_resolved and dest_resolved == source:
                    messagebox.showerror(
                        "Invalid Rule",
                        f"CANNOT move/copy to the EXACT SAME folder!\n\n"
                        f"Monitor: {monitor.path}\n"
                        f"Destination: {dest}\n\n"
                        f"This creates an infinite loop (_1, _1_1, _1_1_1...)\n\n"
                        f"TIP: Create a SUBFOLDER instead:\n"
                        f"Example: {monitor.path}\\Organized"
                    )
                    return

            # Add AI prompt to rule for future reference
            rule_with_prompt = self.result.rule.copy()
            rule_with_prompt["ai_prompt"] = self.result.original_input

            # Add rule to monitor
            monitor.rules.append(rule_with_prompt)

            # Save configuration
            self.monitor_manager.save_monitors()

            # Call callback if provided
            if self.on_rule_created:
                self.on_rule_created(self.result.rule, self.selected_monitor_id)

            messagebox.showinfo("Success", "Rule added to monitor successfully!")
            if not getattr(self, "_embedded", False):
                self._on_close()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to add rule:\n{e}")

    def _create_new_monitor(self):
        """Create new monitor with the generated rule"""
        from tkinter import messagebox, filedialog
        import uuid

        if not self.result.rule:
            return

        # Ask for folder to monitor
        folder_path = filedialog.askdirectory(title="Select Folder to Monitor", parent=self._top())
        # Bring dialog back to front
        self._bring_to_front()
        if not folder_path:
            return

        # CRITICAL: Check for infinite loop (EXACT same folder, not subfolder)
        if self.result.rule.get("action_type") in ["move", "copy"]:
            dest = self.result.rule.get("action_params", {}).get("destination", "")
            source = Path(folder_path).resolve()
            dest_resolved = Path(dest).resolve() if dest else None

            # Only block if EXACT same path (subfolders are OK)
            if dest_resolved and dest_resolved == source:
                messagebox.showerror(
                    "Invalid Rule",
                    f"CANNOT move/copy to the EXACT SAME folder!\n\n"
                    f"Source: {folder_path}\n"
                    f"Destination: {dest}\n\n"
                    f"This creates an infinite loop (_1, _1_1, _1_1_1...)\n\n"
                    f"TIP: Create a SUBFOLDER instead:\n"
                    f"Example: {folder_path}\\Organized"
                )
                return

        try:
            # Create new monitor
            monitor_id = str(uuid.uuid4())

            # Add AI prompt to rule for future reference
            rule_with_prompt = self.result.rule.copy()
            rule_with_prompt["ai_prompt"] = self.result.original_input

            success = self.monitor_manager.add_monitor(
                monitor_id,
                folder_path,
                [rule_with_prompt],  # Rules list with our AI-generated rule
                notify_created=True,
                notify_modified=True,
                notify_deleted=False,
                notify_moved=False
            )

            if success:
                # Call callback if provided
                if self.on_rule_created:
                    self.on_rule_created(self.result.rule, monitor_id, folder_path)

                messagebox.showinfo("Success", f"New monitor created with AI rule!\n\nMonitoring: {folder_path}")
                if not getattr(self, "_embedded", False):
                    self._on_close()
            else:
                messagebox.showerror("Error", "Failed to create monitor")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to create monitor:\n{e}")

    def _toggle_existing_rules(self):
        """Toggle visibility of existing rules section"""
        if self.existing_rules_visible:
            self.existing_rules_scroll.pack_forget()
            self.toggle_btn.configure(text="▶ Existing Rules & Tasks")
            self.existing_rules_visible = False
        else:
            self.existing_rules_scroll.pack(fill="x", pady=(5, 0))
            self.toggle_btn.configure(text="▼ Existing Rules & Tasks")
            self.existing_rules_visible = True

    def _show_existing_rules(self):
        """Display existing AI-created rules and scheduled tasks"""
        # Clear scroll frame
        for widget in self.existing_rules_scroll.winfo_children():
            widget.destroy()

        # Collect ONLY AI-created rules from all monitors
        all_rules = []
        monitors = self.monitor_manager.monitors

        for monitor_id, monitor in monitors.items():
            if not hasattr(monitor, 'rules') or not monitor.rules:
                continue

            monitor_path = getattr(monitor, 'path', 'Unknown')
            for rule_idx, rule in enumerate(monitor.rules):
                # FILTER: Only show AI-created rules
                if self._is_ai_rule(rule):
                    all_rules.append({
                        'monitor_path': monitor_path,
                        'monitor_id': monitor_id,
                        'rule': rule,
                        'rule_idx': rule_idx
                    })

        # Collect scheduled tasks (time-based) if available.
        scheduled = []
        try:
            if hasattr(self.monitor_manager, "scheduled_tasks"):
                scheduled = list(self.monitor_manager.scheduled_tasks.list_tasks() or [])
        except Exception:
            scheduled = []

        if not all_rules and not scheduled:
            # No rules/tasks message
            no_rules_label = ctk.CTkLabel(
                self.existing_rules_scroll,
                text="No AI rules or scheduled tasks yet. Create your first one above!",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="gray"
            )
            no_rules_label.pack(anchor="w", pady=10)
            return

        # Scheduled tasks section
        if scheduled:
            hdr = ctk.CTkLabel(
                self.existing_rules_scroll,
                text="⏰ Scheduled Tasks",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                anchor="w",
            )
            hdr.pack(anchor="w", padx=6, pady=(6, 2))
            for t in scheduled:
                try:
                    title = getattr(t, "title", "Scheduled Task")
                    schedule = getattr(t, "schedule", {}) or {}
                    target = getattr(t, "target_path", "")
                    action = (getattr(t, "action_type", "") or "").upper()
                except Exception:
                    continue

                task_card = ctk.CTkFrame(self.existing_rules_scroll, fg_color="#2b2b2b", corner_radius=6)
                task_card.pack(fill="x", pady=5, padx=5)

                title_label = ctk.CTkLabel(
                    task_card,
                    text=f"⏰ {title}",
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    anchor="w"
                )
                title_label.pack(anchor="w", padx=8, pady=(6, 2))

                desc = f"⚙️ {action} • {schedule} • {Path(target).name if target else target}"
                desc_label = ctk.CTkLabel(
                    task_card,
                    text=desc,
                    font=ctk.CTkFont(family="Segoe UI", size=9),
                    text_color="gray",
                    anchor="w",
                    wraplength=1000
                )
                desc_label.pack(anchor="w", padx=8, pady=(0, 6))

        # AI rules section
        if all_rules:
            hdr = ctk.CTkLabel(
                self.existing_rules_scroll,
                text="🤖 AI Rules (Event‑Based)",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                anchor="w",
            )
            hdr.pack(anchor="w", padx=6, pady=(10, 2))

        # Display each rule directly in the scroll frame
        for item in all_rules:
            rule = item['rule']
            monitor_path = item['monitor_path']

            rule_card = ctk.CTkFrame(self.existing_rules_scroll, fg_color="#2b2b2b", corner_radius=6)
            rule_card.pack(fill="x", pady=5, padx=5)

            # Monitor path (smaller, compact)
            path_label = ctk.CTkLabel(
                rule_card,
                text=f"📁 {Path(monitor_path).name}",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                anchor="w"
            )
            path_label.pack(anchor="w", padx=8, pady=(6, 2))

            # Original prompt (if available) - PURPLE ITALIC
            original_prompt = rule.get('ai_prompt', '')
            if original_prompt:
                prompt_label = ctk.CTkLabel(
                    rule_card,
                    text=f'💬 "{original_prompt}"',
                    font=ctk.CTkFont(family="Segoe UI", size=9, slant="italic"),
                    text_color="#9C27B0",
                    anchor="w",
                    wraplength=1000
                )
                prompt_label.pack(anchor="w", padx=8, pady=(0, 2))

            # Rule description - COMPACT
            action = rule.get('action_type', 'unknown').upper()
            extensions = ', '.join(rule.get('file_extensions', ['*'])[:5])
            if len(rule.get('file_extensions', [])) > 5:
                extensions += "..."
            dest = rule.get('action_params', {}).get('destination', 'N/A')
            name_pattern = rule.get('name_pattern', '')

            desc_text = f"⚙️ {action}: {extensions}"
            if name_pattern:
                desc_text += f" (pattern: {name_pattern[:30]}...)" if len(name_pattern) > 30 else f" (pattern: {name_pattern})"
            desc_text += f" → {Path(dest).name if dest != 'N/A' else dest}"

            desc_label = ctk.CTkLabel(
                rule_card,
                text=desc_text,
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color="gray",
                anchor="w",
                wraplength=1000
            )
            desc_label.pack(anchor="w", padx=8, pady=(0, 6))

    def _is_ai_rule(self, rule: dict) -> bool:
        """Check if rule was created by AI (not manually)"""
        # AI rules have at least one of these markers:
        # 1. name_pattern (AI uses this for filename filtering)
        # 2. handle_duplicates parameter
        # 3. organize_by parameter
        # 4. ai_prompt field (we'll add this)

        if "ai_prompt" in rule:
            return True

        if "name_pattern" in rule and rule["name_pattern"]:
            return True

        if rule.get("action_type") == "organize" and "organize_by" in rule.get("action_params", {}):
            return True

        if rule.get("action_type") in ["move", "copy"]:
            if "handle_duplicates" in rule.get("action_params", {}):
                return True

        return False

    def _close(self):
        """Close dialog"""
        self.cancelled = True
        self._on_close()


class NLRuleView(_NLRuleUI, ctk.CTkFrame):
    """Embeddable Natural Language Rule Builder (used in MainWindow)."""

    def __init__(self, parent, nl_rule_builder, monitor_manager, current_folder: Optional[Path] = None, on_rule_created: Optional[Callable] = None, *, on_close=None):
        super().__init__(parent, fg_color="transparent")
        self._init_common(parent, nl_rule_builder, monitor_manager, current_folder=current_folder, on_rule_created=on_rule_created, on_close=on_close, embedded=True)


class NLRuleDialog(_NLRuleUI, ctk.CTkToplevel):
    """Dialog wrapper for Natural Language Rule Builder (kept for compatibility)."""

    def __init__(self, parent, nl_rule_builder, monitor_manager, current_folder: Optional[Path] = None, on_rule_created: Optional[Callable] = None):
        super().__init__(parent)

        self.title("AI Rule Builder - Natural Language")
        self.geometry("1100x850")
        self.resizable(True, True)  # ALLOW RESIZE - can shrink/stretch
        self.minsize(900, 700)  # Minimum size to prevent breaking layout

        try:
            # Make dialog stay on top of parent
            self.transient(parent)
        except Exception:
            pass

        # Center on screen
        try:
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - 550
            y = (self.winfo_screenheight() // 2) - 425
            self.geometry(f"1100x850+{x}+{y}")
        except Exception:
            pass

        self._init_common(parent, nl_rule_builder, monitor_manager, current_folder=current_folder, on_rule_created=on_rule_created, on_close=self.destroy, embedded=False)

        # Bring to front AFTER UI is created
        self.after(10, self._bring_to_front)
