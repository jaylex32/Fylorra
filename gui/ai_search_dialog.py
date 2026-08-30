"""
Fylorra - AI Search Dialog
Local AI-assisted search over an indexed workspace.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.ai_search import ai_search
from core.filename_explainer import explain_filename
from core.library_index import LibraryIndex


class _AISearchUI:
    def _init_common(self, ai_manager=None):
        self.ai_manager = ai_manager
        self.library = LibraryIndex()
        self._index_thread = None
        self._search_thread = None

    def _top(self):
        try:
            return self.winfo_toplevel()
        except Exception:
            return self

    def _setup_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 10))

        title = ctk.CTkLabel(header, text="AI Search", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"))
        title.pack(side="left")

        subtitle = ctk.CTkLabel(
            header,
            text="Search by meaning (summaries/OCR), not just filenames",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("#a7abb3", "#a7abb3"),
        )
        subtitle.pack(side="left", padx=(14, 0))

        # Index panel
        index_panel = ctk.CTkFrame(self, corner_radius=12)
        index_panel.pack(fill="x", padx=20, pady=(0, 12))

        index_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            index_panel,
            text="Workspace Folder",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))

        self.folder_var = ctk.StringVar(value="")
        self.folder_entry = ctk.CTkEntry(
            index_panel,
            textvariable=self.folder_var,
            height=38,
            placeholder_text="Pick a folder to index...",
        )
        self.folder_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(14, 8))

        browse_btn = ctk.CTkButton(index_panel, text="Browse", width=110, height=38, command=self._browse_folder)
        browse_btn.grid(row=0, column=2, sticky="e", padx=14, pady=(14, 8))

        self.include_subfolders_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            index_panel,
            text="Include subfolders",
            variable=self.include_subfolders_var,
        ).grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        self.docs_only_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            index_panel,
            text="Documents only (recommended)",
            variable=self.docs_only_var,
        ).grid(row=2, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        self.ai_summarize_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            index_panel,
            text="Generate AI summaries (slower, improves natural-language search)",
            variable=self.ai_summarize_var,
        ).grid(row=3, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        self.extract_images_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            index_panel,
            text="Extract text from images (OCR/vision, slow)",
            variable=self.extract_images_var,
        ).grid(row=4, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        self.ocr_pdfs_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            index_panel,
            text="OCR scanned PDFs (slow, helps invoices)",
            variable=self.ocr_pdfs_var,
        ).grid(row=5, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        self.compute_hashes_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            index_panel,
            text="Compute file hashes (for dedupe, slower)",
            variable=self.compute_hashes_var,
        ).grid(row=6, column=1, sticky="w", padx=(0, 10), pady=(0, 12))

        self.fts_label = ctk.CTkLabel(
            index_panel,
            text=f"FTS Search: {'ON' if self.library.fts_enabled else 'OFF'}",
            text_color=("#a7abb3", "#a7abb3"),
        )
        self.fts_label.grid(row=6, column=0, sticky="w", padx=14, pady=(0, 12))

        self.index_btn = ctk.CTkButton(
            index_panel,
            text="Index Now",
            width=110,
            height=34,
            command=self._start_indexing,
        )
        self.index_btn.grid(row=6, column=2, sticky="e", padx=14, pady=(0, 12))

        self.progress_label = ctk.CTkLabel(index_panel, text="", text_color=("#a7abb3", "#a7abb3"))
        self.progress_label.grid(row=7, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 12))

        # Search bar
        search_panel = ctk.CTkFrame(self, corner_radius=12)
        search_panel.pack(fill="x", padx=20, pady=(0, 10))
        search_panel.grid_columnconfigure(0, weight=1)

        self.query_var = ctk.StringVar(value="")
        self.query_entry = ctk.CTkEntry(search_panel, textvariable=self.query_var, height=42, placeholder_text="Ask: “Show me invoices from Amazon”")
        self.query_entry.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        self.query_entry.bind("<Return>", lambda _e: self._run_search())

        right = ctk.CTkFrame(search_panel, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=(0, 14), pady=14)

        self.rerank_var = ctk.BooleanVar(value=True)
        self.rerank_box = ctk.CTkCheckBox(right, text="AI rerank", variable=self.rerank_var)
        self.rerank_box.pack(side="left", padx=(0, 12))

        self.search_btn = ctk.CTkButton(right, text="Search", width=120, height=42, command=self._run_search)
        self.search_btn.pack(side="left")

        self.search_meta = ctk.CTkLabel(search_panel, text="", text_color=("#a7abb3", "#a7abb3"))
        self.search_meta.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        # Results
        self.results_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self._render_empty_state()

    def _render_empty_state(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.results_frame,
            text="No results yet.\n\nIndex a folder, then ask a natural-language query.",
            text_color=("#a7abb3", "#a7abb3"),
            justify="center",
        ).pack(pady=60)

    def _browse_folder(self):
        folder = filedialog.askdirectory(parent=self._top(), title="Select folder to index")
        if folder:
            self.folder_var.set(folder)

    def _start_indexing(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("No folder", "Pick a folder to index first.", parent=self._top())
            return
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            messagebox.showerror("Invalid folder", "That folder does not exist.", parent=self._top())
            return

        if self._index_thread and self._index_thread.is_alive():
            messagebox.showinfo("Indexing", "Indexing is already running.", parent=self._top())
            return

        self.index_btn.configure(state="disabled")
        self.progress_label.configure(text="Starting index…")

        def progress(msg: str, frac: float):
            self.after(0, lambda: self.progress_label.configure(text=f"{msg}  ({frac:.0%})"))

        def run():
            try:
                count = self.library.index_folder(
                    p,
                    include_subfolders=self.include_subfolders_var.get(),
                    ai_manager=self.ai_manager,
                    ai_summarize=bool(self.ai_summarize_var.get() and self.ai_manager and getattr(self.ai_manager, "is_ready", False)),
                    extract_images=bool(self.extract_images_var.get() and self.ai_manager and getattr(self.ai_manager, "is_ready", False)),
                    compute_hashes=bool(self.compute_hashes_var.get()),
                    include_extensions=[".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"] if bool(self.docs_only_var.get()) else None,
                    ocr_scanned_pdfs=bool(self.ocr_pdfs_var.get() and self.ai_manager and getattr(self.ai_manager, "is_ready", False)),
                    ocr_pdf_pages=1,
                    max_pdf_ocr_files=60,
                    progress_cb=progress,
                )
                self.after(0, lambda: self.progress_label.configure(text=f"Indexed {count} file(s)."))
                self.after(0, lambda: self.fts_label.configure(text=f"FTS Search: {'ON' if self.library.fts_enabled else 'OFF'}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Index error", str(e), parent=self._top()))
            finally:
                self.after(0, lambda: self.index_btn.configure(state="normal"))

        self._index_thread = threading.Thread(target=run, daemon=True)
        self._index_thread.start()

    def _run_search(self):
        q = self.query_var.get().strip()
        if not q:
            return
        if self._search_thread and self._search_thread.is_alive():
            return

        self.search_btn.configure(state="disabled")
        self.search_meta.configure(text="Searching…")

        def run():
            try:
                results = ai_search(
                    self.library,
                    q,
                    ai_manager=self.ai_manager,
                    limit=50,
                    rerank=bool(self.rerank_var.get()),
                    folder=Path(self.folder_var.get().strip()) if self.folder_var.get().strip() else None,
                )
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Search error", str(e), parent=self._top()))
                results = []
            finally:
                self.after(0, lambda: self.search_btn.configure(state="normal"))

            def render():
                for w in self.results_frame.winfo_children():
                    w.destroy()

                if not results:
                    self.search_meta.configure(text="No matches.")
                    ctk.CTkLabel(
                        self.results_frame,
                        text="No matches.\n\nTip: index the folder first, then try broader terms.",
                        text_color=("#a7abb3", "#a7abb3"),
                        justify="center",
                    ).pack(pady=60)
                    return

                meta = results[0]
                self.search_meta.configure(
                    text=f"Searching with: {meta.matched_query}   |   AI rewrite: {'ON' if meta.used_ai else 'OFF'}   |   Rerank: {'ON' if meta.used_rerank else 'OFF'}"
                )

                header = ctk.CTkLabel(
                    self.results_frame,
                    text=f"Results ({len(results)})",
                    font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                )
                header.pack(anchor="w", pady=(0, 10))

                for res in results:
                    self._render_result(res.item)

            self.after(0, render)

        self._search_thread = threading.Thread(target=run, daemon=True)
        self._search_thread.start()

    def _render_result(self, item):
        card = ctk.CTkFrame(self.results_frame, corner_radius=12)
        card.pack(fill="x", pady=8)
        card.grid_columnconfigure(0, weight=1)

        name = ctk.CTkLabel(card, text=item.name, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"))
        name.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        path_label = ctk.CTkLabel(card, text=item.path, text_color=("#a7abb3", "#a7abb3"))
        path_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        if item.ai_summary:
            summary = ctk.CTkLabel(card, text=item.ai_summary, wraplength=800, justify="left")
            summary.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 10))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=3, sticky="ne", padx=14, pady=12)

        open_btn = ctk.CTkButton(actions, text="Open", width=90, command=lambda p=item.path: self._open_file(p))
        open_btn.pack(pady=(0, 8))

        explain_btn = ctk.CTkButton(
            actions,
            text="Why this name?",
            width=120,
            fg_color=("#4f555e", "#4f555e"),
            hover_color=("#5c636e", "#5c636e"),
            command=lambda p=item.path: self._explain_file(p),
        )
        explain_btn.pack()

    def _open_file(self, path_str: str):
        p = Path(path_str)
        if not p.exists():
            messagebox.showerror("Missing file", "File no longer exists.", parent=self._top())
            return
        try:
            # Windows open
            import os

            os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("Open failed", str(e), parent=self._top())

    def _explain_file(self, path_str: str):
        p = Path(path_str)
        text = explain_filename(p, ai_manager=self.ai_manager)
        messagebox.showinfo("Why is this file named this?", text, parent=self._top())


class AISearchView(_AISearchUI, ctk.CTkFrame):
    """Embeddable AI Search view (used in MainWindow)."""

    def __init__(self, parent, ai_manager=None):
        super().__init__(parent, fg_color="transparent")
        self._init_common(ai_manager)
        self._setup_ui()


class AISearchDialog(_AISearchUI, ctk.CTkToplevel):
    """Standalone window wrapper (kept for compatibility)."""

    def __init__(self, parent, ai_manager=None):
        super().__init__(parent)
        self._init_common(ai_manager)

        self.title("AI Search")
        self.geometry("950x650")
        self.minsize(900, 600)
        try:
            self.transient(parent)
        except Exception:
            pass

        self._setup_ui()
