"""
Fylorra - Smart Rename Assistant
AI-powered file renaming with preview and approval
"""

import customtkinter as ctk
from pathlib import Path
from typing import Optional, List, Dict, Callable
import threading
from collections import deque
import tkinter as tk
from tkinter import TclError, ttk
from utils.png_icons import PNGIconLoader
from utils.tooltip import ToolTipHelper
from core.bulk_ai_processor import BulkAIProcessor, ProcessingOptions, ProcessingMode
from utils.intelligent_rename import (
    sanitize_ai_filename, get_unique_filename,
    learn_folder_patterns, apply_learned_pattern
)
from utils.universal_undo import get_undo_manager, FileOperation, OperationType
from datetime import datetime


class SmartRenameDialog(ctk.CTkToplevel):
    """Dialog for previewing and approving AI-suggested file renames"""

    def __init__(self, parent, ai_manager, files: List[Path], on_complete: Optional[Callable] = None,
                 folder_mode: bool = False, folder_path: Optional[Path] = None):
        super().__init__(parent)

        self.ai_manager = ai_manager
        self.files = files  # Initial files (may be expanded from folder scan)
        self.on_complete = on_complete
        self.icon_loader = PNGIconLoader()
        self.folder_mode = folder_mode  # True if launched from folder context
        self.folder_path = folder_path  # Root folder for bulk operations
        self.bulk_processor = BulkAIProcessor(ai_manager)

        # Results: {file_path: {"suggested": name, "approved": bool, "edited": name}}
        self.results: Dict[Path, Dict] = {}
        self.processing = False
        self.cancelled = False
        self._closed = False
        self._after_ids: set[str] = set()
        self._ui_queue: deque[tuple[int, Path]] = deque()
        self._ui_queue_lock = threading.Lock()
        self._ui_pump_scheduled = False
        self._processing_finished = False
        self._run_token = 0
        self._restart_after_id: Optional[str] = None
        self._iid_by_path: Dict[Path, str] = {}
        self._path_by_iid: Dict[str, Path] = {}
        self._edit_entry: Optional[tk.Entry] = None
        self._editing_iid: Optional[str] = None
        self._last_transaction_id: Optional[int] = None

        self.title("Smart Rename - Fast Cleanup")
        self.geometry("900x700")
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.winfo_screenheight() // 2) - (700 // 2)
        self.geometry(f"900x700+{x}+{y}")

        self._create_ui()

        # Stop background updates when the dialog is closed
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Destroy>", self._on_destroy, add=True)

        # Start processing after dialog is rendered (non-blocking delay)
        self._safe_after(100, self._start_processing)

    def _is_alive(self) -> bool:
        try:
            return (not self._closed) and bool(self.winfo_exists())
        except TclError:
            return False

    def _safe_after(self, delay_ms: int, func) -> Optional[str]:
        """Schedule a UI callback only if the window still exists."""
        if not self._is_alive():
            return None

        after_id_holder: dict[str, str] = {}

        def runner():
            after_id = after_id_holder.get("id")
            if after_id:
                self._after_ids.discard(after_id)

            if not self._is_alive():
                return

            try:
                func()
            except TclError:
                pass

        try:
            after_id = self.after(delay_ms, runner)
        except TclError:
            return None

        after_id_holder["id"] = after_id
        self._after_ids.add(after_id)
        return after_id

    def _enqueue_ui_row(self, file_path: Path, *, token: Optional[int] = None):
        """Queue a file row for UI creation (prevents freezing with large batches)."""
        token = self._run_token if token is None else int(token)
        with self._ui_queue_lock:
            self._ui_queue.append((token, file_path))
            should_schedule = not self._ui_pump_scheduled
            if should_schedule:
                self._ui_pump_scheduled = True

        if should_schedule:
            self._safe_after(0, self._drain_ui_queue)

    def _drain_ui_queue(self):
        """Create UI rows in small batches to keep the UI responsive."""
        if not self._is_alive():
            return

        batch: list[Path] = []
        token = self._run_token
        with self._ui_queue_lock:
            self._ui_pump_scheduled = False
            batch_size = 50
            while self._ui_queue and len(batch) < batch_size:
                t, fp = self._ui_queue.popleft()
                if t == token:
                    batch.append(fp)
            has_more = bool(self._ui_queue)

        for fp in batch:
            self._add_file_row(fp)

        self._update_showing_label()

        if has_more and not self.cancelled:
            with self._ui_queue_lock:
                if not self._ui_pump_scheduled:
                    self._ui_pump_scheduled = True
            self._safe_after(10, self._drain_ui_queue)
            return

        if self._processing_finished and not self.cancelled:
            self._processing_complete()

    def _update_showing_label(self):
        if not self._is_alive():
            return
        with self._ui_queue_lock:
            queued = sum(1 for t, _fp in self._ui_queue if t == self._run_token)
        total = len(self.files)
        processed = len(self.results)
        suffix = f" (queued UI: {queued})" if queued else ""
        try:
            self.showing_label.configure(text=f"Processed {processed} of {total}{suffix}")
        except Exception:
            pass

    def _on_tree_click(self, event):
        if not self._is_alive():
            return

        try:
            region = self.tree.identify("region", event.x, event.y)
            if region != "cell":
                return
            column = self.tree.identify_column(event.x)
            iid = self.tree.identify_row(event.y)
        except Exception:
            return

        if not iid or column != "#1":
            return

        file_path = self._path_by_iid.get(iid)
        if not file_path:
            return

        current = bool(self.results.get(file_path, {}).get("approved", False))
        self.results[file_path]["approved"] = not current
        self._add_file_row(file_path)

    def _on_tree_double_click(self, event):
        if not self._is_alive():
            return

        try:
            column = self.tree.identify_column(event.x)
            iid = self.tree.identify_row(event.y)
            if not iid or column != "#3":
                return
        except Exception:
            return

        file_path = self._path_by_iid.get(iid)
        if not file_path:
            return

        try:
            bbox = self.tree.bbox(iid, "suggested")
        except Exception:
            return
        if not bbox:
            return

        x, y, w, h = bbox
        value = self.results.get(file_path, {}).get("edited") or self.results.get(file_path, {}).get("suggested") or ""

        self._cancel_tree_edit()

        entry = tk.Entry(self.tree)
        entry.insert(0, str(value))
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        self._edit_entry = entry
        self._editing_iid = iid

        entry.bind("<Return>", lambda _e: self._commit_tree_edit(), add=True)
        entry.bind("<FocusOut>", lambda _e: self._commit_tree_edit(), add=True)
        entry.bind("<Escape>", lambda _e: self._cancel_tree_edit(), add=True)

    def _commit_tree_edit(self):
        if not self._is_alive():
            return
        if self._edit_entry is None or self._editing_iid is None:
            return

        iid = self._editing_iid
        file_path = self._path_by_iid.get(iid)
        if not file_path:
            self._cancel_tree_edit()
            return

        text = self._edit_entry.get().strip()
        if file_path.suffix and text.lower().endswith(file_path.suffix.lower()):
            text = text[: -len(file_path.suffix)].strip()
        if text:
            self.results[file_path]["edited"] = text

        self._cancel_tree_edit()
        self._add_file_row(file_path)

    def _cancel_tree_edit(self):
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except Exception:
                pass
        self._edit_entry = None
        self._editing_iid = None

    def _on_destroy(self, _event=None):
        if self._closed:
            return
        self._closed = True
        self.cancelled = True
        for after_id in list(self._after_ids):
            try:
                self.after_cancel(after_id)
            except TclError:
                pass
            finally:
                self._after_ids.discard(after_id)

    def _create_ui(self):
        """Create the dialog UI"""
        # Header with icon
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)

        # Icon
        ai_icon = self.icon_loader.load_icon("analytics", size=(32, 32))
        icon_label = ctk.CTkLabel(header_frame, image=ai_icon, text="")
        icon_label.image = ai_icon
        icon_label.place(x=0, y=9)

        # Title
        title = ctk.CTkLabel(
            header_frame,
            text="Smart Rename - AI Vision + Rules",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        )
        title.place(x=40, y=10)

        # Subtitle
        subtitle_text = f"Analyzing {len(self.files)} files with AI vision & smart rules..."
        if self.folder_mode and self.folder_path:
            subtitle_text = f"Folder: {self.folder_path.name}"

        self.subtitle = ctk.CTkLabel(
            self,
            text=subtitle_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray"
        )
        self.subtitle.pack(pady=(0, 10))

        # Processing mode (keeps bulk runs fast by default)
        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(mode_frame, text="Mode:", font=ctk.CTkFont(family="Segoe UI", size=11)).pack(side="left", padx=(0, 8))
        self.mode_var = ctk.StringVar(value="Smart (balanced)")
        self.mode_dropdown = ctk.CTkOptionMenu(
            mode_frame,
            variable=self.mode_var,
            values=["Fast (rules only)", "Smart (balanced)", "Deep (AI vision)"],
            width=180,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=lambda _v=None: self._request_reprocess("mode"),
        )
        self.mode_dropdown.pack(side="left")
        ToolTipHelper.add_tooltip(
            self.mode_dropdown,
            "Fast: rules only. Smart: rules + doc analysis. Deep: AI vision for images (slow).",
        )

        # Bulk options (only in folder mode)
        if self.folder_mode and self.folder_path:
            options_frame = ctk.CTkFrame(self, fg_color="transparent")
            options_frame.pack(fill="x", padx=20, pady=(0, 10))

            # Subfolder option
            self.include_subfolders_var = ctk.BooleanVar(value=True)
            self.subfolders_checkbox = ctk.CTkCheckBox(
                options_frame,
                text="Include subfolders (recursive)",
                variable=self.include_subfolders_var,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                command=lambda: self._request_reprocess("subfolders"),
            )
            self.subfolders_checkbox.pack(side="left", padx=(0, 20))
            ToolTipHelper.add_tooltip(
                self.subfolders_checkbox,
                "Search all subfolders recursively for files to rename"
            )

            # File type filter
            filter_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
            filter_frame.pack(side="left")

            ctk.CTkLabel(
                filter_frame,
                text="Filter:",
                font=ctk.CTkFont(family="Segoe UI", size=11)
            ).pack(side="left", padx=(0, 5))

            self.filter_var = ctk.StringVar(value="All Files")
            self.filter_dropdown = ctk.CTkOptionMenu(
                filter_frame,
                variable=self.filter_var,
                values=["All Files", "Images Only", "Videos Only", "Documents Only", "Code Files Only"],
                width=150,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                command=lambda _v=None: self._request_reprocess("filter"),
            )
            self.filter_dropdown.pack(side="left")
            ToolTipHelper.add_tooltip(
                self.filter_dropdown,
                "Filter files by type before processing"
            )

        # Progress bar
        self.progress = ctk.CTkProgressBar(self, width=860)
        self.progress.pack(padx=20, pady=(0, 20))
        self.progress.set(0)

        tree_container = ctk.CTkFrame(self, corner_radius=10, fg_color="#1b1b1b")
        tree_container.pack(padx=20, pady=(0, 20), fill="both", expand=True)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        tree_bg = "#1b1b1b"
        row_bg_even = "#1e1e1e"
        row_bg_odd = "#232323"
        grid_color = "#3a3a3a"
        text_color = "#f0f0f0"
        sel_bg = "#2b5d8a"

        style.configure(
            "SmartRename.Treeview",
            background=row_bg_even,
            fieldbackground=tree_bg,
            foreground=text_color,
            bordercolor=grid_color,
            lightcolor=grid_color,
            darkcolor=grid_color,
            rowheight=26,
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 11),
        )
        style.map(
            "SmartRename.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "SmartRename.Treeview.Heading",
            background="#2a2a2a",
            foreground="#ffffff",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "SmartRename.Treeview.Heading",
            background=[("active", "#333333")],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "SmartRename.Vertical.TScrollbar",
            background=tree_bg,
            troughcolor=tree_bg,
            bordercolor=grid_color,
            lightcolor=grid_color,
            darkcolor=grid_color,
            arrowsize=12,
        )
        style.map("SmartRename.Vertical.TScrollbar", background=[("active", "#2a2a2a")])

        self.tree = ttk.Treeview(
            tree_container,
            columns=("approved", "original", "suggested"),
            show="headings",
            selectmode="browse",
            style="SmartRename.Treeview",
        )
        self.tree.heading("approved", text="✓")
        self.tree.heading("original", text="Original")
        self.tree.heading("suggested", text="New Name")
        self.tree.column("approved", width=40, anchor="center", stretch=False)
        self.tree.column("original", width=360, anchor="w", stretch=True)
        self.tree.column("suggested", width=420, anchor="w", stretch=True)

        self.tree.tag_configure("even", background=row_bg_even, foreground=text_color)
        self.tree.tag_configure("odd", background=row_bg_odd, foreground=text_color)
        self.tree.tag_configure("error", foreground="#ff6b6b")

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview, style="SmartRename.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Button-1>", self._on_tree_click, add=True)
        self.tree.bind("<Double-1>", self._on_tree_double_click, add=True)

        # Bottom controls
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Left side - select all/none
        left_controls = ctk.CTkFrame(controls_frame, fg_color="transparent")
        left_controls.pack(side="left")

        self.select_all_btn = ctk.CTkButton(
            left_controls,
            text="Select All",
            width=100,
            command=self._select_all,
            state="disabled"
        )
        self.select_all_btn.pack(side="left", padx=(0, 10))

        self.select_none_btn = ctk.CTkButton(
            left_controls,
            text="Select None",
            width=100,
            command=self._select_none,
            state="disabled"
        )
        self.select_none_btn.pack(side="left")

        # Right side - undo/apply/cancel
        right_controls = ctk.CTkFrame(controls_frame, fg_color="transparent")
        right_controls.pack(side="right")

        # Undo button
        self.undo_btn = ctk.CTkButton(
            right_controls,
            text="⏮️ Undo",
            width=100,
            command=self._undo_last_rename,
            fg_color="gray"
        )
        self.undo_btn.pack(side="left", padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            right_controls,
            text="Cancel",
            width=100,
            command=self._cancel,
            fg_color="gray"
        )
        self.cancel_btn.pack(side="left", padx=(0, 10))

        self.apply_btn = ctk.CTkButton(
            right_controls,
            text="Apply Renames",
            width=120,
            command=self._apply_renames,
            state="disabled"
        )
        self.apply_btn.pack(side="left")

        # Add tooltips to buttons
        ToolTipHelper.add_tooltips_batch({
            self.select_all_btn: "Select all files for renaming",
            self.select_none_btn: "Deselect all files",
            self.cancel_btn: "cancel_operation",
            self.apply_btn: "apply_changes"
        })

        self.showing_label = ctk.CTkLabel(
            controls_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray",
        )
        self.showing_label.pack(side="bottom", pady=(10, 0))

    def _start_processing(self):
        """Start processing files in background"""
        if not self._is_alive():
            return

        # If folder mode, scan for files first
        if self.folder_mode and self.folder_path:
            self._scan_folder_and_process()
        else:
            self._begin_processing()

    def _scan_folder_and_process(self):
        """Scan folder for files based on options, then process"""
        if not self._is_alive():
            return

        # Get filter extensions
        filter_choice = self.filter_var.get()
        file_extensions = None  # None = all files

        if filter_choice == "Images Only":
            file_extensions = BulkAIProcessor.get_image_extensions()
        elif filter_choice == "Videos Only":
            file_extensions = BulkAIProcessor.get_video_extensions()
        elif filter_choice == "Documents Only":
            file_extensions = BulkAIProcessor.get_document_extensions()
        elif filter_choice == "Code Files Only":
            file_extensions = BulkAIProcessor.get_code_extensions()

        mode_choice = (self.mode_var.get() or "").strip()
        mode = ProcessingMode.SMART
        if mode_choice.startswith("Fast"):
            mode = ProcessingMode.FAST
        elif mode_choice.startswith("Deep"):
            mode = ProcessingMode.DEEP

        # Create processing options
        options = ProcessingOptions(
            include_subfolders=self.include_subfolders_var.get(),
            file_extensions=file_extensions,
            batch_size=50,
            mode=mode
        )

        token = self._run_token

        # Show scanning message
        self.subtitle.configure(text="Scanning folder...")

        # Scan in background thread
        def scan_thread(run_token: int):
            files = self.bulk_processor.scan_folder(self.folder_path, options)

            if not self._is_alive():
                return
            if run_token != self._run_token:
                return

            # Update files list
            self.files = files

            # Update UI on main thread
            self._safe_after(0, lambda: self._on_scan_complete(len(files)))

        threading.Thread(target=lambda: scan_thread(token), daemon=True).start()

    def _on_scan_complete(self, file_count: int):
        """Called when folder scan completes"""
        if not self._is_alive():
            return

        if file_count == 0:
            self.subtitle.configure(text="No files found matching criteria")
            self.cancel_btn.configure(state="normal")
            return

        # Update subtitle
        self.subtitle.configure(text=f"Found {file_count} files - starting analysis...")

        # Start processing
        self._begin_processing()

    def _begin_processing(self):
        """Begin processing the files list"""
        if not self._is_alive():
            return

        self._run_token += 1
        self.processing = True
        self._processing_finished = False
        with self._ui_queue_lock:
            self._ui_queue.clear()
            self._ui_pump_scheduled = False
        self._iid_by_path.clear()
        self._path_by_iid.clear()
        try:
            for iid in self.tree.get_children():
                self.tree.delete(iid)
        except Exception:
            pass
        self._update_showing_label()
        token = self._run_token
        self._worker_thread = threading.Thread(target=lambda: self._process_files(token), daemon=True)
        self._worker_thread.start()

    def _process_files(self, token: int):
        """Process each file with AI (runs in background thread - non-blocking)"""
        total = len(self.files)

        mode_choice = (self.mode_var.get() or "").strip()
        deep_mode = mode_choice.startswith("Deep")
        smart_mode = mode_choice.startswith("Smart")

        # Count image files for warning
        image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        image_count = sum(1 for f in self.files if f.suffix.lower() in image_exts)

        # Warn if many images and Deep (vision) is enabled.
        if deep_mode and image_count > 10:
            self._safe_after(0, lambda: self._warn_slow_processing(image_count))

        for idx, file_path in enumerate(self.files):
            if self.cancelled or token != self._run_token:
                break

            # Throttle progress updates - only update every 5 files or at completion
            if idx % 5 == 0 or idx == total - 1:
                progress = (idx + 1) / total
                self._safe_after(0, lambda p=progress, i=idx: self._update_progress(p, i + 1, total))

            # Determine if we should use AI vision
            ext = file_path.suffix.lower()
            use_ai_vision = False

            # AI vision for images only in Deep mode (keeps bulk runs fast by default).
            if deep_mode and ext in image_exts and bool(self.ai_manager and getattr(self.ai_manager, "is_ready", False)):
                use_ai_vision = True
            # Use AI analysis for documents
            elif ext in ['.pdf', '.docx', '.doc']:
                # For documents, use semantic analysis in Smart/Deep modes if available.
                if (smart_mode or deep_mode) and bool(self.ai_manager and getattr(self.ai_manager, "is_ready", False)):
                    try:
                        result = self.ai_manager.analyze_document(file_path)
                        if result and result.suggested_filename:
                            suggested_name = result.suggested_filename
                            # Store result
                            self.results[file_path] = {
                                "suggested": suggested_name,
                                "approved": True,
                                "edited": suggested_name
                            }
                            # Add to UI on main thread
                            self._enqueue_ui_row(file_path, token=token)
                            continue
                    except Exception as e:
                        print(f"Document analysis failed: {e}")

            # In Fast mode, avoid AI entirely (just clean up names).
            if mode_choice.startswith("Fast"):
                suggested_name = self.ai_manager.analyze_file_for_rename(file_path, use_ai=False)
                if suggested_name:
                      self.results[file_path] = {
                          "suggested": suggested_name,
                          "approved": True,
                          "edited": suggested_name,
                          "used_ai": False,
                      }
                      self._enqueue_ui_row(file_path, token=token)
                      continue

            # Analyze file (with AI vision for images if enabled)
            suggested_name = self.ai_manager.analyze_file_for_rename(file_path, use_ai=use_ai_vision)

            # If vision produced nothing, fall back to fast cleanup so the UI still shows a suggestion.
            if (not suggested_name) and use_ai_vision:
                suggested_name = self.ai_manager.analyze_file_for_rename(file_path, use_ai=False)

            if suggested_name:
                # Store result with metadata about AI usage
                self.results[file_path] = {
                    "suggested": suggested_name,
                    "approved": True,  # Auto-approve by default
                    "edited": suggested_name,
                    "used_ai": use_ai_vision  # Track if AI was used
                }

                # Add to UI on main thread
                self._enqueue_ui_row(file_path, token=token)
            else:
                # Still show a row so the user can manually type a name.
                fallback_name = file_path.stem or "untitled"
                self.results[file_path] = {
                    "suggested": fallback_name,
                    "approved": False,
                    "edited": fallback_name,
                    "used_ai": use_ai_vision,
                    "error": "No suggestion from AI"
                }
                self._enqueue_ui_row(file_path, token=token)

        # Mark finished; UI completion will run once queued rows are drained.
        if token == self._run_token:
            self._processing_finished = True
        if not self.cancelled and token == self._run_token:
            self._safe_after(0, self._drain_ui_queue)

    def _warn_slow_processing(self, image_count):
        """Warn user about slow AI vision processing"""
        if not self._is_alive():
            return
        self.subtitle.configure(
            text=f"⚠️ Processing {image_count} images with AI vision - this may take several minutes!",
            text_color="#FF9800"
        )

    def _request_reprocess(self, reason: str = ""):
        """
        Re-run analysis when the user changes mode/options.
        Debounced to avoid restarting repeatedly while the user clicks around.
        """
        if not self._is_alive() or self.cancelled:
            return

        if self._restart_after_id:
            try:
                self.after_cancel(self._restart_after_id)
            except Exception:
                pass
            self._restart_after_id = None

        def do_restart():
            self._restart_after_id = None
            if not self._is_alive() or self.cancelled:
                return

            # Abort current run (threads will stop due to token mismatch).
            self._run_token += 1
            self._processing_finished = False
            self.processing = False
            self.results = {}
            try:
                self.progress.set(0.0)
            except Exception:
                pass
            try:
                self.subtitle.configure(text="Re-analyzing with new settings...")
            except Exception:
                pass
            try:
                for iid in self.tree.get_children():
                    self.tree.delete(iid)
            except Exception:
                pass
            self._iid_by_path.clear()
            self._path_by_iid.clear()
            with self._ui_queue_lock:
                self._ui_queue.clear()
                self._ui_pump_scheduled = False
            self._update_showing_label()

            try:
                self.apply_btn.configure(state="disabled")
                self.select_all_btn.configure(state="disabled")
                self.select_none_btn.configure(state="disabled")
            except Exception:
                pass

            # Start a fresh scan/process.
            self._start_processing()

        # Debounce a bit.
        self._restart_after_id = self._safe_after(250, do_restart)

    def _update_progress(self, value: float, current: int, total: int):
        """Update progress bar and subtitle"""
        if not self._is_alive():
            return
        self.progress.set(value)
        self.subtitle.configure(text=f"Processing {current}/{total} files...")

    def _add_file_row(self, file_path: Path):
        """Add or update a row in the results table"""
        if not self._is_alive():
            return

        result = self.results.get(file_path)
        if not result:
            return
        approved_symbol = "☑" if result.get("approved") else "☐"
        edited = (result.get("edited") or result.get("suggested") or "").strip()
        suggested_display = f"{edited}{file_path.suffix}"

        iid = self._iid_by_path.get(file_path)
        if iid is None:
            iid = str(len(self._iid_by_path) + 1)
            self._iid_by_path[file_path] = iid
            self._path_by_iid[iid] = file_path
            tags = ("even" if int(iid) % 2 == 0 else "odd",) + (("error",) if result.get("error") else tuple())
            try:
                self.tree.insert("", "end", iid=iid, values=(approved_symbol, file_path.name, suggested_display), tags=tags)
            except Exception:
                return
        else:
            tags = ("even" if int(iid) % 2 == 0 else "odd",) + (("error",) if result.get("error") else tuple())
            try:
                self.tree.item(iid, values=(approved_symbol, file_path.name, suggested_display), tags=tags)
            except Exception:
                return

    def _processing_complete(self):
        """Called when processing is complete"""
        if not self._is_alive():
            return
        self.processing = False
        approved_count = sum(1 for r in self.results.values() if r["approved"])

        self.subtitle.configure(text=f"Ready to rename {approved_count} of {len(self.results)} files")
        self.progress.set(1.0)
        self._update_showing_label()

        # Enable buttons
        self.select_all_btn.configure(state="normal")
        self.select_none_btn.configure(state="normal")
        self.apply_btn.configure(state="normal")
        self._update_undo_button()

    def _select_all(self):
        """Select all checkboxes"""
        if not self._is_alive():
            return
        for file_path, result in self.results.items():
            result["approved"] = True

        for iid, fp in self._path_by_iid.items():
            if fp in self.results:
                self._add_file_row(fp)

        approved_count = len(self.results)
        self.subtitle.configure(text=f"Ready to rename {approved_count} of {len(self.results)} files")

    def _select_none(self):
        """Deselect all checkboxes"""
        if not self._is_alive():
            return
        for file_path, result in self.results.items():
            result["approved"] = False

        for iid, fp in self._path_by_iid.items():
            if fp in self.results:
                self._add_file_row(fp)

        self.subtitle.configure(text=f"Ready to rename 0 of {len(self.results)} files")

    def _apply_renames(self):
        """Apply approved renames with intelligent validation and undo tracking"""
        renamed_count = 0
        errors = []
        undo_operations = []
        transaction_id: Optional[int] = None

        # Learn patterns from folder if available
        pattern_info = None
        if self.folder_path:
            pattern_info = learn_folder_patterns(self.folder_path)

        for file_path, result in self.results.items():
            if not result["approved"]:
                continue

            new_name = result["edited"].strip()
            if not new_name:
                continue

            # Sanitize the filename
            validation = sanitize_ai_filename(new_name, preserve_case=True)
            sanitized_name = validation.sanitized_name

            # Apply pattern if learned and confident
            if pattern_info and pattern_info['template'] and pattern_info['confidence'] > 0.5:
                # Try to extract AI analysis metadata if available
                ai_analysis = result.get('metadata', {})
                if ai_analysis:
                    suggested_name = apply_learned_pattern(
                        pattern_info['template'],
                        ai_analysis,
                        pattern_info['separator']
                    )
                    if suggested_name:
                        sanitized_name = suggested_name

            # Get unique name with smart duplicate handling
            final_name, dup_explanation = get_unique_filename(
                file_path,
                sanitized_name,
                ai_context={'new_analysis': result.get('metadata', {})}
            )

            # Build new path
            new_path = file_path.parent / f"{final_name}{file_path.suffix}"

            # Perform rename
            try:
                file_path.rename(new_path)
                renamed_count += 1

                # Record for undo
                undo_operations.append(
                    FileOperation(
                        operation_type=OperationType.RENAME,
                        source_path=str(file_path),
                        destination_path=str(new_path),
                        original_content=None,
                        timestamp=datetime.now().isoformat(),
                        success=True,
                        metadata={
                            'ai_suggested': result.get('suggested', ''),
                            'user_edited': result.get('edited', ''),
                            'pattern_applied': pattern_info['template'] if pattern_info else None,
                            'duplicate_handling': dup_explanation if final_name != sanitized_name else None
                        }
                    )
                )
            except Exception as e:
                errors.append(f"{file_path.name}: {str(e)}")
                undo_operations.append(
                    FileOperation(
                        operation_type=OperationType.RENAME,
                        source_path=str(file_path),
                        destination_path=str(new_path),
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
                OperationType.BULK_RENAME,
                f"Smart Rename: {renamed_count} files",
                metadata={
                    'folder': str(self.folder_path) if self.folder_path else None,
                    'pattern_used': pattern_info['template'] if pattern_info else None,
                    'total_approved': len([r for r in self.results.values() if r['approved']])
                }
              )

            self._last_transaction_id = transaction_id

        # Show results
        result_dialog = ctk.CTkToplevel(self)
        result_dialog.title("Smart Rename Complete")
        result_dialog.geometry("550x450")

        # Success message with transaction ID
        success_msg = f"✓ Successfully renamed {renamed_count} files"
        if undo_operations:
            success_msg += f"\n\n💾 Transaction ID: #{transaction_id}"
            success_msg += "\n💡 You can undo this rename for 30 days"

        ctk.CTkLabel(
            result_dialog,
            text=success_msg,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(pady=20)

        # Pattern info if applied
        if pattern_info and pattern_info['template']:
            pattern_label = ctk.CTkLabel(
                result_dialog,
                text=f"📋 Pattern applied: {pattern_info['template']} ({pattern_info['confidence']:.0%} confidence)",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="gray"
            )
            pattern_label.pack(pady=(0, 10))

        if errors:
            error_msg = "\n".join(errors[:10])  # Show first 10 errors
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"

            ctk.CTkLabel(
                result_dialog,
                text=f"⚠️ {len(errors)} errors occurred:",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#FF6B6B"
            ).pack(pady=(10, 5))

            error_text = ctk.CTkTextbox(result_dialog, width=500, height=200)
            error_text.pack(padx=20, pady=(0, 20))
            error_text.insert("1.0", error_msg)
            error_text.configure(state="disabled")

        btn_row = ctk.CTkFrame(result_dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=1)

        def _undo_now():
            if transaction_id is None:
                return
            try:
                ok, msg, reversed_count = get_undo_manager().undo_transaction(int(transaction_id))
            except Exception as e:
                ok, msg, reversed_count = False, str(e), 0
            from tkinter import messagebox
            if ok:
                messagebox.showinfo("Undo Complete", f"Successfully undone {reversed_count} renames.", parent=result_dialog)
                try:
                    result_dialog.destroy()
                except Exception:
                    pass
                self._update_undo_button()
                # Refresh preview to match reverted filenames.
                self._request_reprocess("undo")
            else:
                messagebox.showerror("Undo Failed", f"Could not undo rename:\n\n{msg}", parent=result_dialog)

        undo_btn = ctk.CTkButton(
            btn_row,
            text="⏮️ Undo Now",
            width=160,
            height=36,
            command=_undo_now,
            fg_color="#3d5a80",
            hover_color="#2d4a70",
        )
        if transaction_id is None:
            undo_btn.configure(state="disabled", fg_color="#424242", hover_color="#505050")
        undo_btn.grid(row=0, column=0, padx=(0, 10), sticky="w")

        ctk.CTkButton(
            btn_row,
            text="Undo History",
            width=160,
            height=36,
            command=lambda: self._open_undo_history(parent=result_dialog),
        ).grid(row=0, column=1, padx=10)

        ctk.CTkButton(
            btn_row,
            text="Close",
            width=160,
            height=36,
            fg_color="#424242",
            hover_color="#505050",
            command=result_dialog.destroy,
        ).grid(row=0, column=2, padx=(10, 0), sticky="e")

        # Callback (do not auto-close the main dialog; user may want to Undo)
        if self.on_complete:
            self.on_complete(renamed_count)
        try:
            self._update_undo_button()
        except Exception:
            pass
        try:
            # Disable apply until user re-runs analysis (prevents applying against stale paths).
            self.apply_btn.configure(state="disabled")
        except Exception:
            pass

    def _cancel(self):
        """Cancel processing and close"""
        self.cancelled = True
        try:
            self.destroy()
        except TclError:
            pass

    def _update_undo_button(self):
        """Update undo button state based on history"""
        try:
            recent = get_undo_manager().get_recent_transactions(limit=1)
            if recent and recent[0].can_undo:
                self.undo_btn.configure(state="normal", text=f"⏮️ Undo ({recent[0].success_count})")
            else:
                self.undo_btn.configure(state="disabled", text="⏮️ Undo")
        except Exception:
            self.undo_btn.configure(state="disabled", text="⏮️ Undo")

    def _undo_last_rename(self):
        """Undo the most recent rename transaction"""
        from tkinter import messagebox

        try:
            recent = get_undo_manager().get_recent_transactions(limit=1)

            if not recent:
                messagebox.showinfo("No History", "No rename operations to undo.")
                return

            transaction = recent[0]
            if not transaction.can_undo:
                messagebox.showinfo("Already Undone", "The most recent rename has already been undone.")
                return

            # Confirm undo
            result = messagebox.askyesno(
                "Confirm Undo",
                f"Undo rename of {transaction.success_count} files?\n\n"
                f"Operation: {transaction.description}\n"
                f"Date: {transaction.timestamp}\n\n"
                f"This will restore the original filenames."
            )

            if result:
                # Perform undo
                success, message, reversed_count = get_undo_manager().undo_transaction(transaction.transaction_id)

                if success:
                    messagebox.showinfo(
                        "Undo Complete",
                        f"Successfully undone {reversed_count} renames"
                    )
                    self._update_undo_button()
                    self._request_reprocess("undo")

                    # Callback if provided
                    if self.on_complete:
                        self.on_complete(reversed_count)
                else:
                    messagebox.showerror("Undo Failed", f"Could not undo rename:\n\n{message}")

        except Exception as e:
            messagebox.showerror("Error", f"Undo failed:\n{e}")

    def _open_undo_history(self, parent=None):
        try:
            from gui.undo_history_dialog import UndoHistoryDialog
            win = UndoHistoryDialog(parent or self)
            try:
                win.lift()
                win.attributes("-topmost", True)
                win.after(200, lambda: win.attributes("-topmost", False))
                win.focus_force()
            except Exception:
                pass
        except Exception:
            pass
