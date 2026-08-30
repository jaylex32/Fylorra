"""
Fylorra - Workspace Dialog
Unified "one place" screen: choose a target folder + run multiple tools together.
All actions run through WorkflowRunner to avoid a fragmented UX.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

from core.ai_command import CommandPlan, CommandStep
from core.workflow_actions import HeadlessCommandAction, actions_from_command_plan
from core.workflow_runner import WorkflowContext, WorkflowRunner


class WorkspaceView(ctk.CTkFrame):
    def __init__(self, parent, ai_manager=None):
        super().__init__(parent, fg_color="transparent")
        self.ai_manager = ai_manager

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._history_lines: list[str] = []

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Workspace", font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Pick a folder once, then run any combination of tools in one flow.",
            text_color=("#666666", "#b0b0b0"),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        top = ctk.CTkFrame(self)
        top.grid(row=1, column=0, padx=18, pady=(0, 12), sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        self.folder_var = ctk.StringVar(value=str(Path.home()))
        folder_entry = ctk.CTkEntry(top, textvariable=self.folder_var, placeholder_text="Target folder...")
        folder_entry.grid(row=0, column=0, padx=(12, 8), pady=12, sticky="ew")
        ctk.CTkButton(top, text="Browse", width=110, command=self._browse_folder).grid(row=0, column=1, padx=(0, 12), pady=12)

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=2, column=0, padx=18, pady=(0, 12), sticky="ew")
        self.include_subfolders = ctk.BooleanVar(value=True)
        self.include_hidden = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Include subfolders", variable=self.include_subfolders).pack(side="left")
        ctk.CTkCheckBox(opts, text="Include hidden files", variable=self.include_hidden).pack(side="left", padx=(14, 0))

        body = ctk.CTkFrame(self)
        body.grid(row=3, column=0, padx=18, pady=(0, 18), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.actions = ctk.CTkScrollableFrame(
            body,
            label_text="Actions",
            scrollbar_button_color=("#3a3a3a", "#2a2a2a"),
            scrollbar_button_hover_color=("#4a4a4a", "#3a3a3a"),
        )
        self.actions.grid(row=0, column=0, padx=(14, 8), pady=14, sticky="nsew")
        self.actions.grid_columnconfigure(0, weight=1)

        self.history = ctk.CTkFrame(body)
        self.history.grid(row=0, column=1, padx=(8, 14), pady=14, sticky="nsew")
        self.history.grid_columnconfigure(0, weight=1)
        self.history.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.history, text="Run History", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")
        self.history_text = ctk.CTkTextbox(self.history, wrap="word")
        self.history_text.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.history_text.configure(state="disabled")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, padx=18, pady=(0, 18), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(footer, text="Ready", text_color=("#666666", "#b0b0b0"))
        self.status.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(footer, text="Run Selected", width=160, command=self._run_selected).grid(row=0, column=1, sticky="e")

        self._action_vars: dict[str, ctk.BooleanVar] = {}
        self._build_action_list()

    def _top(self):
        try:
            return self.winfo_toplevel()
        except Exception:
            return self

    def _browse_folder(self):
        p = filedialog.askdirectory(parent=self._top(), title="Select a folder")
        if p:
            self.folder_var.set(p)

    def _target_folder(self) -> Path:
        return Path(self.folder_var.get()).expanduser()

    def _add_action(self, action_id: str, title: str, desc: str, *, default: bool = False):
        var = ctk.BooleanVar(value=default)
        self._action_vars[action_id] = var
        card = ctk.CTkFrame(self.actions)
        card.grid_columnconfigure(0, weight=1)
        card.grid(row=len(self._action_vars), column=0, padx=12, pady=(8, 0), sticky="ew")
        ctk.CTkCheckBox(card, text=title, variable=var, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
        ctk.CTkLabel(card, text=desc, wraplength=380, justify="left", text_color=("#666666", "#b0b0b0")).grid(
            row=1, column=0, padx=12, pady=(0, 10), sticky="w"
        )

    def _build_action_list(self):
        # AI organization tools (dialogs)
        self._add_action("smart_rename", "Smart Rename", "AI-powered rename with preview + undo.", default=False)
        self._add_action("auto_categorize", "Auto-Categorize", "Organize files into folders by type/category.", default=False)
        self._add_action("security_scan", "Security Scan", "Scan images for sensitive information.", default=False)
        self._add_action("content_analysis", "Content Analysis", "Analyze document content in bulk.", default=False)

        # Index/search
        self._add_action("index_folder", "Index Folder", "Build local index for AI Search (recommended).", default=True)

        # ZIP
        self._add_action("zip_folder", "Zip Folder", "Create an archive of this folder.", default=False)

        # Conversions
        self._add_action("convert_images", "Convert Images", "Convert images to another format (PNG/JPG/WEBP…).", default=False)
        self._add_action("convert_media", "Convert Audio/Video", "Convert media in bulk using ffmpeg (managed by Python package).", default=False)
        self._add_action("convert_office_to_pdf", "Office → PDF", "Convert office docs via LibreOffice headless (optional).", default=False)

        # PDFs
        self._add_action("merge_pdfs", "Merge PDFs", "Merge PDFs found in the folder into one file.", default=False)
        self._add_action("split_pdf_bookmarks", "Split PDF By Bookmarks", "Split a PDF into files using bookmarks.", default=False)
        self._add_action("split_pdf_chunks", "Split PDF Into Chunks", "Split a PDF into N-pages-per-file.", default=False)
        self._add_action("split_pdf_pages", "Split PDF To Pages", "Split a PDF into single-page PDFs.", default=False)
        self._add_action("extract_pdf_pages", "Extract PDF Pages", "Extract a page range into a new PDF.", default=False)
        self._add_action("rotate_pdf", "Rotate PDF", "Rotate pages in a PDF and save a copy.", default=False)
        self._add_action("remove_pdf_pages", "Remove PDF Pages", "Remove a range of pages and save a copy.", default=False)
        self._add_action("watermark_pdf", "Watermark PDF", "Apply a diagonal watermark text (requires reportlab).", default=False)

    def _append_history(self, lines: list[str]):
        self._history_lines.extend(lines)
        self._history_lines = self._history_lines[-400:]
        self.history_text.configure(state="normal")
        self.history_text.delete("1.0", "end")
        self.history_text.insert("1.0", "\n".join(self._history_lines))
        self.history_text.configure(state="disabled")

    def _prompt_pdf_input(self) -> str | None:
        return simpledialog.askstring("PDF", "Enter input PDF (relative under folder, e.g. report.pdf):", parent=self._top())

    def _run_selected(self):
        folder = self._target_folder()
        if not folder.exists():
            messagebox.showerror("Workspace", "Target folder does not exist.", parent=self._top())
            return

        include_sub = bool(self.include_subfolders.get())
        include_hidden = bool(self.include_hidden.get())

        steps: list[CommandStep] = []
        selected = [k for k, v in self._action_vars.items() if bool(v.get())]
        if not selected:
            messagebox.showinfo("Workspace", "Select at least one action.", parent=self._top())
            return

        # Dialog-based tools: just add the step (runner will open dialogs).
        for tool in ("smart_rename", "auto_categorize", "security_scan", "content_analysis"):
            if tool in selected:
                steps.append(CommandStep(tool=tool, args={}, description=tool.replace("_", " ").title(), destructive=True))

        # Index/search
        if "index_folder" in selected:
            steps.append(
                CommandStep(
                    tool="index_folder",
                    args={"include_subfolders": include_sub, "include_hidden": include_hidden},
                    description="Index folder",
                    destructive=False,
                )
            )

        # ZIP
        if "zip_folder" in selected:
            zip_name = simpledialog.askstring("Zip", "Output ZIP name:", initialvalue="Archive.zip", parent=self) or "Archive.zip"
            steps.append(
                CommandStep(
                    tool="zip_folder",
                    args={"include_subfolders": include_sub, "output_zip_name": zip_name, "overwrite": False},
                    description="Zip folder",
                    destructive=False,
                )
            )

        # Conversions
        if "convert_images" in selected:
            fmt = simpledialog.askstring("Images", "Output format (png/jpg/webp/bmp/tiff):", initialvalue="png", parent=self) or "png"
            steps.append(
                CommandStep(
                    tool="convert_images",
                    args={"include_subfolders": include_sub, "output_format": fmt, "output_subfolder": "Converted_Images", "overwrite": False},
                    description="Convert images",
                    destructive=False,
                )
            )
        if "convert_media" in selected:
            fmt = simpledialog.askstring("Media", "Output format (mp4/mp3/wav/m4a/etc):", initialvalue="mp4", parent=self) or "mp4"
            steps.append(
                CommandStep(
                    tool="convert_media",
                    args={"include_subfolders": include_sub, "output_format": fmt, "output_subfolder": "Converted_Media", "overwrite": False},
                    description="Convert media",
                    destructive=False,
                )
            )
        if "convert_office_to_pdf" in selected:
            steps.append(
                CommandStep(
                    tool="convert_office_to_pdf",
                    args={"include_subfolders": include_sub, "output_subfolder": "Converted_PDF", "overwrite": False, "output_mode": "subfolder"},
                    description="Office → PDF",
                    destructive=False,
                )
            )

        # PDF tools
        if "merge_pdfs" in selected:
            out_name = simpledialog.askstring("PDF Merge", "Output PDF name:", initialvalue="Merged.pdf", parent=self) or "Merged.pdf"
            steps.append(
                CommandStep(
                    tool="merge_pdfs",
                    args={"include_subfolders": include_sub, "output_pdf_name": out_name, "overwrite": False},
                    description="Merge PDFs",
                    destructive=False,
                )
            )
        if "split_pdf_bookmarks" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                steps.append(
                    CommandStep(
                        tool="split_pdf_bookmarks",
                        args={"input_pdf": inp, "output_subfolder": "Split_By_Bookmarks", "overwrite": False, "min_pages": 1},
                        description="Split PDF by bookmarks",
                        destructive=False,
                    )
                )
        if "split_pdf_chunks" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                pages = simpledialog.askinteger("PDF Chunks", "Pages per file:", initialvalue=10, parent=self) or 10
                steps.append(
                    CommandStep(
                        tool="split_pdf_chunks",
                        args={"input_pdf": inp, "output_subfolder": "Split_Chunks", "overwrite": False, "pages_per_file": pages},
                        description="Split PDF into chunks",
                        destructive=False,
                    )
                )
        if "split_pdf_pages" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                ranges = simpledialog.askstring("PDF Pages", "Page ranges (all or 1-3,5):", initialvalue="all", parent=self) or "all"
                steps.append(
                    CommandStep(
                        tool="split_pdf_pages",
                        args={"input_pdf": inp, "output_subfolder": "Split_Pages", "overwrite": False, "page_ranges": ranges},
                        description="Split PDF to pages",
                        destructive=False,
                    )
                )
        if "extract_pdf_pages" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                ranges = simpledialog.askstring("Extract Pages", "Page ranges (e.g. 2-3):", initialvalue="1-1", parent=self) or "1-1"
                out_name = simpledialog.askstring("Extract Pages", "Output PDF name:", initialvalue="Extracted.pdf", parent=self) or "Extracted.pdf"
                steps.append(
                    CommandStep(
                        tool="extract_pdf_pages",
                        args={"input_pdf": inp, "output_pdf_name": out_name, "overwrite": False, "page_ranges": ranges},
                        description="Extract PDF pages",
                        destructive=False,
                    )
                )
        if "rotate_pdf" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                deg = simpledialog.askinteger("Rotate", "Degrees (90/180/270):", initialvalue=90, parent=self) or 90
                out_name = simpledialog.askstring("Rotate", "Output PDF name:", initialvalue="Rotated.pdf", parent=self) or "Rotated.pdf"
                steps.append(
                    CommandStep(
                        tool="rotate_pdf",
                        args={"input_pdf": inp, "rotation_degrees": deg, "output_pdf_name": out_name, "overwrite": False, "page_ranges": "all"},
                        description="Rotate PDF",
                        destructive=False,
                    )
                )
        if "remove_pdf_pages" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                rm = simpledialog.askstring("Remove Pages", "Pages to remove (e.g. 2,5-7):", parent=self) or ""
                out_name = simpledialog.askstring("Remove Pages", "Output PDF name:", initialvalue="RemovedPages.pdf", parent=self) or "RemovedPages.pdf"
                if rm.strip():
                    steps.append(
                        CommandStep(
                            tool="remove_pdf_pages",
                            args={"input_pdf": inp, "remove_ranges": rm, "output_pdf_name": out_name, "overwrite": False},
                            description="Remove PDF pages",
                            destructive=False,
                        )
                    )
        if "watermark_pdf" in selected:
            inp = self._prompt_pdf_input()
            if inp:
                txt = simpledialog.askstring("Watermark", "Watermark text:", initialvalue="CONFIDENTIAL", parent=self) or "CONFIDENTIAL"
                out_name = simpledialog.askstring("Watermark", "Output PDF name:", initialvalue="Watermarked.pdf", parent=self) or "Watermarked.pdf"
                steps.append(
                    CommandStep(
                        tool="watermark_pdf",
                        args={"input_pdf": inp, "text": txt, "output_pdf_name": out_name, "overwrite": False},
                        description="Watermark PDF",
                        destructive=False,
                    )
                )

        if not steps:
            messagebox.showinfo("Workspace", "No runnable steps (you may have canceled required prompts).", parent=self._top())
            return

        plan = CommandPlan(intent_summary="Workspace run", steps=steps)
        ui_actions, headless_plan = actions_from_command_plan(plan)

        ctx = WorkflowContext(parent=self._top(), ai_manager=self.ai_manager, target_folder=folder, include_subfolders=include_sub)
        runner = WorkflowRunner(ctx)

        actions = list(ui_actions)
        if headless_plan.steps:
            actions.append(HeadlessCommandAction(action_id="headless", title="Background Steps", plan=headless_plan))

        def on_progress(msg: str, frac: float):
            self.status.configure(text=f"{msg} ({frac:.0%})")

        def on_done(reports):
            ok = all(r.ok for r in reports)
            lines = ["---", f"Workspace run: {'OK' if ok else 'DONE (errors)'}"]
            for r in reports:
                if r.action_id == "headless" and r.data and isinstance(r.data, dict):
                    for item in r.data.get("results", []):
                        status = "OK" if item.get("ok") else "FAIL"
                        tool = item.get("tool")
                        msg = item.get("message") or item.get("error") or ""
                        lines.append(f"{status} {tool} {msg}".strip())
                else:
                    lines.append(f"{'OK' if r.ok else 'FAIL'} {r.action_id} {r.message}".strip())
            self._append_history(lines)
            self.status.configure(text="Ready")

        runner.run(actions, progress=on_progress, done=on_done)


class WorkspaceDialog(ctk.CTkToplevel):
    """Standalone window wrapper (kept for compatibility)."""

    def __init__(self, parent, ai_manager=None):
        super().__init__(parent)
        self.title("Fylorra Workspace")
        self.geometry("980x720")
        self.minsize(940, 680)
        try:
            self.transient(parent)
        except Exception:
            pass

        view = WorkspaceView(self, ai_manager=ai_manager)
        view.pack(fill="both", expand=True)
