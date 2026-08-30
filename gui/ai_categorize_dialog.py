"""
Fylorra - AI Auto-Categorize Dialog
Organize files by visual content
Enhanced with 51 comprehensive categories
"""

import customtkinter as ctk
from pathlib import Path
from typing import Dict, List, Optional
import threading
import json
from utils.png_icons import PNGIconLoader
from core.enhanced_categorizer import EnhancedCategorizer
from utils.tooltip import ToolTipHelper
from utils.universal_undo import get_undo_manager, FileOperation, OperationType
from datetime import datetime
from tkinter import filedialog


class AICategorizeDialog(ctk.CTkToplevel):
    """Dialog for auto-categorizing files in a folder"""

    def __init__(self, parent, ai_manager, ai_categorizer, folder_path: Path):
        super().__init__(parent)

        self.ai_manager = ai_manager
        # Use enhanced categorizer with 51 categories
        self.enhanced_categorizer = EnhancedCategorizer(ai_manager=ai_manager, use_ai_vision=False)
        self.folder_path = folder_path
        self.icon_loader = PNGIconLoader()

        self.categorized: Dict[str, List[Path]] = {}
        self.category_checkboxes: Dict[str, ctk.BooleanVar] = {}  # Track checkbox states
        self.processing = False
        self.cancelled = False
        self._last_transaction_id: Optional[int] = None
        self.include_subfolders = True  # Default to include subfolders
        self._autostart_after_id = None
        self._options_touched = False
        self._results_stale = False

        self.title("Auto-Categorize - 51 Categories")
        self.geometry("700x700")
        self.resizable(True, True)
        self.minsize(700, 650)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 350
        y = (self.winfo_screenheight() // 2) - 350
        self.geometry(f"700x700+{x}+{y}")

        self._create_ui()

        # Auto-start (delayed) so users can change options when launched from Workspace.
        self._schedule_autostart()

    def _create_ui(self):
        """Create the dialog UI"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)

        ai_icon = self.icon_loader.load_icon("analytics", size=(32, 32))
        icon_label = ctk.CTkLabel(header_frame, image=ai_icon, text="")
        icon_label.image = ai_icon
        icon_label.place(x=0, y=9)

        title = ctk.CTkLabel(
            header_frame,
            text="Enhanced Categorization - 51 Categories",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        )
        title.place(x=40, y=10)

        # Subtitle
        self.subtitle = ctk.CTkLabel(
            self,
            text=f"Organizing: {self.folder_path.name}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray"
        )
        self.subtitle.pack(pady=(0, 5))

        # Top controls (compact)
        top_card = ctk.CTkFrame(self, corner_radius=12)
        top_card.pack(fill="x", padx=20, pady=(8, 10))
        top_card.grid_columnconfigure(0, weight=1)
        top_card.grid_columnconfigure(1, weight=1)
        top_card.grid_columnconfigure(2, weight=0)

        self.subfolders_var = ctk.BooleanVar(value=True)
        self.subfolders_checkbox = ctk.CTkCheckBox(
            top_card,
            text="Include subfolders",
            variable=self.subfolders_var,
            command=self._on_subfolder_toggle,
        )
        self.subfolders_checkbox.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        ToolTipHelper.add_tooltip(self.subfolders_checkbox, "Search all subfolders recursively for files to categorize")

        self.smart_scope_var = ctk.BooleanVar(value=True)
        self.smart_scope_checkbox = ctk.CTkCheckBox(
            top_card,
            text="Smart scope (skip projects/caches)",
            variable=self.smart_scope_var,
            command=self._on_options_changed,
        )
        self.smart_scope_checkbox.grid(row=0, column=1, sticky="w", padx=12, pady=(12, 6))
        ToolTipHelper.add_tooltip(
            self.smart_scope_checkbox,
            "Avoids shredding code/audio/video projects by skipping typical project roots and cache/build folders.",
        )

        self.include_other_var = ctk.BooleanVar(value=False)
        self.include_other_checkbox = ctk.CTkCheckBox(
            top_card,
            text="Include 'Other' (move unknown formats)",
            variable=self.include_other_var,
            command=self._on_options_changed,
        )
        self.include_other_checkbox.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))
        ToolTipHelper.add_tooltip(
            self.include_other_checkbox,
            "Off = unknown/unrecognized files are left in place. On = unknown files will be grouped into 'Other'.",
        )

        self.move_files_var = ctk.BooleanVar(value=False)
        self.move_checkbox = ctk.CTkCheckBox(
            top_card,
            text="Move files to category folders",
            variable=self.move_files_var,
            state="disabled",
        )
        self.move_checkbox.grid(row=1, column=1, sticky="w", padx=12, pady=(0, 6))
        ToolTipHelper.add_tooltip(self.move_checkbox, "Preview only by default; enable to apply moves.")

        can_ai_manager = bool(self.ai_manager)
        self.use_ai_vision_var = ctk.BooleanVar(value=False)
        self.ai_checkbox = ctk.CTkCheckBox(
            top_card,
            text="AI vision (images)",
            variable=self.use_ai_vision_var,
            state="normal" if can_ai_manager else "disabled",
            command=self._on_ai_vision_toggle,
        )
        self.ai_checkbox.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
        ToolTipHelper.add_tooltip(self.ai_checkbox, "Uses the local vision model for harder image categories.")

        self.use_ai_docs_var = ctk.BooleanVar(value=False)
        self.ai_docs_checkbox = ctk.CTkCheckBox(
            top_card,
            text="AI (scanned PDFs)",
            variable=self.use_ai_docs_var,
            state="normal" if can_ai_manager else "disabled",
            command=self._on_ai_vision_toggle,
        )
        self.ai_docs_checkbox.grid(row=2, column=1, sticky="w", padx=12, pady=(0, 10))
        ToolTipHelper.add_tooltip(self.ai_docs_checkbox, "High-confidence only; cached + rate limited.")

        self._ai_state_label = ctk.CTkLabel(top_card, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self._ai_state_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 12))

        # Summary / report (collapsed by default)
        self.summary_open_var = ctk.BooleanVar(value=False)
        self.summary_btn = ctk.CTkButton(top_card, text="Summary ▾", width=120, command=self._toggle_summary)
        self.summary_btn.grid(row=0, column=2, sticky="e", padx=12, pady=(12, 6))

        self.summary_body = ctk.CTkFrame(top_card, corner_radius=10)
        self.summary_body.grid(row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        self.summary_body.grid_remove()
        self.summary_body.grid_columnconfigure(0, weight=1)

        self.summary_text = ctk.CTkLabel(self.summary_body, text="", justify="left", anchor="w")
        self.summary_text.grid(row=0, column=0, sticky="w", padx=12, pady=10)

        right = ctk.CTkFrame(self.summary_body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=12, pady=10)

        self.conf_threshold = ctk.DoubleVar(value=0.75)
        ctk.CTkLabel(right, text="Auto-select ≥", text_color="gray").pack(side="left", padx=(0, 6))
        self.conf_slider = ctk.CTkSlider(right, from_=0.5, to=0.95, number_of_steps=9, variable=self.conf_threshold)
        self.conf_slider.pack(side="left", padx=(0, 8))
        self.conf_value = ctk.CTkLabel(right, text="0.75", text_color="gray")
        self.conf_value.pack(side="left", padx=(0, 10))
        self.conf_slider.configure(command=lambda v: self.conf_value.configure(text=f"{float(v):.2f}"))

        self.auto_select_btn = ctk.CTkButton(right, text="Auto-select", width=110, command=self._auto_select_by_confidence)
        self.auto_select_btn.pack(side="left", padx=(0, 8))
        self.export_btn = ctk.CTkButton(right, text="Export Report", width=120, command=self._export_report)
        self.export_btn.pack(side="left")

        # Progress
        self.progress = ctk.CTkProgressBar(self, width=660)
        self.progress.pack(padx=20, pady=(0, 20))
        self.progress.set(0)

        # Results frame (fixed height to ensure buttons are visible)
        self.results_frame = ctk.CTkScrollableFrame(self, width=660)
        self.results_frame.pack(padx=20, pady=(0, 10), fill="both", expand=True)

        # Controls
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Left side - Close and Undo
        left_controls = ctk.CTkFrame(controls_frame, fg_color="transparent")
        left_controls.pack(side="left")

        self.cancel_btn = ctk.CTkButton(
            left_controls,
            text="Cancel",
            width=100,
            command=self._close,
            fg_color="gray"
        )
        self.cancel_btn.pack(side="left", padx=(0, 10))
        self.cancel_btn.configure(state="normal")

        self.start_btn = ctk.CTkButton(
            left_controls,
            text="Start",
            width=100,
            command=self._start_processing,
        )
        self.start_btn.pack(side="left", padx=(0, 10))

        # Undo button
        self.undo_btn = ctk.CTkButton(
            left_controls,
            text="⏮️ Undo",
            width=100,
            command=self._undo_last_operation,
            fg_color="gray"
        )
        self.undo_btn.pack(side="left")

        # Right side - Apply
        self.apply_btn = ctk.CTkButton(
            controls_frame,
            text="Apply Organization",
            width=150,
            command=self._apply_organization,
            state="disabled"
        )
        self.apply_btn.pack(side="right")

        # Add tooltips to buttons
        ToolTipHelper.add_tooltips_batch({
            self.cancel_btn: "cancel_operation",
            self.apply_btn: "apply_changes"
        })

    def _on_subfolder_toggle(self):
        """Handle subfolder checkbox toggle"""
        self.include_subfolders = self.subfolders_var.get()
        self._on_options_changed()

    def _on_options_changed(self):
        self._options_touched = True
        self._cancel_autostart()
        self._mark_results_stale()

    def _mark_results_stale(self):
        if self.processing or self.cancelled:
            return
        if self.categorized:
            self._results_stale = True
            try:
                self.start_btn.configure(state="normal", text="Re-run")
            except Exception:
                pass
            try:
                self.apply_btn.configure(state="disabled")
                self.move_checkbox.configure(state="disabled")
            except Exception:
                pass
            try:
                self.subtitle.configure(text="Options changed — click Re-run to update results")
            except Exception:
                pass

    def _cancel_autostart(self):
        if self._autostart_after_id:
            try:
                self.after_cancel(self._autostart_after_id)
            except Exception:
                pass
            self._autostart_after_id = None

    def _schedule_autostart(self):
        # Delay autostart so users can change options; if they touch options, it becomes manual.
        def maybe_start():
            self._autostart_after_id = None
            if self._options_touched:
                return
            self._start_processing()

        self._autostart_after_id = self.after(600, maybe_start)

    def _on_ai_vision_toggle(self):
        self._on_options_changed()
        if not self.use_ai_vision_var.get() and not self.use_ai_docs_var.get():
            self._ai_state_label.configure(text="")
            return
        if not self.ai_manager:
            self._ai_state_label.configure(text="AI not available.")
            return
        if getattr(self.ai_manager, "is_ready", False):
            self._ai_state_label.configure(text="AI ready.")
            return

        # Auto-load model when the user enables vision.
        if getattr(self.ai_manager, "is_loading", False):
            self._ai_state_label.configure(text="Loading AI model…")
            return

        self._ai_state_label.configure(text="Loading AI model…")

        def cb(msg: str, frac: float):
            try:
                self.after(0, lambda: self._ai_state_label.configure(text=msg))
            except Exception:
                pass

        try:
            self.ai_manager.load_model_async(progress_callback=cb)
        except Exception:
            pass

    def _start_processing(self):
        """Start processing in background"""
        if self.processing:
            return

        # If user requested AI vision but model isn't ready yet, wait briefly.
        if (self.use_ai_vision_var.get() or self.use_ai_docs_var.get()) and self.ai_manager and not getattr(self.ai_manager, "is_ready", False):
            self.subtitle.configure(text="Loading AI model… (will auto-start)")
            self._ai_state_label.configure(text="Loading AI model…")

            def poll():
                if self.cancelled or not self.winfo_exists():
                    return
                if getattr(self.ai_manager, "is_ready", False):
                    self._ai_state_label.configure(text="AI ready.")
                    self._start_processing()
                    return
                self.after(250, poll)

            self.after(250, poll)
            return

        self.processing = True
        self._results_stale = False
        try:
            self.apply_btn.configure(state="disabled")
            self.move_checkbox.configure(state="disabled")
        except Exception:
            pass
        self.start_btn.configure(state="disabled")
        thread = threading.Thread(target=self._process_files, daemon=True)
        thread.start()

    def _process_files(self):
        """Process files - Enhanced categorization with 51 categories (runs in background thread)"""
        last_update = [0]  # Track last update to throttle UI updates

        def progress_callback(message, progress, current, total):
            # Don't update if dialog was closed
            if self.cancelled or not self.winfo_exists():
                return

            # Throttle updates - only update every 10 files or at 100%
            if current - last_update[0] < 10 and progress < 1.0:
                return

            last_update[0] = current

            try:
                # Schedule UI update on main thread (throttled)
                self.after(0, lambda m=message, p=progress, c=current, t=total: self._update_progress(m, p, c, t))
            except Exception:
                pass  # Ignore if dialog closed

        try:
            # Enhanced categorization with 51 categories
            # Supports subfolder recursion
            self.categorized = self.enhanced_categorizer.categorize_folder(
                self.folder_path,
                include_subfolders=self.include_subfolders,
                progress_callback=progress_callback,
                cancel_check=lambda: bool(self.cancelled),
                use_ai_vision=bool(self.use_ai_vision_var.get()),
                smart_scope=bool(self.smart_scope_var.get()),
                include_other=bool(self.include_other_var.get()),
                use_ai_documents=bool(self.use_ai_docs_var.get()),
                max_ai_documents=40,
            )
        except Exception as e:
            print(f"Categorization error: {e}")
            import traceback
            traceback.print_exc()
            self.categorized = {}

        # Show results only if dialog still exists
        # Schedule on main thread
        if not self.cancelled and self.winfo_exists():
            self.after(0, self._show_results)

    def _update_progress(self, message: str, progress: float, current: int, total: int):
        """Update progress bar - safe from threading errors"""
        if self.cancelled or not self.winfo_exists():
            return
        try:
            self.subtitle.configure(text=f"{message} ({current}/{total})")
            self.progress.set(progress)
        except Exception:
            pass  # Dialog was closed

    def _show_results(self):
        """Display categorization results"""
        self.processing = False
        if self.cancelled:
            self.subtitle.configure(text="Cancelled")
            self.progress.set(0.0)
            return

        self.subtitle.configure(text="Analysis complete")
        self.progress.set(1.0)

        if not self.categorized:
            no_results = ctk.CTkLabel(
                self.results_frame,
                text="No files were categorized",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color="gray"
            )
            no_results.pack(pady=50)
            self.cancel_btn.configure(state="normal")
            self.start_btn.configure(state="normal", text="Re-run")
            return

        # Display categories
        total_items = sum(len(items) for items in self.categorized.values())
        file_items = 0
        empty_folder_count = 0
        try:
            for cat, items in self.categorized.items():
                for p in items:
                    if hasattr(p, "is_file") and p.is_file():
                        file_items += 1
                    elif cat == "empty_folders":
                        empty_folder_count += 1
        except Exception:
            file_items = total_items

        summary = ctk.CTkLabel(
            self.results_frame,
            text=f"Found {file_items} files in {len(self.categorized)} categories"
                 + (f"  •  Empty folders: {empty_folder_count}" if empty_folder_count else ""),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        )
        summary.pack(pady=(10, 20))

        self._refresh_summary_text()

        # Show each category with checkbox
        for category, files in sorted(self.categorized.items()):
            category_frame = ctk.CTkFrame(self.results_frame, fg_color="#2b2b2b", corner_radius=8)
            category_frame.pack(fill="x", pady=5, padx=5)

            # Header with checkbox
            header_frame = ctk.CTkFrame(category_frame, fg_color="transparent")
            header_frame.pack(fill="x", padx=10, pady=(10, 5))

            # Checkbox for this category
            default_checked = category not in {"empty_folders", "ignored_projects", "other"}
            checkbox_var = ctk.BooleanVar(value=default_checked)
            self.category_checkboxes[category] = checkbox_var

            checkbox = ctk.CTkCheckBox(
                header_frame,
                text="",
                variable=checkbox_var,
                width=20,
                checkbox_width=20,
                checkbox_height=20
            )
            checkbox.pack(side="left", padx=(0, 10))

            # Category header
            folder_name = self.enhanced_categorizer.get_category_folder(category)
            header = ctk.CTkLabel(
                header_frame,
                text=f"📁 {folder_name} ({len(files)} files)",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                anchor="w"
            )
            header.pack(side="left", fill="x", expand=True)

            # Add tooltip to checkbox
            ToolTipHelper.add_tooltip(
                checkbox,
                f"Include/exclude this category from organization"
            )

            # File list (show first 10)
            files_text = ", ".join(f.name for f in files[:10])
            if len(files) > 10:
                files_text += f" ... and {len(files) - 10} more"

            files_label = ctk.CTkLabel(
                category_frame,
                text=files_text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="gray",
                anchor="w",
                wraplength=620
            )
            files_label.pack(anchor="w", padx=40, pady=(0, 10))

        # Enable controls
        self.move_checkbox.configure(state="normal")
        self.cancel_btn.configure(state="normal")
        self.apply_btn.configure(state="normal")
        self.start_btn.configure(state="normal", text="Re-run")
        self._update_undo_button()

    def _toggle_summary(self):
        is_open = bool(self.summary_open_var.get())
        self.summary_open_var.set(not is_open)
        if not is_open:
            self.summary_btn.configure(text="Summary ▴")
            self.summary_body.grid()
            self._refresh_summary_text()
        else:
            self.summary_btn.configure(text="Summary ▾")
            self.summary_body.grid_remove()

    def _refresh_summary_text(self):
        try:
            dec = getattr(self.enhanced_categorizer, "last_decisions", {}) or {}
        except Exception:
            dec = {}

        total_files = 0
        skipped_unknown = 0
        ignored_projects = 0
        empty_files = 0
        empty_folders = 0

        for k, d in dec.items():
            cat = getattr(d, "category", "")
            if cat == "other":
                skipped_unknown += 1
            elif cat == "ignored_projects":
                ignored_projects += 1
            elif cat == "empty_files":
                empty_files += 1
            elif cat == "empty_folders":
                empty_folders += 1
            else:
                total_files += 1

        txt = (
            f"Scanned: {total_files + skipped_unknown} files\n"
            f"Categorized: {total_files} files\n"
            f"Unknown (left in place): {skipped_unknown} files\n"
            f"Ignored project folders: {ignored_projects}\n"
            f"Empty files: {empty_files}   •   Empty folders: {empty_folders}"
        )
        try:
            self.summary_text.configure(text=txt)
        except Exception:
            pass

    def _export_report(self):
        if not self.categorized:
            return

        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Auto-Categorize Report",
            defaultextension=".json",
            filetypes=[("JSON report", "*.json")],
            initialfile="fylorra_categorize_report.json",
        )
        if not save_path:
            return

        dec = getattr(self.enhanced_categorizer, "last_decisions", {}) or {}

        by_cat: dict[str, dict] = {}
        for cat, items in self.categorized.items():
            confidences: list[float] = []
            sample: list[str] = []
            for p in items[:50]:
                try:
                    d = dec.get(str(p))
                    if d is not None:
                        confidences.append(float(getattr(d, "confidence", 0.0)))
                    if len(sample) < 10:
                        sample.append(str(getattr(p, "name", p)))
                except Exception:
                    continue
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
            by_cat[cat] = {"count": len(items), "avg_confidence": round(avg_conf, 3), "sample": sample}

        ignored = [str(p) for p in self.categorized.get("ignored_projects", [])]
        empties = [str(p) for p in self.categorized.get("empty_folders", [])]

        report = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "folder": str(self.folder_path),
            "options": {
                "include_subfolders": bool(self.include_subfolders),
                "smart_scope": bool(self.smart_scope_var.get()),
                "include_other": bool(self.include_other_var.get()),
                "use_ai_vision_images": bool(self.use_ai_vision_var.get()),
                "use_ai_documents_pdfs": bool(self.use_ai_docs_var.get()),
            },
            "counts": {
                "categories": len(self.categorized),
                "ignored_projects": len(ignored),
                "empty_folders": len(empties),
            },
            "by_category": by_cat,
            "ignored_projects_list": ignored[:500],
            "empty_folders_list": empties[:500],
        }

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.subtitle.configure(text=f"Report exported: {save_path}")
        except Exception as e:
            from tkinter import messagebox

            messagebox.showerror("Export failed", str(e), parent=self)

    def _auto_select_by_confidence(self):
        if not self.categorized:
            return
        threshold = float(self.conf_threshold.get())
        dec = getattr(self.enhanced_categorizer, "last_decisions", {}) or {}

        for cat, items in self.categorized.items():
            var = self.category_checkboxes.get(cat)
            if var is None:
                continue
            if cat in {"empty_folders", "ignored_projects", "other"}:
                var.set(False)
                continue
            confidences: list[float] = []
            for p in items:
                d = dec.get(str(p))
                if d is None:
                    continue
                try:
                    confidences.append(float(getattr(d, "confidence", 0.0)))
                except Exception:
                    pass
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
            var.set(avg_conf >= threshold)

    def _apply_organization(self):
        """Apply the categorization"""
        if self._results_stale:
            from tkinter import messagebox
            messagebox.showwarning(
                "Results out of date",
                "Options were changed after the last scan.\n\nClick 'Re-run' to update results before applying.",
                parent=self,
            )
            return
        if not self.move_files_var.get():
            from tkinter import messagebox
            messagebox.showwarning(
                "Preview Mode",
                "Check 'Move files to category folders' to apply changes"
            )
            return

        # Disable controls
        self.apply_btn.configure(state="disabled")
        self.move_checkbox.configure(state="disabled")

        # Show progress
        self.subtitle.configure(text="Organizing files...")
        self.progress.set(0)

        # Organize in background
        def organize():
            import shutil
            moved_count = 0
            undo_operations = []

            for category, files in self.categorized.items():
                # Check if this category is selected
                if category not in self.category_checkboxes or not self.category_checkboxes[category].get():
                    continue  # Skip unchecked categories

                # Get target folder
                target_folder = self.folder_path / self.enhanced_categorizer.get_category_folder(category)

                # Create folder
                target_folder.mkdir(parents=True, exist_ok=True)

                # Move files
                for file_path in files:
                    try:
                        if not file_path.is_file():
                            continue
                        target_path = target_folder / file_path.name

                        # Handle duplicates
                        if target_path.exists():
                            stem = file_path.stem
                            suffix = file_path.suffix
                            counter = 1
                            while target_path.exists():
                                target_path = target_folder / f"{stem}_{counter}{suffix}"
                                counter += 1

                        # Move file
                        shutil.move(str(file_path), str(target_path))
                        moved_count += 1

                        # Record for undo
                        undo_operations.append(
                            FileOperation(
                                operation_type=OperationType.MOVE,
                                source_path=str(file_path),
                                destination_path=str(target_path),
                                original_content=None,
                                timestamp=datetime.now().isoformat(),
                                success=True,
                                metadata={'category': category}
                            )
                        )
                    except Exception as e:
                        print(f"Error moving {file_path}: {e}")
                        undo_operations.append(
                            FileOperation(
                                operation_type=OperationType.MOVE,
                                source_path=str(file_path),
                                destination_path=str(target_path),
                                original_content=None,
                                timestamp=datetime.now().isoformat(),
                                success=False,
                                error_message=str(e)
                            )
                        )
            
            # Save to undo history
            if undo_operations:
                undo_manager = get_undo_manager()
                transaction_id = undo_manager.create_transaction(
                    undo_operations,
                    OperationType.BULK_MOVE,
                    f"Auto-Categorize: {moved_count} files",
                    metadata={'folder': str(self.folder_path)}
                )
                self._last_transaction_id = transaction_id
            
            self.after(0, lambda: self._organization_complete(moved_count, undo_operations))

        thread = threading.Thread(target=organize, daemon=True)
        thread.start()

    def _organization_complete(self, moved_count: int, undo_operations: List = None):
        """Called when organization is complete"""
        status_text = f"Organization complete - {moved_count} files moved"
        if undo_operations:
            status_text += "\n💡 You can undo this operation for 30 days"
        self.subtitle.configure(text=status_text)
        self.progress.set(1.0)
        self._update_undo_button()

        from tkinter import messagebox
        messagebox.showinfo(
            "Organization Complete",
            f"Successfully organized {moved_count} files into category folders!"
            ,
            parent=self
        )

        # Keep the dialog open so the user can Undo.
        try:
            self.apply_btn.configure(state="disabled")
        except Exception:
            pass

    def _close(self):
        """Close dialog"""
        self.cancelled = True
        self.destroy()

    def _update_undo_button(self):
        """Update undo button state based on history"""
        try:
            recent = get_undo_manager().get_recent_transactions(limit=1)
            if recent and recent[0].can_undo:
                self.undo_btn.configure(
                    state="normal",
                    text=f"⏮️ Undo ({recent[0].success_count})"
                )
            else:
                self.undo_btn.configure(state="disabled", text="⏮️ Undo")
        except Exception:
            self.undo_btn.configure(state="disabled", text="⏮️ Undo")

    def _undo_last_operation(self):
        """Undo the most recent categorization operation"""
        from tkinter import messagebox

        try:
            recent = get_undo_manager().get_recent_transactions(limit=1)

            if not recent:
                messagebox.showinfo("No History", "No categorization operations to undo.")
                return

            transaction = recent[0]
            if not transaction.can_undo:
                messagebox.showinfo("Already Undone", "The most recent operation has already been undone.")
                return

            # Confirm undo
            result = messagebox.askyesno(
                "Confirm Undo",
                f"Undo categorization of {transaction.success_count} files?\n\n"
                f"Operation: {transaction.description}\n"
                f"Date: {transaction.timestamp}\n\n"
                f"This will move files back to their original locations."
            )

            if result:
                # Perform undo
                success, message, reversed_count = get_undo_manager().undo_transaction(transaction.transaction_id)

                if success:
                    messagebox.showinfo(
                        "Undo Complete",
                        f"Successfully undone {reversed_count} file moves",
                        parent=self
                    )
                    self._update_undo_button()
                    try:
                        self.apply_btn.configure(state="normal")
                    except Exception:
                        pass
                else:
                    messagebox.showerror("Undo Failed", f"Could not undo operation:\n\n{message}", parent=self)

        except Exception as e:
            messagebox.showerror("Error", f"Undo failed:\n{e}", parent=self)
