"""
Fylorra - File Tools Dialog
Manual access to built-in converters (PDF/ZIP/Image/Office->PDF/Media).
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import threading

import customtkinter as ctk

from core.ai_command import plan_from_nl, run_plan as run_command_plan
from core.ffmpeg_manager import get_ffmpeg_exe
from core.image_converter import convert_images_in_folder
from core.lo_converter import LibreOfficeConverter
from core.media_converter import convert_media_in_folder
from core.media_tools import convert_media_file
from core.pdf_advanced import remove_pages
from core.pdf_tools import extract_pages_to_pdf, merge_pdfs, rotate_pdf, split_pdf_by_bookmarks, split_pdf_into_chunks, split_pdf_to_pages
from core.pdf_to_docx import pdf_to_docx_text
from core.pdf_text_extract import pdf_to_txt
from core.workflow_actions import HeadlessCommandAction, actions_from_command_plan
from core.workflow_runner import WorkflowContext, WorkflowRunner
from core.archive_tools import create_archive, extract_archive
from core.zip_tools import unzip_archive, unzip_archive_with_progress, zip_folder, zip_folder_with_progress

FILE_TOOLS_ALLOWED = {
    "index_folder",
    "search_index",
    "convert_office_to_pdf",
    "zip_folder",
    "unzip_archive",
    "convert_images",
    "convert_media",
    "convert_media_file",
    "cut_video",
    "convert_excel_to_csv",
    "merge_pdfs",
    "extract_pdf_pages",
    "split_pdf_pages",
    "split_pdf_chunks",
    "split_pdf_bookmarks",
    "rotate_pdf",
    "remove_pdf_pages",
    "reorder_pdf_pages",
    "watermark_pdf",
    "search_pdf_text",
    "make_folder",
    "move_files",
    "copy_files",
    "delete_files",
    "organize_audio_by_tags",
}


class _FileToolsUI:
    def _build_ui(self, parent, ai_manager=None, settings_manager=None, *, embedded: bool = False):
        self._app_root = parent
        self.ai_manager = ai_manager
        self.settings_manager = settings_manager
        self._embedded = bool(embedded)
        self._ai_plan = None

        self._converter = LibreOfficeConverter()

        self.grid_columnconfigure(0, weight=1)
        # row 4 is the main body
        self.grid_rowconfigure(4, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=18, pady=(18, 6), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="File Tools", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Select a folder, pick a tab, run a tool (outputs go into subfolders).",
            text_color=("#666666", "#b0b0b0"),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        folder_frame = ctk.CTkFrame(self)
        folder_frame.grid(row=1, column=0, padx=18, pady=(6, 10), sticky="ew")
        folder_frame.grid_columnconfigure(0, weight=1)

        self.folder_var = ctk.StringVar(value=str(Path.home()))
        try:
            self.folder_var.trace_add("write", lambda *_: self._on_target_folder_changed())
        except Exception:
            pass
        ctk.CTkEntry(folder_frame, textvariable=self.folder_var, placeholder_text="Target folder...").grid(
            row=0, column=0, padx=(12, 8), pady=12, sticky="ew"
        )
        ctk.CTkButton(folder_frame, text="Browse", width=110, command=self._browse_folder).grid(
            row=0, column=1, padx=(0, 12), pady=12
        )

        self.caps_label = ctk.CTkLabel(folder_frame, text="", text_color=("#666666", "#b0b0b0"))
        self.caps_label.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="w")
        self._refresh_caps()

        # Top tabs bar: main tabs + context controls (Convert: Media/Images/Office + Batch/Single)
        top_tabs_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_tabs_bar.grid(row=2, column=0, padx=18, pady=(0, 8), sticky="ew")
        top_tabs_bar.grid_columnconfigure(0, weight=0)
        top_tabs_bar.grid_columnconfigure(1, weight=1)
        top_tabs_bar.grid_columnconfigure(2, weight=0)

        self.tab_selector = ctk.CTkSegmentedButton(top_tabs_bar, values=["PDF", "Convert", "ZIP"], command=self._switch_tab)
        self.tab_selector.grid(row=0, column=0, sticky="w")

        self._convert_controls = ctk.CTkFrame(top_tabs_bar, fg_color="transparent")
        self._convert_controls.grid(row=0, column=2, sticky="e")
        self._convert_controls.grid_columnconfigure((0, 1), weight=0)

        self.convert_nav = ctk.CTkSegmentedButton(
            self._convert_controls,
            values=["Media", "Images", "Office"],
            height=32,
            command=lambda v: self._set_convert_view(v),
        )
        self.convert_nav.grid(row=0, column=0, padx=(0, 10))

        self.convert_media_mode = ctk.CTkSegmentedButton(
            self._convert_controls,
            values=["Batch", "Single"],
            height=32,
            command=lambda v: self._set_media_mode(v),
        )
        self.convert_media_mode.grid(row=0, column=1)

        # Hidden unless Convert tab is active
        self._convert_controls.grid_remove()

        ai_wrap = self._add_collapsible_section(self, title="AI Assist", row=3, column=0, padx=18, pady=(0, 10), start_open=False)
        ai_panel = ctk.CTkFrame(ai_wrap, fg_color="transparent")
        ai_panel.grid(row=0, column=0, sticky="ew")
        ai_panel.grid_columnconfigure(0, weight=1)
        ai_panel.grid_columnconfigure(1, weight=0)
        ai_panel.grid_columnconfigure(2, weight=0)
        ai_panel.grid_columnconfigure(3, weight=0)

        self.ai_prompt_var = ctk.StringVar(value="")
        self.ai_prompt = ctk.CTkEntry(
            ai_panel,
            textvariable=self.ai_prompt_var,
            height=42,
            placeholder_text="AI Assist: e.g. convert Deezer to mp3 320kbps into MP3 Music",
        )
        self.ai_prompt.grid(row=0, column=0, padx=(12, 10), pady=12, sticky="ew")

        self.ai_plan_btn = ctk.CTkButton(ai_panel, text="Generate Plan", width=150, height=42, command=self._generate_ai_plan)
        self.ai_plan_btn.grid(row=0, column=1, padx=(0, 10), pady=12, sticky="e")

        self.ai_run_btn = ctk.CTkButton(ai_panel, text="Run", width=90, height=42, state="disabled", command=self._run_ai_plan)
        self.ai_run_btn.grid(row=0, column=2, padx=(0, 10), pady=12, sticky="e")

        ctk.CTkButton(ai_panel, text="Workspace", width=120, height=42, command=self._open_workspace).grid(
            row=0, column=3, padx=(0, 12), pady=12, sticky="e"
        )

        # Prompt presets to help users get started
        presets_row = ctk.CTkFrame(ai_panel, fg_color="transparent")
        presets_row.grid(row=1, column=0, columnspan=4, padx=12, pady=(0, 10), sticky="ew")
        presets_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(presets_row, text="Presets:", text_color=("#666666", "#b0b0b0")).grid(row=0, column=0, sticky="w")

        self._prompt_presets = {
            "Convert subfolder audio → MP3 320k": "Convert all audio in <subfolder> to mp3 320kbps into folder named Converted_Audio",
            "Convert folder videos → MP4": "Convert all videos in this folder to mp4 into folder named Converted_Video",
            "Convert videos → MP4 (GPU if available)": "Convert all videos in this folder to mp4 into folder named Converted_Video using GPU if available",
            "Convert videos → MKV H.265 720p": "Convert all videos in this folder to mkv h265 720p into folder named Converted_Video",
            "Convert videos → MP4 H.264 1080p": "Convert all videos in this folder to mp4 h264 1080p into folder named Converted_Video",
            "Convert videos → WEBM VP9 720p": "Convert all videos in this folder to webm vp9 720p into folder named Converted_Video",
            "Make ringtone (cut segment)": "Cut 16 - Track.flac from 1:23 to 1:41 into Ringtone.mp3",
            "Convert images → WEBP": "Convert all images in this folder to webp into folder named Converted_Images",
            "Office → PDF then ZIP": "Convert all Word/Excel/PowerPoint files to PDF, then zip the folder into Archive.zip",
            "PDF split to pages": "Split manual.pdf into individual pages into folder named Split_Pages",
            "PDF split by bookmarks": "Split manual.pdf by bookmarks into folder named Split_By_Bookmarks",
            "PDF merge": "Merge PDFs report1.pdf and report2.pdf into Merged.pdf",
            "ZIP folder": "Zip this folder into Archive.zip",
            "Unzip archive": "Unzip Archive.zip into folder named Extracted",
            "Index + search": "Index this folder, then find invoices from Amazon",
        }
        self.preset_var = ctk.StringVar(value=list(self._prompt_presets.keys())[0])
        ctk.CTkOptionMenu(presets_row, values=list(self._prompt_presets.keys()), variable=self.preset_var).grid(
            row=0, column=1, padx=(10, 10), sticky="ew"
        )
        ctk.CTkButton(presets_row, text="Insert", width=110, command=self._insert_preset).grid(row=0, column=2, sticky="e")

        self.ai_status_var = ctk.StringVar(value="")
        self.ai_status = ctk.CTkLabel(ai_panel, textvariable=self.ai_status_var, text_color=("#666666", "#b0b0b0"))
        self.ai_status.grid(row=2, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="w")

        self.ai_progress = ctk.CTkProgressBar(ai_panel)
        self.ai_progress.set(0.0)
        self.ai_progress.grid(row=3, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="ew")
        self.ai_progress.grid_remove()

        self.ai_plan_preview = ctk.CTkTextbox(ai_panel, height=110, wrap="word")
        self.ai_plan_preview.grid(row=4, column=0, columnspan=4, padx=12, pady=(0, 12), sticky="ew")
        self.ai_plan_preview.configure(state="disabled")
        self.ai_plan_preview.grid_remove()

        # Make the main body scrollable so tools never push buttons off-screen.
        # Hide the scrollbar (mouse wheel still works). CustomTkinter versions differ,
        # so we hide the internal scrollbar widget instead of relying on ctor args.
        self.body = ctk.CTkScrollableFrame(self)
        try:
            sb = getattr(self.body, "_scrollbar", None)
            if sb is not None:
                sb.grid_remove()
        except Exception:
            pass
        # Mousewheel scrolling still works via CustomTkinter's internal bindings;
        # avoid global bind_all here (it can interfere with other pages/widgets).
        self.body.grid(row=4, column=0, padx=18, pady=(0, 12), sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)

        self.pdf_tab = self._build_pdf_tab(self.body)
        self.convert_tab = self._build_convert_tab(self.body)
        self.zip_tab = self._build_zip_tab(self.body)

        footer = ctk.CTkFrame(self)
        footer.grid(row=5, column=0, padx=18, pady=(0, 18), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=0)
        self.status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(footer, textvariable=self.status_var, text_color=("#666666", "#b0b0b0")).grid(
            row=0, column=0, padx=12, pady=(10, 6), sticky="w"
        )

        self._task_row = ctk.CTkFrame(footer, fg_color="transparent")
        self._task_row.grid(row=0, column=1, padx=12, pady=(10, 6), sticky="e")
        self.task_progress = ctk.CTkProgressBar(self._task_row, width=220)
        self.task_progress.set(0.0)
        self.task_progress.grid(row=0, column=0, padx=(0, 10))
        self.task_percent_var = ctk.StringVar(value="")
        self.task_percent = ctk.CTkLabel(self._task_row, textvariable=self.task_percent_var, text_color=("#666666", "#b0b0b0"))
        self.task_percent.grid(row=0, column=1, padx=(0, 10))
        self.task_cancel_btn = ctk.CTkButton(self._task_row, text="Cancel", width=90, command=self._cancel_task)
        self.task_cancel_btn.grid(row=0, column=2)
        self._task_row.grid_remove()
        self._task_thread = None
        self._task_cancel_event = None
        self._task_determinate = False
        log_wrap = self._add_collapsible_section(footer, title="Log", row=1, column=0, columnspan=2, pady=(0, 12), start_open=False)
        self.log = ctk.CTkTextbox(log_wrap, height=120, wrap="word")
        self.log.grid(row=0, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.log.configure(state="disabled")

        self.tab_selector.set("PDF")
        self._switch_tab("PDF")

        self.transient(parent)
        self.grab_set()
        self.after(120, self.lift)

    def _add_collapsible_section(
        self,
        parent,
        *,
        title: str,
        row: int,
        column: int = 0,
        columnspan: int = 1,
        padx=0,
        pady=(0, 10),
        start_open: bool = False,
    ):
        """
        Creates a dropdown-like section (collapsed by default) and returns the body frame to populate.
        """
        container = ctk.CTkFrame(parent)
        container.grid(row=row, column=column, columnspan=columnspan, padx=padx, pady=pady, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header.grid_columnconfigure(0, weight=1)

        state = {"open": bool(start_open)}

        def update_btn():
            arrow = "▾" if state["open"] else "▸"
            toggle.configure(text=f"{arrow} {title}")

        def toggle_open():
            state["open"] = not state["open"]
            if state["open"]:
                body.grid()
            else:
                body.grid_remove()
            update_btn()

        toggle = ctk.CTkButton(
            header,
            text="",
            height=32,
            fg_color=("gray85", "#2b2b2b"),
            hover_color=("gray80", "#333333"),
            anchor="w",
            command=toggle_open,
        )
        toggle.grid(row=0, column=0, sticky="ew")

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)
        if not state["open"]:
            body.grid_remove()
        update_btn()
        return body

    def _ensure_ai_ready(self) -> bool:
        from tkinter import messagebox

        if not self.ai_manager:
            messagebox.showwarning("AI Not Available", "AI is not initialized. Check Settings.", parent=self)
            return False
        if getattr(self.ai_manager, "is_ready", False):
            return True
        if getattr(self.ai_manager, "model_files_exist", lambda: False)():
            from gui.ai_loading_dialog import AILoadingDialog

            dlg = AILoadingDialog(self, self.ai_manager)
            self.wait_window(dlg)
            return bool(getattr(self.ai_manager, "is_ready", False))
        load = messagebox.askyesno(
            "AI Model Download Required",
            "AI model needs to be downloaded first.\n\nDownload/load now?",
            parent=self,
        )
        if not load:
            return False
        from gui.ai_loading_dialog import AILoadingDialog

        dlg = AILoadingDialog(self, self.ai_manager)
        self.wait_window(dlg)
        return bool(getattr(self.ai_manager, "is_ready", False))

    def _set_ai_status(self, text: str):
        try:
            self.ai_status_var.set(text)
        except Exception:
            pass

    def _render_ai_plan_preview(self):
        plan = self._ai_plan
        if not plan:
            try:
                self.ai_plan_preview.configure(state="normal")
                self.ai_plan_preview.delete("1.0", "end")
                self.ai_plan_preview.configure(state="disabled")
                self.ai_plan_preview.grid_remove()
            except Exception:
                pass
            return

        lines = [f"{plan.intent_summary}", ""]
        for i, step in enumerate(plan.steps, start=1):
            lines.append(f"{i}. {step.tool} — {step.description}")
        txt = "\n".join(lines).strip() + "\n"

        try:
            self.ai_plan_preview.configure(state="normal")
            self.ai_plan_preview.delete("1.0", "end")
            self.ai_plan_preview.insert("1.0", txt)
            self.ai_plan_preview.configure(state="disabled")
            self.ai_plan_preview.grid()
        except Exception:
            pass

    def _generate_ai_plan(self):
        prompt = (self.ai_prompt_var.get() or "").strip()
        if not prompt:
            messagebox.showinfo("AI Assist", "Type an instruction first.", parent=self)
            return
        if not self._ensure_ai_ready():
            return

        self.ai_plan_btn.configure(state="disabled")
        self.ai_run_btn.configure(state="disabled")
        self._set_ai_status("Planning…")
        self.ai_progress.set(0.0)
        try:
            self.ai_progress.grid()
        except Exception:
            pass

        target = self._target_folder()

        def work():
            try:
                plan = plan_from_nl(self.ai_manager, prompt, target_folder=target, allowed_tools=FILE_TOOLS_ALLOWED)
                self.after(0, lambda: self._on_ai_plan_ready(plan))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self._on_ai_plan_failed(err))

        threading.Thread(target=work, daemon=True).start()

    def _on_ai_plan_ready(self, plan):
        self._ai_plan = plan
        self._render_ai_plan_preview()
        self._set_ai_status("Plan ready.")
        self.ai_progress.set(0.0)
        try:
            self.ai_progress.grid_remove()
        except Exception:
            pass
        self.ai_plan_btn.configure(state="normal")
        self.ai_run_btn.configure(state="normal")

    def _on_ai_plan_failed(self, err: str):
        self._ai_plan = None
        self._render_ai_plan_preview()
        self._set_ai_status("Plan failed.")
        try:
            self.ai_progress.grid_remove()
        except Exception:
            pass
        self.ai_plan_btn.configure(state="normal")
        self.ai_run_btn.configure(state="disabled")
        messagebox.showerror("AI Plan", err, parent=self)

    def _run_ai_plan(self):
        if not self._ai_plan:
            return
        if not self._ensure_ai_ready():
            return

        self.ai_plan_btn.configure(state="disabled")
        self.ai_run_btn.configure(state="disabled")
        self._set_ai_status("Running…")
        self.ai_progress.set(0.0)
        try:
            self.ai_progress.grid()
        except Exception:
            pass

        plan = self._ai_plan
        target = self._target_folder()
        ui_actions, headless_plan = actions_from_command_plan(plan)

        def finish(report: dict):
            ok = report.get("ok")
            self._set_ai_status("Done." if ok else "Completed with errors.")
            self.ai_progress.set(0.0)
            try:
                self.ai_progress.grid_remove()
            except Exception:
                pass
            self.ai_plan_btn.configure(state="normal")
            self.ai_run_btn.configure(state="normal")
            try:
                self._append_log(f"AI: {plan.intent_summary} -> ok={bool(ok)}")
            except Exception:
                pass

            if ok:
                messagebox.showinfo("AI File Tools", "Completed.", parent=self)
                return

            errors = []
            for r in (report.get("results") or []):
                if not isinstance(r, dict):
                    continue
                if r.get("ok") is True:
                    continue
                tool = str(r.get("tool") or "step")
                err = str(r.get("error") or r.get("message") or "Unknown error")
                errors.append(f"{tool}: {err}")

            if errors:
                for line in errors[:8]:
                    try:
                        self._append_log(f"AI ERROR: {line}")
                    except Exception:
                        pass
                msg = "Completed with errors:\n\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n… and {len(errors) - 5} more (see log)."
                messagebox.showerror("AI File Tools", msg, parent=self)
            else:
                messagebox.showerror("AI File Tools", "Completed with errors. See log.", parent=self)

        def emit(msg: str, frac: float):
            def ui():
                self._set_ai_status(f"{msg} ({frac:.0%})")
                self.ai_progress.set(max(0.0, min(1.0, float(frac))))

            self.after(0, ui)

        def run_headless_only():
            try:
                report = run_command_plan(headless_plan, target_folder=target, ai_manager=self.ai_manager, progress=emit)
                self.after(0, lambda: finish(report))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self._on_ai_run_failed(err))

        if not ui_actions:
            threading.Thread(target=run_headless_only, daemon=True).start()
            return

        ctx = WorkflowContext(parent=self, ai_manager=self.ai_manager, target_folder=target, include_subfolders=True)
        runner = WorkflowRunner(ctx)

        actions = list(ui_actions)
        if headless_plan.steps:
            actions.append(HeadlessCommandAction(action_id="headless", title="Background Steps", plan=headless_plan))

        def on_progress(msg: str, frac: float):
            self._set_ai_status(f"{msg} ({frac:.0%})")
            self.ai_progress.set(max(0.0, min(1.0, float(frac))))

        def on_done(reports):
            ok = all(r.ok for r in reports if r.action_id != "workflow")
            flat_results = []
            for r in reports:
                if r.action_id == "headless" and r.data and isinstance(r.data, dict):
                    flat_results.extend(r.data.get("results", []))
                else:
                    flat_results.append({"tool": r.action_id, "ok": r.ok, "error": "" if r.ok else r.message})
            report = {"ok": ok, "intent_summary": plan.intent_summary, "results": flat_results}
            self.after(0, lambda: finish(report))

        runner.run(actions, progress=on_progress, done=on_done)

    def _on_ai_run_failed(self, err: str):
        self._set_ai_status("Run failed.")
        try:
            self.ai_progress.grid_remove()
        except Exception:
            pass
        self.ai_plan_btn.configure(state="normal")
        self.ai_run_btn.configure(state="normal" if self._ai_plan else "disabled")
        messagebox.showerror("AI Run", err, parent=self)

    def _open_workspace(self):
        prompt = (self.ai_prompt_var.get() or "").strip()
        # Workspace doesn't require AI, but if prompt is present user probably wants AI.
        if prompt and self.ai_manager and not getattr(self.ai_manager, "is_ready", False):
            # optional on-demand load
            self._ensure_ai_ready()
        try:
            from gui.workspace_dialog import WorkspaceDialog

            WorkspaceDialog(self, self.ai_manager)
        except Exception as e:
            messagebox.showerror("Workspace", str(e), parent=self)

    def _insert_preset(self):
        key = (self.preset_var.get() or "").strip()
        text = self._prompt_presets.get(key)
        if not text:
            return
        self.ai_prompt_var.set(text)

    def _target_folder(self) -> Path:
        return Path(self.folder_var.get()).expanduser()

    def _browse_folder(self):
        p = filedialog.askdirectory(title="Select a folder")
        if p:
            self.folder_var.set(p)
        self._on_target_folder_changed()

    def _refresh_caps(self):
        parts = []
        try:
            import pypdf  # noqa: F401
            parts.append("PDF: OK")
        except Exception:
            parts.append("PDF: missing pypdf")
        parts.append("Office Convert: OK" if self._converter.is_available() else "Office Convert: needs LibreOffice")
        parts.append("Media: OK" if get_ffmpeg_exe() else "Media: missing ffmpeg")
        self.caps_label.configure(text=" | ".join(parts))

    def _on_target_folder_changed(self):
        self._refresh_caps()
        try:
            if hasattr(self, "media_preview_src_var"):
                self._update_media_preview()
            if hasattr(self, "single_preview_out_var"):
                self._update_single_preview()
        except Exception:
            pass

    def _normalize_subfolder(self, text: str) -> str | None:
        s = (text or "").strip().strip("/\\")
        if not s:
            return None
        p = Path(s)
        if p.is_absolute() or ".." in p.parts:
            return "__invalid__"
        return p.as_posix()

    def _pick_subfolder(self, var: ctk.StringVar):
        base = self._target_folder()
        p = filedialog.askdirectory(title="Pick a subfolder", initialdir=str(base))
        if not p:
            return
        try:
            rel = Path(p).resolve().relative_to(base.resolve())
        except Exception:
            messagebox.showerror("Pick Subfolder", "Please pick a folder inside the Target folder.", parent=self)
            return
        var.set(rel.as_posix())

    def _update_media_preview(self):
        try:
            base = self._target_folder()
            source_sub = self._normalize_subfolder(self.media_source_sub.get())
            if source_sub == "__invalid__":
                self.media_preview_src_var.set("Source: (invalid subfolder)")
                self.media_preview_out_var.set("Output: (invalid subfolder)")
                return
            source_dir = base / source_sub if source_sub else base

            out_sub = (self.media_out_sub.get() or "Converted_Media").strip() or "Converted_Media"
            output_root = (self.media_output_root.get() or "target").strip().lower()
            out_base = source_dir if output_root == "source" else base
            out_dir = out_base / out_sub

            preserve = bool(self.media_preserve_structure.get())
            example_dir = out_dir
            if preserve and source_sub and output_root == "target":
                example_dir = out_dir / source_sub

            self.media_preview_src_var.set(f"Source: {source_dir}")
            self.media_preview_out_var.set(f"Output: {example_dir}")
        except Exception:
            pass

    def _pick_single_media_file(self):
        base = self._target_folder()
        p = filedialog.askopenfilename(
            title="Pick a media file",
            initialdir=str(base),
            filetypes=[
                ("Media", "*.mp3 *.wav *.m4a *.flac *.mp4 *.mkv *.avi *.mov *.webm"),
                ("All files", "*.*"),
            ],
        )
        if not p:
            return
        self.single_input_path.set(p)

    def _pick_office_single_file(self):
        base = self._target_folder()
        p = filedialog.askopenfilename(
            title="Pick a document",
            initialdir=str(base),
            filetypes=[
                ("Documents", "*.pdf *.doc *.docx *.odt *.rtf *.txt *.html *.htm *.xls *.xlsx *.ods *.csv *.tsv *.ppt *.pptx *.odp"),
                ("All files", "*.*"),
            ],
        )
        if not p:
            return
        self.office_single_input_path.set(p)

    def _update_single_preview(self):
        try:
            base = self._target_folder()
            fmt = (self.single_format.get() or "mp3").strip().lower()
            out_sub = (self.single_out_sub.get() or "Converted_Media").strip() or "Converted_Media"
            inp = (self.single_input_path.get() or "").strip()
            if not inp:
                out_root = (getattr(self, "single_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
                out_base = base if out_root == "target" else base
                self.single_preview_out_var.set(f"Output: {out_base / out_sub}")
                return
            inp_path = Path(inp)
            out_root = (getattr(self, "single_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
            out_base = base if out_root == "target" else inp_path.parent
            out_path = out_base / out_sub / f"{inp_path.stem}.{fmt}"
            self.single_preview_out_var.set(f"Output: {out_path}")
        except Exception:
            pass

    def _update_office_single_preview(self):
        try:
            base = self._target_folder()
            inp = (getattr(self, "office_single_input_path", ctk.StringVar(value="")).get() or "").strip()
            out_sub = (getattr(self, "office_out_sub", ctk.StringVar(value="Converted_Office")).get() or "Converted_Office").strip() or "Converted_Office"
            out_fmt = (getattr(self, "office_output_format", ctk.StringVar(value="pdf")).get() or "pdf").strip().lower().lstrip(".")
            out_root = (getattr(self, "office_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
            if not inp:
                self.office_single_preview_var.set("")
                return
            in_path = Path(inp)
            out_base = base if out_root == "target" else in_path.parent
            out_path = out_base / out_sub / (in_path.stem + "." + out_fmt)
            self.office_single_preview_var.set(f"Output: {out_path}")
        except Exception:
            pass

    def _switch_tab(self, name: str):
        for w in (self.pdf_tab, self.convert_tab, self.zip_tab):
            w.grid_forget()
        if name == "PDF":
            try:
                self._convert_controls.grid_remove()
            except Exception:
                pass
            self.pdf_tab.grid(row=0, column=0, sticky="nsew")
        elif name == "Convert":
            try:
                self._convert_controls.grid()
            except Exception:
                pass
            self.convert_tab.grid(row=0, column=0, sticky="nsew")
            # Ensure the correct convert view/mode is visible
            try:
                self._set_convert_view(getattr(self, "_current_convert_view", "Media"))
            except Exception:
                pass
        else:
            try:
                self._convert_controls.grid_remove()
            except Exception:
                pass
            self.zip_tab.grid(row=0, column=0, sticky="nsew")

    def _set_convert_view(self, name: str):
        name = (name or "Media").strip()
        self._current_convert_view = name
        try:
            self.convert_nav.set(name)
        except Exception:
            pass
        views = getattr(self, "_convert_views", None) or {}
        for k, frame in views.items():
            try:
                if k == name:
                    frame.grid()
                else:
                    frame.grid_remove()
            except Exception:
                pass
        # Show Batch/Single only for Media
        try:
            if name == "Media":
                self.convert_media_mode.grid()
            else:
                self.convert_media_mode.grid_remove()
        except Exception:
            pass

    def _set_media_mode(self, mode: str):
        mode = (mode or "Batch").strip()
        self._current_media_mode = mode
        try:
            self.convert_media_mode.set(mode)
        except Exception:
            pass
        batch = getattr(self, "_media_batch_frame", None)
        single = getattr(self, "_media_single_frame", None)
        try:
            if mode == "Single":
                if batch:
                    batch.grid_remove()
                if single:
                    single.grid()
            else:
                if single:
                    single.grid_remove()
                if batch:
                    batch.grid()
        except Exception:
            pass

    def _append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _cancel_task(self):
        ev = getattr(self, "_task_cancel_event", None)
        if ev:
            try:
                ev.set()
            except Exception:
                pass
        self._set_status("Cancelling…")
        try:
            self.task_cancel_btn.configure(state="disabled")
        except Exception:
            pass

    def _run_background_task(self, *, title: str, worker, on_done):
        if self._task_thread and self._task_thread.is_alive():
            messagebox.showinfo("Busy", "A task is already running. Please wait or Cancel it.", parent=self)
            return

        self._task_cancel_event = threading.Event()
        ev = self._task_cancel_event
        self._set_status(title)
        try:
            self.task_cancel_btn.configure(state="normal")
            self.task_percent_var.set("0%")
            self._task_determinate = False
            self.task_progress.configure(mode="indeterminate")
            self.task_progress.start()
            self._task_row.grid()
        except Exception:
            pass

        def done_ui(result, err: str | None):
            try:
                self._task_row.grid_remove()
            except Exception:
                pass
            try:
                self.task_progress.stop()
                self.task_progress.configure(mode="determinate")
                self.task_progress.set(0.0)
                self.task_percent_var.set("")
            except Exception:
                pass
            self._task_cancel_event = None
            self._task_thread = None
            on_done(result, err)

        def run():
            try:
                result = worker(ev)
                self.after(0, lambda: done_ui(result, None))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: done_ui(None, err))

        self._task_thread = threading.Thread(target=run, daemon=True)
        self._task_thread.start()

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _pick_pdf(self, var: ctk.StringVar):
        p = filedialog.askopenfilename(title="Select PDF", filetypes=[("PDF", "*.pdf")])
        if p:
            var.set(p)

    def _pick_zip(self, var: ctk.StringVar):
        p = filedialog.askopenfilename(title="Select ZIP", filetypes=[("ZIP", "*.zip")])
        if p:
            var.set(p)

    def _resolve_input(self, value: str) -> Path | None:
        value = (value or "").strip().strip("\"'")
        if not value:
            return None
        p = Path(value)
        if p.is_absolute():
            return p
        return self._target_folder() / value

    # ----- PDF -----
    def _build_pdf_tab(self, parent):
        tab = ctk.CTkFrame(parent, fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # Compact PDF source row (used by operations that need an input PDF)
        src = ctk.CTkFrame(tab)
        src.grid(row=0, column=0, padx=6, pady=(0, 10), sticky="ew")
        src.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(src, text="PDF Source:", text_color=("#666666", "#b0b0b0")).grid(row=0, column=0, padx=(12, 10), pady=12, sticky="w")
        self.pdf_source = ctk.StringVar(value="")
        ctk.CTkEntry(src, textvariable=self.pdf_source, placeholder_text="Input PDF (relative or full path)").grid(row=0, column=1, pady=12, sticky="ew")
        ctk.CTkButton(src, text="Browse", width=110, command=lambda: self._pick_pdf(self.pdf_source)).grid(row=0, column=2, padx=(10, 12), pady=12)

        # One toolbar for PDF tools (shows only one panel at a time)
        toolbar = ctk.CTkSegmentedButton(tab, values=["Merge", "Split/Extract", "Rotate", "Bookmarks"], height=34)
        toolbar.grid(row=1, column=0, padx=6, pady=(0, 10), sticky="w")

        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.grid(row=2, column=0, padx=0, pady=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        views: dict[str, ctk.CTkFrame] = {}

        def show(name: str):
            for k, f in views.items():
                if k == name:
                    f.grid()
                else:
                    f.grid_remove()

        # ---- Merge ----
        merge = ctk.CTkFrame(body)
        merge.grid(row=0, column=0, sticky="nsew")
        merge.grid_columnconfigure(0, weight=1)
        views["Merge"] = merge
        self.merge_include_sub = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(merge, text="Include subfolders", variable=self.merge_include_sub).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")
        self.merge_out_name = ctk.StringVar(value="Merged.pdf")
        ctk.CTkEntry(merge, textvariable=self.merge_out_name, placeholder_text="Output PDF name").grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.merge_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(merge, text="Overwrite output if exists", variable=self.merge_overwrite).grid(row=2, column=0, padx=12, pady=(0, 8), sticky="w")
        ctk.CTkButton(merge, text="Merge PDFs in Target Folder", command=self._run_merge_pdfs).grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")

        # ---- Split / Extract ----
        split = ctk.CTkFrame(body)
        split.grid(row=0, column=0, sticky="nsew")
        split.grid_columnconfigure(0, weight=1)
        split.grid_remove()
        views["Split/Extract"] = split
        self.split_ranges = ctk.StringVar(value="all")
        ctk.CTkEntry(split, textvariable=self.split_ranges, placeholder_text="Page ranges (all or 1-3,5)").grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        self.split_out_sub = ctk.StringVar(value="Split_Pages")
        ctk.CTkEntry(split, textvariable=self.split_out_sub, placeholder_text="Output subfolder (in Target)").grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.split_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(split, text="Overwrite outputs", variable=self.split_overwrite).grid(row=2, column=0, padx=12, pady=(0, 8), sticky="w")
        btns = ctk.CTkFrame(split, fg_color="transparent")
        btns.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Split to Files", command=self._run_split_pdf).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(btns, text="Extract to One PDF", command=self._run_extract_pdf).grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # ---- Rotate ----
        rotate = ctk.CTkFrame(body)
        rotate.grid(row=0, column=0, sticky="nsew")
        rotate.grid_columnconfigure((0, 1), weight=1)
        rotate.grid_remove()
        views["Rotate"] = rotate
        self.rotate_degrees = ctk.StringVar(value="90")
        self.rotate_ranges = ctk.StringVar(value="all")
        self.rotate_out_name = ctk.StringVar(value="Rotated.pdf")
        ctk.CTkOptionMenu(rotate, values=["90", "180", "270"], variable=self.rotate_degrees).grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        ctk.CTkEntry(rotate, textvariable=self.rotate_ranges, placeholder_text="Rotate page ranges").grid(row=0, column=1, padx=12, pady=(12, 8), sticky="ew")
        ctk.CTkEntry(rotate, textvariable=self.rotate_out_name, placeholder_text="Output PDF name").grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        self.rotate_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(rotate, text="Overwrite output", variable=self.rotate_overwrite).grid(row=2, column=0, padx=12, pady=(0, 8), sticky="w")
        ctk.CTkButton(rotate, text="Rotate PDF", command=self._run_rotate_pdf).grid(row=3, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")

        # ---- Bookmarks ----
        bm = ctk.CTkFrame(body)
        bm.grid(row=0, column=0, sticky="nsew")
        bm.grid_columnconfigure((0, 1), weight=1)
        bm.grid_remove()
        views["Bookmarks"] = bm
        self.bm_out_sub = ctk.StringVar(value="Split_By_Bookmarks")
        self.bm_min_pages = ctk.StringVar(value="1")
        ctk.CTkEntry(bm, textvariable=self.bm_out_sub, placeholder_text="Output subfolder (in Target)").grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        ctk.CTkEntry(bm, textvariable=self.bm_min_pages, placeholder_text="Min pages per section").grid(row=0, column=1, padx=12, pady=(12, 8), sticky="ew")
        self.bm_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(bm, text="Overwrite outputs", variable=self.bm_overwrite).grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")
        ctk.CTkButton(bm, text="Split by Bookmarks", command=self._run_split_bookmarks).grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")

        toolbar.configure(command=show)
        toolbar.set("Merge")
        show("Merge")

        return tab

    # ----- Convert -----
    def _build_convert_tab(self, parent):
        tab = ctk.CTkFrame(parent, fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        content = ctk.CTkFrame(tab, fg_color="transparent")
        content.grid(row=1, column=0, padx=0, pady=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        views: dict[str, ctk.CTkFrame] = {}
        self._convert_views = views

        # ---------------- Media view ----------------
        media_view = ctk.CTkFrame(content, fg_color="transparent")
        media_view.grid(row=0, column=0, sticky="nsew")
        media_view.grid_columnconfigure(0, weight=1)
        views["Media"] = media_view

        media_stack = ctk.CTkFrame(media_view, fg_color="transparent")
        media_stack.grid(row=0, column=0, sticky="nsew")
        media_stack.grid_columnconfigure(0, weight=1)

        media_batch = ctk.CTkFrame(media_stack)
        media_batch.grid(row=0, column=0, sticky="nsew")
        media_batch.grid_columnconfigure((0, 1), weight=1)
        self._media_batch_frame = media_batch

        media_single = ctk.CTkFrame(media_stack)
        media_single.grid(row=0, column=0, sticky="nsew")
        media_single.grid_columnconfigure(0, weight=1)
        media_single.grid_remove()
        self._media_single_frame = media_single

        # Default selection (actual showing is driven by top tab controls in _switch_tab)
        try:
            self._current_convert_view = getattr(self, "_current_convert_view", "Media")
            self._current_media_mode = getattr(self, "_current_media_mode", "Batch")
        except Exception:
            self._current_convert_view = "Media"
            self._current_media_mode = "Batch"

        # Presets (applies to Media Batch/Single)
        media_presets = {
            "Custom": {},
            "Audio: MP3 320k (CBR)": {"format": "mp3", "audio_bitrate": "320k", "preserve_cover": True},
            "Audio: MP3 192k": {"format": "mp3", "audio_bitrate": "192k", "preserve_cover": True},
            "Audio: FLAC (lossless)": {"format": "flac", "audio_bitrate": None, "preserve_cover": True},
            "Video: MP4 H.264 1080p": {"format": "mp4", "video_codec": "h264", "scale": "1080p", "video_crf": "20"},
            "Video: MKV H.265 720p": {"format": "mkv", "video_codec": "h265", "scale": "720p", "video_crf": "26"},
            "Video: MKV H.265 720p (GPU if available)": {"format": "mkv", "video_codec": "h265", "scale": "720p", "video_crf": "26", "use_gpu": True},
            "Video: WebM VP9 1080p": {"format": "webm", "video_codec": "vp9", "scale": "1080p", "video_crf": "32"},
        }

        def apply_preset(name: str, *, single: bool):
            cfg = media_presets.get(name, {})
            if single:
                if "format" in cfg:
                    self.single_format.set(cfg["format"])
                if "audio_bitrate" in cfg and hasattr(self, "single_bitrate"):
                    self.single_bitrate.set(cfg["audio_bitrate"] or "")
                if "video_codec" in cfg and hasattr(self, "single_video_codec"):
                    self.single_video_codec.set(cfg["video_codec"])
                if "scale" in cfg and hasattr(self, "single_scale"):
                    self.single_scale.set(cfg["scale"])
                if "video_crf" in cfg and hasattr(self, "single_video_crf"):
                    self.single_video_crf.set(cfg["video_crf"] or "")
                if "use_gpu" in cfg and hasattr(self, "single_use_gpu"):
                    self.single_use_gpu.set(bool(cfg["use_gpu"]))
                if "preserve_cover" in cfg and hasattr(self, "single_preserve_cover"):
                    self.single_preserve_cover.set(bool(cfg["preserve_cover"]))
            else:
                if "format" in cfg:
                    self.media_format.set(cfg["format"])
                if "audio_bitrate" in cfg and hasattr(self, "media_bitrate"):
                    self.media_bitrate.set(cfg["audio_bitrate"] or "")
                if "video_codec" in cfg and hasattr(self, "media_video_codec"):
                    self.media_video_codec.set(cfg["video_codec"])
                if "scale" in cfg and hasattr(self, "media_scale"):
                    self.media_scale.set(cfg["scale"])
                if "video_crf" in cfg and hasattr(self, "media_video_crf"):
                    self.media_video_crf.set(cfg["video_crf"] or "")
                if "use_gpu" in cfg and hasattr(self, "media_use_gpu"):
                    self.media_use_gpu.set(bool(cfg["use_gpu"]))
                if "preserve_cover" in cfg and hasattr(self, "media_preserve_cover"):
                    self.media_preserve_cover.set(bool(cfg["preserve_cover"]))

        # ---- Media (Batch) UI ----
        ctk.CTkLabel(media_batch, text="Media (Batch)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        self.media_source_sub = ctk.StringVar(value="")
        src_row = ctk.CTkFrame(media_batch, fg_color="transparent")
        src_row.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        src_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(src_row, textvariable=self.media_source_sub, placeholder_text="Source subfolder (optional, e.g. Deezer)").grid(
            row=0, column=0, sticky="ew"
        )
        ctk.CTkButton(src_row, text="Pick…", width=90, command=lambda: self._pick_subfolder(self.media_source_sub)).grid(
            row=0, column=1, padx=(10, 0)
        )

        preset_row = ctk.CTkFrame(media_batch, fg_color="transparent")
        preset_row.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        preset_row.grid_columnconfigure(1, weight=1)
        preset_row.grid_columnconfigure(2, weight=0)
        ctk.CTkLabel(preset_row, text="Preset:", text_color=("#666666", "#b0b0b0")).grid(row=0, column=0, sticky="w")
        self.media_preset = ctk.StringVar(value="Custom")
        ctk.CTkOptionMenu(
            preset_row,
            values=list(media_presets.keys()),
            variable=self.media_preset,
            command=lambda v: apply_preset(v, single=False),
        ).grid(row=0, column=1, padx=(10, 0), sticky="ew")

        self.media_format = ctk.StringVar(value="mp4")
        ctk.CTkOptionMenu(
            preset_row,
            values=["mp4", "mkv", "webm", "mp3", "wav", "m4a", "flac"],
            variable=self.media_format,
            width=110,
        ).grid(row=0, column=2, padx=(10, 0), sticky="e")

        self.media_out_sub = ctk.StringVar(value="Converted_Media")
        self.media_output_root = ctk.StringVar(value="target")
        out_row = ctk.CTkFrame(media_batch, fg_color="transparent")
        out_row.grid(row=3, column=0, columnspan=2, padx=12, pady=(0, 6), sticky="ew")
        out_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(out_row, textvariable=self.media_out_sub, placeholder_text="Output folder name (e.g. Converted_Media)").grid(
            row=0, column=0, sticky="ew"
        )
        ctk.CTkOptionMenu(out_row, values=["target", "source"], variable=self.media_output_root, width=110).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )

        adv = self._add_collapsible_section(media_batch, title="Advanced", row=4, column=0, columnspan=2, padx=12, pady=(0, 8), start_open=False)
        adv.grid_columnconfigure((0, 1), weight=1)
        self.media_preserve_structure = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(adv, text="Preserve folder structure", variable=self.media_preserve_structure).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.media_preserve_cover = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(adv, text="Preserve cover art (MP3)", variable=self.media_preserve_cover).grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.media_video_codec = ctk.StringVar(value="h264")
        ctk.CTkOptionMenu(adv, values=["h264", "h265", "vp9"], variable=self.media_video_codec).grid(row=1, column=0, padx=(0, 12), pady=(0, 8), sticky="ew")
        self.media_scale = ctk.StringVar(value="keep")
        ctk.CTkOptionMenu(adv, values=["keep", "720p", "1080p", "4k"], variable=self.media_scale).grid(row=1, column=1, pady=(0, 8), sticky="ew")
        self.media_bitrate = ctk.StringVar(value="320k")
        ctk.CTkEntry(adv, textvariable=self.media_bitrate, placeholder_text="Audio bitrate (e.g. 320k)").grid(row=2, column=0, padx=(0, 12), pady=(0, 8), sticky="ew")
        self.media_video_crf = ctk.StringVar(value="20")
        ctk.CTkEntry(adv, textvariable=self.media_video_crf, placeholder_text="Video quality (CRF, lower=better, e.g. 20)").grid(row=2, column=1, pady=(0, 8), sticky="ew")
        self.media_use_gpu = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(adv, text="Use GPU (NVENC if available)", variable=self.media_use_gpu).grid(row=3, column=0, sticky="w")
        self.media_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(adv, text="Overwrite outputs", variable=self.media_overwrite).grid(row=3, column=1, sticky="w")

        self.media_include_sub = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(media_batch, text="Include subfolders", variable=self.media_include_sub).grid(
            row=5, column=0, padx=12, pady=(0, 8), sticky="w"
        )

        self.media_preview_src_var = ctk.StringVar(value="")
        self.media_preview_out_var = ctk.StringVar(value="")
        ctk.CTkLabel(media_batch, textvariable=self.media_preview_src_var, text_color=("#666666", "#b0b0b0")).grid(
            row=6, column=0, padx=12, pady=(0, 2), sticky="w"
        )
        ctk.CTkLabel(media_batch, textvariable=self.media_preview_out_var, text_color=("#666666", "#b0b0b0")).grid(
            row=7, column=0, padx=12, pady=(0, 8), sticky="w"
        )
        ctk.CTkButton(media_batch, text="Convert Media (Batch)", command=self._run_convert_media).grid(
            row=8, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew"
        )

        # ---- Media (Single) UI ----
        ctk.CTkLabel(media_single, text="Media (Single File)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )
        self.single_input_path = ctk.StringVar(value="")
        pick_row = ctk.CTkFrame(media_single, fg_color="transparent")
        pick_row.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        pick_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(pick_row, textvariable=self.single_input_path, placeholder_text="Pick a media file…").grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(pick_row, text="Browse", width=110, command=self._pick_single_media_file).grid(row=0, column=1, padx=(10, 0))

        single_preset_row = ctk.CTkFrame(media_single, fg_color="transparent")
        single_preset_row.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")
        single_preset_row.grid_columnconfigure(1, weight=1)
        single_preset_row.grid_columnconfigure(2, weight=0)
        ctk.CTkLabel(single_preset_row, text="Preset:", text_color=("#666666", "#b0b0b0")).grid(row=0, column=0, sticky="w")
        self.single_preset = ctk.StringVar(value="Custom")
        ctk.CTkOptionMenu(
            single_preset_row,
            values=list(media_presets.keys()),
            variable=self.single_preset,
            command=lambda v: apply_preset(v, single=True),
        ).grid(row=0, column=1, padx=(10, 0), sticky="ew")

        self.single_format = ctk.StringVar(value="mp4")
        ctk.CTkOptionMenu(
            single_preset_row,
            values=["mp4", "mkv", "webm", "mp3", "wav", "m4a", "flac"],
            variable=self.single_format,
            width=110,
        ).grid(row=0, column=2, padx=(10, 0), sticky="e")

        self.single_out_sub = ctk.StringVar(value="Converted_Media")
        self.single_output_root = ctk.StringVar(value="target")
        out_row = ctk.CTkFrame(media_single, fg_color="transparent")
        out_row.grid(row=3, column=0, padx=12, pady=(0, 6), sticky="ew")
        out_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(out_row, textvariable=self.single_out_sub, placeholder_text="Output folder name").grid(
            row=0, column=0, sticky="ew"
        )
        ctk.CTkOptionMenu(out_row, values=["target", "source"], variable=self.single_output_root, width=110).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )

        single_adv = self._add_collapsible_section(media_single, title="Advanced", row=4, column=0, columnspan=1, padx=12, pady=(0, 8), start_open=False)
        single_adv.grid_columnconfigure((0, 1), weight=1)
        self.single_video_codec = ctk.StringVar(value="h264")
        ctk.CTkOptionMenu(single_adv, values=["h264", "h265", "vp9"], variable=self.single_video_codec).grid(row=0, column=0, padx=(0, 12), pady=(0, 8), sticky="ew")
        self.single_scale = ctk.StringVar(value="keep")
        ctk.CTkOptionMenu(single_adv, values=["keep", "720p", "1080p", "4k"], variable=self.single_scale).grid(row=0, column=1, pady=(0, 8), sticky="ew")
        self.single_video_crf = ctk.StringVar(value="20")
        ctk.CTkEntry(single_adv, textvariable=self.single_video_crf, placeholder_text="Video quality (CRF, e.g. 20)").grid(row=1, column=0, padx=(0, 12), pady=(0, 8), sticky="ew")
        self.single_bitrate = ctk.StringVar(value="320k")
        ctk.CTkEntry(single_adv, textvariable=self.single_bitrate, placeholder_text="Audio bitrate (e.g. 320k)").grid(row=1, column=1, pady=(0, 8), sticky="ew")
        self.single_use_gpu = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(single_adv, text="Use GPU (NVENC if available)", variable=self.single_use_gpu).grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.single_preserve_cover = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(single_adv, text="Preserve cover art (MP3)", variable=self.single_preserve_cover).grid(row=2, column=1, sticky="w", pady=(0, 6))
        self.single_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(single_adv, text="Overwrite output", variable=self.single_overwrite).grid(row=3, column=0, sticky="w")

        self.single_preview_out_var = ctk.StringVar(value="")
        ctk.CTkLabel(media_single, textvariable=self.single_preview_out_var, text_color=("#666666", "#b0b0b0")).grid(
            row=5, column=0, padx=12, pady=(0, 8), sticky="w"
        )
        single_btn_row = ctk.CTkFrame(media_single, fg_color="transparent")
        single_btn_row.grid(row=6, column=0, padx=12, pady=(0, 12), sticky="ew")
        single_btn_row.grid_columnconfigure(0, weight=1)
        single_btn_row.grid_columnconfigure(1, weight=0)
        ctk.CTkButton(single_btn_row, text="Convert Media (Single)", command=self._run_convert_single_media).grid(
            row=0, column=0, sticky="ew"
        )
        ctk.CTkButton(single_btn_row, text="Advanced Editor…", width=160, command=self._open_media_editor).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )

        ctk.CTkLabel(
            media_view,
            text="Tip: use AI bar above for natural-language conversions (codec/resolution/GPU supported).",
            text_color=("#666666", "#b0b0b0"),
        ).grid(row=2, column=0, padx=6, pady=(8, 0), sticky="w")

        # ---------------- Images view ----------------
        images_view = ctk.CTkFrame(content, fg_color="transparent")
        images_view.grid(row=0, column=0, sticky="nsew")
        images_view.grid_columnconfigure(0, weight=1)
        images_view.grid_remove()
        views["Images"] = images_view

        ctk.CTkLabel(images_view, text="Images (Batch)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )
        self.img_source_sub = ctk.StringVar(value="")
        img_src = ctk.CTkFrame(images_view, fg_color="transparent")
        img_src.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        img_src.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(img_src, textvariable=self.img_source_sub, placeholder_text="Source subfolder (optional)").grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(img_src, text="Pick…", width=90, command=lambda: self._pick_subfolder(self.img_source_sub)).grid(row=0, column=1, padx=(10, 0))
        self.img_format = ctk.StringVar(value="webp")
        ctk.CTkOptionMenu(images_view, values=["webp", "png", "jpg", "bmp", "tiff"], variable=self.img_format).grid(
            row=2, column=0, padx=12, pady=(0, 8), sticky="ew"
        )
        self.img_out_sub = ctk.StringVar(value="Converted_Images")
        ctk.CTkEntry(images_view, textvariable=self.img_out_sub, placeholder_text="Output folder name").grid(
            row=3, column=0, padx=12, pady=(0, 8), sticky="ew"
        )
        self.img_include_sub = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(images_view, text="Include subfolders", variable=self.img_include_sub).grid(row=4, column=0, padx=12, pady=(0, 6), sticky="w")
        self.img_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(images_view, text="Overwrite outputs", variable=self.img_overwrite).grid(row=5, column=0, padx=12, pady=(0, 10), sticky="w")
        ctk.CTkButton(images_view, text="Convert Images", command=self._run_convert_images).grid(row=6, column=0, padx=12, pady=(0, 12), sticky="ew")

        # ---------------- Office view ----------------
        office_view = ctk.CTkFrame(content, fg_color="transparent")
        office_view.grid(row=0, column=0, sticky="nsew")
        office_view.grid_columnconfigure(0, weight=1)
        office_view.grid_remove()
        views["Office"] = office_view

        header_row = ctk.CTkFrame(office_view, fg_color="transparent")
        header_row.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header_row, text="Office Convert", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        self.office_mode = ctk.CTkSegmentedButton(header_row, values=["Batch", "Single"], height=30)
        self.office_mode.grid(row=0, column=1, sticky="e")

        office_stack = ctk.CTkFrame(office_view, fg_color="transparent")
        office_stack.grid(row=1, column=0, sticky="nsew")
        office_stack.grid_columnconfigure(0, weight=1)

        office_batch = ctk.CTkFrame(office_stack)
        office_batch.grid(row=0, column=0, sticky="nsew")
        office_batch.grid_columnconfigure(0, weight=1)

        office_single = ctk.CTkFrame(office_stack)
        office_single.grid(row=0, column=0, sticky="nsew")
        office_single.grid_columnconfigure(0, weight=1)
        office_single.grid_remove()

        def show_office_mode(mode: str):
            if mode == "Single":
                office_batch.grid_remove()
                office_single.grid()
            else:
                office_single.grid_remove()
                office_batch.grid()

        self.office_mode.configure(command=show_office_mode)
        self.office_mode.set("Batch")

        # Shared output settings
        self.office_out_sub = ctk.StringVar(value="Converted_Office")
        self.office_output_format = ctk.StringVar(value="pdf")
        self.office_output_root = ctk.StringVar(value="target")
        self.office_overwrite = ctk.BooleanVar(value=False)

        # ---- Office (Batch) ----
        self.office_source_sub = ctk.StringVar(value="")
        off_src = ctk.CTkFrame(office_batch, fg_color="transparent")
        off_src.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        off_src.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(off_src, textvariable=self.office_source_sub, placeholder_text="Source subfolder (optional)").grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(off_src, text="Pick…", width=90, command=lambda: self._pick_subfolder(self.office_source_sub)).grid(row=0, column=1, padx=(10, 0))

        out_row = ctk.CTkFrame(office_batch, fg_color="transparent")
        out_row.grid(row=1, column=0, padx=0, pady=(0, 8), sticky="ew")
        out_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(out_row, textvariable=self.office_out_sub, placeholder_text="Output folder name").grid(row=0, column=0, sticky="ew")
        ctk.CTkOptionMenu(out_row, values=["pdf", "docx", "odt", "xlsx", "ods", "csv", "pptx", "odp", "txt", "html"], variable=self.office_output_format, width=110).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )
        ctk.CTkOptionMenu(out_row, values=["target", "source"], variable=self.office_output_root, width=110).grid(
            row=0, column=2, padx=(10, 0), sticky="e"
        )
        self.office_include_sub = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(office_batch, text="Include subfolders", variable=self.office_include_sub).grid(row=2, column=0, pady=(0, 6), sticky="w")
        ctk.CTkCheckBox(office_batch, text="Overwrite outputs", variable=self.office_overwrite).grid(row=3, column=0, pady=(0, 10), sticky="w")
        ctk.CTkButton(office_batch, text="Convert Documents (Batch)", command=self._run_convert_office).grid(row=4, column=0, pady=(0, 12), sticky="ew")

        # ---- Office (Single) ----
        self.office_single_input_path = ctk.StringVar(value="")
        pick_row = ctk.CTkFrame(office_single, fg_color="transparent")
        pick_row.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        pick_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(pick_row, textvariable=self.office_single_input_path, placeholder_text="Pick a document…").grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(pick_row, text="Browse", width=110, command=self._pick_office_single_file).grid(row=0, column=1, padx=(10, 0))

        out_row_s = ctk.CTkFrame(office_single, fg_color="transparent")
        out_row_s.grid(row=1, column=0, padx=0, pady=(0, 8), sticky="ew")
        out_row_s.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(out_row_s, textvariable=self.office_out_sub, placeholder_text="Output folder name").grid(row=0, column=0, sticky="ew")
        ctk.CTkOptionMenu(out_row_s, values=["pdf", "docx", "odt", "xlsx", "ods", "csv", "pptx", "odp", "txt", "html"], variable=self.office_output_format, width=110).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )
        ctk.CTkOptionMenu(out_row_s, values=["target", "source"], variable=self.office_output_root, width=110).grid(
            row=0, column=2, padx=(10, 0), sticky="e"
        )
        ctk.CTkCheckBox(office_single, text="Overwrite output", variable=self.office_overwrite).grid(row=2, column=0, pady=(0, 10), sticky="w")
        self.office_single_preview_var = ctk.StringVar(value="")
        ctk.CTkLabel(office_single, textvariable=self.office_single_preview_var, text_color=("#666666", "#b0b0b0")).grid(row=3, column=0, pady=(0, 8), sticky="w")
        ctk.CTkButton(office_single, text="Convert Document (Single)", command=self._run_convert_office_single).grid(row=4, column=0, pady=(0, 12), sticky="ew")

        # Sync top controls state
        try:
            self.convert_nav.set(self._current_convert_view)
            self.convert_media_mode.set(self._current_media_mode)
        except Exception:
            pass
        self._set_convert_view(self._current_convert_view)
        self._set_media_mode(self._current_media_mode)

        # previews update on changes
        for v in (
            self.media_source_sub,
            self.media_format,
            self.media_out_sub,
            self.media_output_root,
            self.media_preserve_structure,
        ):
            try:
                v.trace_add("write", lambda *_: self._update_media_preview())
            except Exception:
                pass
        for v in (self.single_input_path, self.single_format, self.single_out_sub, self.single_output_root):
            try:
                v.trace_add("write", lambda *_: self._update_single_preview())
            except Exception:
                pass
        for v in (self.office_single_input_path, self.office_out_sub, self.office_output_format, self.office_output_root):
            try:
                v.trace_add("write", lambda *_: self._update_office_single_preview())
            except Exception:
                pass
        self._update_media_preview()
        self._update_single_preview()
        self._update_office_single_preview()

        return tab

    # ----- ZIP -----
    def _build_zip_tab(self, parent):
        tab = ctk.CTkFrame(parent, fg_color="transparent")
        tab.grid_columnconfigure(0, weight=1)

        tab.grid_rowconfigure(2, weight=1)

        toolbar = ctk.CTkSegmentedButton(tab, values=["Create ZIP", "Extract ZIP"], height=34)
        toolbar.grid(row=0, column=0, padx=6, pady=(0, 10), sticky="w")

        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        views: dict[str, ctk.CTkFrame] = {}

        def show(name: str):
            for k, f in views.items():
                if k == name:
                    f.grid()
                else:
                    f.grid_remove()

        # -------- Create ZIP --------
        create = ctk.CTkFrame(body)
        create.grid(row=0, column=0, sticky="nsew")
        create.grid_columnconfigure(0, weight=1)
        views["Create ZIP"] = create

        self.zip_source_sub = ctk.StringVar(value="")
        src_row = ctk.CTkFrame(create, fg_color="transparent")
        src_row.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        src_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(src_row, textvariable=self.zip_source_sub, placeholder_text="Source subfolder (optional, inside Target)").grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(src_row, text="Pick…", width=90, command=lambda: self._pick_subfolder(self.zip_source_sub)).grid(row=0, column=1, padx=(10, 0))

        self.zip_name = ctk.StringVar(value="Archive")
        self.zip_format = ctk.StringVar(value="zip")
        self.zip_zip_ext = ctk.StringVar(value=".zip")
        self.zip_output_root = ctk.StringVar(value="target")
        out_row = ctk.CTkFrame(create, fg_color="transparent")
        out_row.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        out_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(out_row, textvariable=self.zip_name, placeholder_text="Archive name (no extension)").grid(row=0, column=0, sticky="ew")
        ctk.CTkOptionMenu(out_row, values=["zip", "7z", "tar.gz", "tar.xz", "tar.bz2"], variable=self.zip_format, width=110).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )
        ctk.CTkOptionMenu(out_row, values=["target", "source"], variable=self.zip_output_root, width=110).grid(row=0, column=2, padx=(10, 0), sticky="e")

        flags = ctk.CTkFrame(create, fg_color="transparent")
        flags.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")
        flags.grid_columnconfigure((0, 1), weight=1)
        self.zip_include_sub = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(flags, text="Include subfolders", variable=self.zip_include_sub).grid(row=0, column=0, sticky="w")
        self.zip_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(flags, text="Overwrite if exists", variable=self.zip_overwrite).grid(row=0, column=1, sticky="w")
        self.zip_timestamp = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(flags, text="Add timestamp", variable=self.zip_timestamp).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.zip_split = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(flags, text="Split into parts", variable=self.zip_split).grid(row=1, column=1, sticky="w", pady=(6, 0))

        self.zip_part_mb = ctk.StringVar(value="100")
        ctk.CTkEntry(create, textvariable=self.zip_part_mb, placeholder_text="Part size (MB, used only if split enabled)").grid(
            row=3, column=0, padx=12, pady=(0, 8), sticky="ew"
        )

        self.zip_preview_var = ctk.StringVar(value="")
        ctk.CTkLabel(create, textvariable=self.zip_preview_var, text_color=("#666666", "#b0b0b0")).grid(row=4, column=0, padx=12, pady=(0, 8), sticky="w")
        ctk.CTkButton(create, text="Create Archive", command=self._run_zip_folder).grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")

        # -------- Extract ZIP --------
        extract = ctk.CTkFrame(body)
        extract.grid(row=0, column=0, sticky="nsew")
        extract.grid_columnconfigure(0, weight=1)
        extract.grid_remove()
        views["Extract ZIP"] = extract

        self.unzip_input = ctk.StringVar(value="")
        in_row = ctk.CTkFrame(extract, fg_color="transparent")
        in_row.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        in_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(in_row, textvariable=self.unzip_input, placeholder_text="Archive (.zip) path").grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(in_row, text="Browse", width=110, command=lambda: self._pick_zip(self.unzip_input)).grid(row=0, column=1, padx=(10, 0))

        self.unzip_out_sub = ctk.StringVar(value="Extracted")
        self.unzip_output_root = ctk.StringVar(value="target")
        out_row2 = ctk.CTkFrame(extract, fg_color="transparent")
        out_row2.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        out_row2.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(out_row2, textvariable=self.unzip_out_sub, placeholder_text="Output folder name").grid(row=0, column=0, sticky="ew")
        ctk.CTkOptionMenu(out_row2, values=["target", "source"], variable=self.unzip_output_root, width=110).grid(row=0, column=1, padx=(10, 0), sticky="e")

        self.unzip_overwrite = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(extract, text="Overwrite existing files", variable=self.unzip_overwrite).grid(row=2, column=0, padx=12, pady=(0, 10), sticky="w")

        self.unzip_preview_var = ctk.StringVar(value="")
        ctk.CTkLabel(extract, textvariable=self.unzip_preview_var, text_color=("#666666", "#b0b0b0")).grid(row=3, column=0, padx=12, pady=(0, 8), sticky="w")
        ctk.CTkButton(extract, text="Extract", command=self._run_unzip).grid(row=4, column=0, padx=12, pady=(0, 12), sticky="ew")

        def update_preview(*_):
            try:
                target = self._target_folder()
                src_sub = self._normalize_subfolder(self.zip_source_sub.get())
                src_folder = target / src_sub if (src_sub and src_sub != "__invalid__") else target
                out_base = target if (self.zip_output_root.get() or "target") == "target" else src_folder
                fmt = (getattr(self, "zip_format", ctk.StringVar(value="zip")).get() or "zip").strip().lower()
                base = (self.zip_name.get() or "Archive").strip() or "Archive"
                ext = ".zip" if fmt == "zip" else ".7z" if fmt == "7z" else ".tar.gz" if fmt == "tar.gz" else ".tar.xz" if fmt == "tar.xz" else ".tar.bz2" if fmt == "tar.bz2" else ".zip"
                name = base + ext
                if self.zip_timestamp.get():
                    from datetime import datetime
                    # keep compound suffixes like .tar.gz intact
                    if name.lower().endswith(".tar.gz"):
                        stem = name[:-7]
                        suffix = ".tar.gz"
                    elif name.lower().endswith(".tar.xz"):
                        stem = name[:-7]
                        suffix = ".tar.xz"
                    elif name.lower().endswith(".tar.bz2"):
                        stem = name[:-8]
                        suffix = ".tar.bz2"
                    else:
                        stem = Path(name).stem
                        suffix = Path(name).suffix or ".zip"
                    name = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"
                if bool(getattr(self, "zip_split", ctk.BooleanVar(value=False)).get()):
                    self.zip_preview_var.set(f"Archive parts: {out_base / (name + '.parts')}")
                else:
                    self.zip_preview_var.set(f"Archive: {out_base / name}")
            except Exception:
                pass
            try:
                target = self._target_folder()
                inp = (self.unzip_input.get() or "").strip()
                archive = Path(inp) if inp else None
                out_base = target
                if archive and archive.exists():
                    out_base = target if (self.unzip_output_root.get() or "target") == "target" else archive.parent
                self.unzip_preview_var.set(f"Extract to: {out_base / (self.unzip_out_sub.get() or 'Extracted')}")
            except Exception:
                pass

        for v in (
            self.zip_source_sub,
            self.zip_name,
            self.zip_format,
            self.zip_output_root,
            self.zip_timestamp,
            self.zip_split,
            self.zip_part_mb,
            self.unzip_input,
            self.unzip_out_sub,
            self.unzip_output_root,
        ):
            try:
                v.trace_add("write", update_preview)
            except Exception:
                pass
        update_preview()

        toolbar.configure(command=show)
        toolbar.set("Create ZIP")
        show("Create ZIP")

        return tab

    # ----- Actions -----
    def _run_merge_pdfs(self):
        folder = self._target_folder()
        include_sub = bool(self.merge_include_sub.get())
        out_pdf = folder / ((self.merge_out_name.get() or "Merged.pdf").strip())
        pdfs = sorted([p for p in folder.glob("**/*.pdf" if include_sub else "*.pdf") if p.is_file()], key=lambda x: str(x).lower())
        try:
            self._set_status("Merging PDFs…")
            r = merge_pdfs(pdfs, output_pdf=out_pdf, overwrite=bool(self.merge_overwrite.get()))
            messagebox.showinfo("Merge PDFs", r.message, parent=self)
            self._append_log(f"Merge PDFs -> {out_pdf}")
        except Exception as e:
            messagebox.showerror("Merge PDFs", str(e), parent=self)
        finally:
            self._set_status("Ready")

    def _run_split_pdf(self):
        folder = self._target_folder()
        inp = self._resolve_input(self.pdf_source.get())
        if not inp:
            messagebox.showerror("Split PDF", "Select an input PDF (PDF Source).", parent=self)
            return
        out_dir = folder / (self.split_out_sub.get() or "Split_Pages")
        try:
            self._set_status("Splitting pages…")
            r = split_pdf_to_pages(inp, output_dir=out_dir, overwrite=bool(self.split_overwrite.get()), page_ranges=(self.split_ranges.get() or "all"))
            messagebox.showinfo("Split PDF", r.message, parent=self)
            self._append_log(f"Split pages -> {out_dir}")
        except Exception as e:
            messagebox.showerror("Split PDF", str(e), parent=self)
        finally:
            self._set_status("Ready")

    def _run_extract_pdf(self):
        folder = self._target_folder()
        inp = self._resolve_input(self.pdf_source.get())
        if not inp:
            messagebox.showerror("Extract Pages", "Select an input PDF (PDF Source).", parent=self)
            return
        out_name = simpledialog.askstring("Extract Pages", "Output PDF name:", initialvalue="Extracted.pdf", parent=self) or "Extracted.pdf"
        out_pdf = folder / out_name
        try:
            self._set_status("Extracting pages…")
            r = extract_pages_to_pdf(inp, output_pdf=out_pdf, overwrite=bool(self.split_overwrite.get()), page_ranges=(self.split_ranges.get() or "all"))
            messagebox.showinfo("Extract Pages", r.message, parent=self)
            self._append_log(f"Extract pages -> {out_pdf}")
        except Exception as e:
            messagebox.showerror("Extract Pages", str(e), parent=self)
        finally:
            self._set_status("Ready")

    def _run_rotate_pdf(self):
        folder = self._target_folder()
        inp = self._resolve_input(self.pdf_source.get())
        if not inp:
            messagebox.showerror("Rotate PDF", "Select an input PDF (PDF Source).", parent=self)
            return
        out_pdf = folder / ((self.rotate_out_name.get() or "Rotated.pdf").strip())
        try:
            self._set_status("Rotating…")
            r = rotate_pdf(
                inp,
                output_pdf=out_pdf,
                rotation_degrees=int(self.rotate_degrees.get() or 90),
                page_ranges=(self.rotate_ranges.get() or "all"),
                overwrite=bool(self.rotate_overwrite.get()),
            )
            messagebox.showinfo("Rotate PDF", r.message, parent=self)
            self._append_log(f"Rotate -> {out_pdf}")
        except Exception as e:
            messagebox.showerror("Rotate PDF", str(e), parent=self)
        finally:
            self._set_status("Ready")

    def _run_split_bookmarks(self):
        folder = self._target_folder()
        inp = self._resolve_input(self.pdf_source.get())
        if not inp:
            messagebox.showerror("Split Bookmarks", "Select an input PDF (PDF Source).", parent=self)
            return
        out_dir = folder / (self.bm_out_sub.get() or "Split_By_Bookmarks")
        try:
            self._set_status("Splitting by bookmarks…")
            r = split_pdf_by_bookmarks(inp, output_dir=out_dir, overwrite=bool(self.bm_overwrite.get()), min_pages=int(self.bm_min_pages.get() or 1))
            if r.ok:
                messagebox.showinfo("Split Bookmarks", r.message, parent=self)
                self._append_log(f"Split bookmarks -> {out_dir}")
            else:
                messagebox.showwarning("Split Bookmarks", r.message, parent=self)
        except Exception as e:
            messagebox.showerror("Split Bookmarks", str(e), parent=self)
        finally:
            self._set_status("Ready")

    def _run_convert_images(self):
        base = self._target_folder()
        sub = self._normalize_subfolder(getattr(self, "img_source_sub", ctk.StringVar(value="")).get())
        if sub == "__invalid__":
            messagebox.showerror("Convert Images", "Invalid source subfolder. Use a path inside the Target folder.", parent=self)
            return
        src = base / sub if sub else base

        def worker(cancel_ev):
            def per(cur, total, path):
                frac = 0.0 if total <= 0 else float(cur) / float(total)
                def ui():
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(max(0.0, min(1.0, frac)))
                    self.task_percent_var.set(f"{frac:.0%}")
                    self._set_status(f"Images {cur}/{total}: {Path(path).name}")
                self.after(0, ui)

            return convert_images_in_folder(
                src,
                include_subfolders=bool(self.img_include_sub.get()),
                output_format=(self.img_format.get() or "png"),
                output_subfolder=(self.img_out_sub.get() or "Converted_Images"),
                overwrite=bool(self.img_overwrite.get()),
                progress_cb=per,
                cancel_event=cancel_ev,
            )

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Convert Images", err, parent=self)
                return
            r = result
            if not r or not getattr(r, "ok", False):
                messagebox.showerror("Convert Images", getattr(r, "message", "Failed."), parent=self)
                return
            messagebox.showinfo("Convert Images", r.message, parent=self)
            self._append_log(f"Convert Images -> {r.output_dir}")

        self._run_background_task(title="Converting images…", worker=worker, on_done=on_done)

    def _run_convert_office(self):
        if not self._converter.is_available():
            msg = (
                "LibreOffice (soffice) is required for Office → PDF conversions.\n\n"
                "Yes: Download LibreOffice\nNo: Open Settings\nCancel: Do nothing"
            )
            choice = messagebox.askyesnocancel("LibreOffice Required", msg, parent=self)
            if choice is True:
                try:
                    from gui.libreoffice_download_dialog import LibreOfficeDownloadDialog

                    dlg = LibreOfficeDownloadDialog(self)
                    self.wait_window(dlg)
                    self._refresh_caps()
                except Exception:
                    pass
            elif choice is False:
                try:
                    from gui.settings_dialog import SettingsDialog
                    if self.settings_manager is not None:
                        dlg = SettingsDialog(self, self.settings_manager)
                        self.wait_window(dlg)
                    else:
                        messagebox.showinfo("Settings", "Open Settings from the main window to configure LibreOffice.", parent=self)
                except Exception:
                    pass
            return
        folder = self._target_folder()
        sub = self._normalize_subfolder(getattr(self, "office_source_sub", ctk.StringVar(value="")).get())
        if sub == "__invalid__":
            messagebox.showerror("Office → PDF", "Invalid source subfolder. Use a path inside the Target folder.", parent=self)
            return
        src_root = folder / sub if sub else folder
        include_sub = bool(self.office_include_sub.get())
        overwrite = bool(self.office_overwrite.get())
        out_sub = (getattr(self, "office_out_sub", ctk.StringVar(value="Converted_Office")).get() or "Converted_Office").strip() or "Converted_Office"
        out_root = (getattr(self, "office_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
        out_base = folder if out_root == "target" else src_root
        out_dir = out_base / out_sub

        out_fmt = (getattr(self, "office_output_format", ctk.StringVar(value="pdf")).get() or "pdf").strip().lower().lstrip(".")

        def allowed_exts_for(fmt: str) -> set[str]:
            doc = {".doc", ".docx", ".odt", ".rtf", ".txt", ".html", ".htm"}
            sheet = {".xls", ".xlsx", ".ods", ".csv", ".tsv"}
            pres = {".ppt", ".pptx", ".odp"}
            office = doc | sheet | pres
            if fmt in {"pdf"}:
                return office
            if fmt in {"docx", "odt", "txt", "html"}:
                return doc | {".pdf"}
            if fmt in {"xlsx", "ods", "csv"}:
                return sheet
            if fmt in {"pptx", "odp"}:
                return pres
            return office

        exts = allowed_exts_for(out_fmt)

        def worker(cancel_ev):
            out_dir.mkdir(parents=True, exist_ok=True)
            files = sorted(
                [p for p in src_root.glob("**/*" if include_sub else "*") if p.is_file() and p.suffix.lower() in exts],
                key=lambda x: str(x).lower(),
            )
            total = len(files)
            converted = 0
            skipped = 0

            for i, f in enumerate(files, start=1):
                if cancel_ev and cancel_ev.is_set():
                    return {"ok": False, "cancelled": True, "converted": converted, "skipped": skipped, "out_dir": str(out_dir)}

                frac = 0.0 if total <= 0 else float(i) / float(total)

                def ui(frac=frac, i=i, total=total, name=f.name):
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(max(0.0, min(1.0, frac)))
                    self.task_percent_var.set(f"{frac:.0%}")
                    self._set_status(f"Office {i}/{total}: {name}")

                self.after(0, ui)

                out_path_guess = out_dir / (f.stem + "." + out_fmt)
                if out_path_guess.exists() and not overwrite:
                    skipped += 1
                    continue
                out_path, err_msg = self._converter.convert_to_format_verbose(f, out_dir=out_dir, output_format=out_fmt)
                ok_this = False
                if out_path:
                    # LibreOffice sometimes creates empty TXT exports for PDFs. Detect and fallback.
                    try:
                        if f.suffix.lower() == ".pdf" and out_fmt == "txt" and out_path.exists() and out_path.stat().st_size == 0:
                            out_path = None
                    except Exception:
                        pass
                if out_path:
                    ok_this = True
                elif f.suffix.lower() == ".pdf" and out_fmt == "txt":
                    try:
                        fb = out_dir / (f.stem + ".txt")
                        pdf_to_txt(f, output_path=fb)
                        if fb.exists():
                            ok_this = True
                    except Exception as e:
                        err_msg = (err_msg or "") + f" | TXT fallback failed: {e}"

                if ok_this:
                    converted += 1
                else:
                    try:
                        self._append_log(f"Office convert failed: {f.name} -> {err_msg or 'failed'}")
                    except Exception:
                        pass
            return {"ok": True, "converted": converted, "skipped": skipped, "out_dir": str(out_dir), "fmt": out_fmt}

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Office Convert", err, parent=self)
                return
            r = result or {}
            if r.get("cancelled"):
                messagebox.showinfo("Office Convert", f"Cancelled. Converted {r.get('converted', 0)} files.", parent=self)
                return
            if not r.get("ok"):
                messagebox.showerror("Office Convert", "Failed.", parent=self)
                return
            messagebox.showinfo("Office Convert", f"Converted {r.get('converted', 0)} files to .{r.get('fmt','pdf')} (skipped {r.get('skipped', 0)}).", parent=self)
            self._append_log(f"Office convert -> {r.get('out_dir')} (fmt={r.get('fmt')}, converted={r.get('converted', 0)}, skipped={r.get('skipped', 0)})")

        self._run_background_task(title="Converting documents…", worker=worker, on_done=on_done)

    def _run_convert_office_single(self):
        if not self._converter.is_available():
            msg = (
                "LibreOffice (soffice) is required for document conversions.\n\n"
                "Yes: Download LibreOffice\nNo: Open Settings\nCancel: Do nothing"
            )
            choice = messagebox.askyesnocancel("LibreOffice Required", msg, parent=self)
            if choice is True:
                try:
                    from gui.libreoffice_download_dialog import LibreOfficeDownloadDialog

                    dlg = LibreOfficeDownloadDialog(self)
                    self.wait_window(dlg)
                    self._refresh_caps()
                except Exception:
                    pass
            elif choice is False:
                try:
                    from gui.settings_dialog import SettingsDialog
                    if self.settings_manager is not None:
                        dlg = SettingsDialog(self, self.settings_manager)
                        self.wait_window(dlg)
                        self._converter = LibreOfficeConverter()
                        self._refresh_caps()
                    else:
                        messagebox.showinfo("Settings", "Open Settings from the main window to configure LibreOffice.", parent=self)
                except Exception:
                    pass
            return

        inp_raw = (getattr(self, "office_single_input_path", ctk.StringVar(value="")).get() or "").strip()
        if not inp_raw:
            messagebox.showerror("Office Convert", "Pick a document first.", parent=self)
            return
        inp = Path(inp_raw)
        if not inp.exists():
            messagebox.showerror("Office Convert", "Selected file does not exist.", parent=self)
            return

        folder = self._target_folder()
        out_sub = (getattr(self, "office_out_sub", ctk.StringVar(value="Converted_Office")).get() or "Converted_Office").strip() or "Converted_Office"
        out_fmt = (getattr(self, "office_output_format", ctk.StringVar(value="pdf")).get() or "pdf").strip().lower().lstrip(".")
        out_root = (getattr(self, "office_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
        out_base = folder if out_root == "target" else inp.parent
        out_dir = out_base / out_sub
        out_dir.mkdir(parents=True, exist_ok=True)
        overwrite = bool(getattr(self, "office_overwrite", ctk.BooleanVar(value=False)).get())

        def worker(cancel_ev):
            if cancel_ev and cancel_ev.is_set():
                return {"ok": False, "cancelled": True}
            out_guess = out_dir / (inp.stem + "." + out_fmt)
            if out_guess.exists() and not overwrite:
                return {"ok": True, "skipped": True, "out": str(out_guess), "fmt": out_fmt}
            out_path, err_msg = self._converter.convert_to_format_verbose(inp, out_dir=out_dir, output_format=out_fmt)
            if out_path:
                # LibreOffice sometimes creates empty TXT exports for PDFs. Detect and fallback.
                try:
                    if inp.suffix.lower() == ".pdf" and out_fmt == "txt" and out_path.exists() and out_path.stat().st_size == 0:
                        raise RuntimeError("Empty TXT produced.")
                except Exception:
                    pass
                else:
                    return {"ok": True, "out": str(out_path), "fmt": out_fmt}
            # Fallback: PDF -> DOCX text extraction (useful for many scanned/print PDFs)
            if inp.suffix.lower() == ".pdf" and out_fmt == "docx":
                try:
                    fb = out_dir / (inp.stem + ".docx")
                    pdf_to_docx_text(inp, output_path=fb)
                    if fb.exists():
                        return {"ok": True, "out": str(fb), "fmt": "docx", "fallback": True}
                except Exception as e:
                    err_msg = (err_msg or "") + f" | Fallback failed: {e}"
            # Fallback: PDF -> TXT text extraction
            if inp.suffix.lower() == ".pdf" and out_fmt == "txt":
                try:
                    fb = out_dir / (inp.stem + ".txt")
                    pdf_to_txt(inp, output_path=fb)
                    if fb.exists():
                        return {"ok": True, "out": str(fb), "fmt": "txt", "fallback": True}
                except Exception as e:
                    err_msg = (err_msg or "") + f" | TXT fallback failed: {e}"
            return {"ok": False, "error": err_msg or "Conversion failed."}

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Office Convert", err, parent=self)
                return
            r = result or {}
            if r.get("cancelled"):
                messagebox.showinfo("Office Convert", "Cancelled.", parent=self)
                return
            if not r.get("ok"):
                messagebox.showerror("Office Convert", str(r.get("error") or "Failed."), parent=self)
                try:
                    self._append_log(f"Office single failed -> {r.get('error')}")
                except Exception:
                    pass
                return
            if r.get("skipped"):
                messagebox.showinfo("Office Convert", "Output already exists (skipped).", parent=self)
                return
            messagebox.showinfo("Office Convert", f"Converted to .{r.get('fmt')}.", parent=self)
            try:
                if r.get("fallback"):
                    self._append_log(f"Office single (fallback PDF->DOCX) -> {r.get('out')}")
                else:
                    self._append_log(f"Office single -> {r.get('out')}")
            except Exception:
                pass
            self._update_office_single_preview()

        self._run_background_task(title=f"Converting: {inp.name}…", worker=worker, on_done=on_done)

    def _open_media_editor(self):
        inp_raw = (self.single_input_path.get() or "").strip()
        if not inp_raw:
            messagebox.showwarning("Advanced Editor", "Pick a media file first.", parent=self)
            return
        inp = Path(inp_raw)
        if not inp.exists() or not inp.is_file():
            messagebox.showwarning("Advanced Editor", "Selected media file does not exist.", parent=self)
            return

        ext = inp.suffix.lower()
        video_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
        audio_exts = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".alac", ".aiff", ".ape"}

        try:
            if ext in video_exts:
                import subprocess
                import sys
                import json

                root = Path(__file__).resolve().parents[1]
                p_lit = json.dumps(str(inp))
                code = (
                    "import sys; from PySide6.QtWidgets import QApplication; "
                    "from core.settings_manager import SettingsManager; from core.ai_manager import AIManager; "
                    "from gui.video_editor_dialog import VideoEditorDialog; "
                    "app=QApplication(sys.argv); s=SettingsManager(); ai=AIManager(s.app_folder, s); "
                    f"dlg=VideoEditorDialog(None, ai, initial_file=({p_lit} or None)); "
                    "app.setQuitOnLastWindowClosed(True); dlg.show(); sys.exit(app.exec())"
                )
                subprocess.Popen([sys.executable, "-c", code], cwd=str(root))
                return
            if ext in audio_exts:
                from gui.audio_editor_dialog import AudioEditorDialog

                AudioEditorDialog(self, ai_manager=self.ai_manager, initial_file=inp)
                return

            messagebox.showinfo(
                "Advanced Editor",
                "This file type isn't supported in the editor yet.\n\nTry converting it first, then open the editor.",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Advanced Editor", str(e), parent=self)

    def _run_convert_media(self):
        if not get_ffmpeg_exe():
            messagebox.showerror("Media Conversion", "ffmpeg not available. Install imageio-ffmpeg.", parent=self)
            return
        folder = self._target_folder()
        fmt = (self.media_format.get() or "mp3").strip().lower()
        out_sub = (self.media_out_sub.get() or "Converted_Media").strip()
        source_sub = self._normalize_subfolder(self.media_source_sub.get())
        if source_sub == "__invalid__":
            messagebox.showerror("Media Conversion", "Invalid source subfolder. Use a path inside the Target folder.", parent=self)
            return
        output_root = (self.media_output_root.get() or "target").strip().lower()
        bitrate = (self.media_bitrate.get() or "").strip()
        if bitrate and bitrate.isdigit():
            bitrate = f"{bitrate}k"
        bitrate = bitrate or None
        video_crf = (self.media_video_crf.get() or "").strip() or None
        use_gpu = bool(getattr(self, "media_use_gpu", ctk.BooleanVar(value=False)).get())

        def worker(cancel_ev):
            state = {"cur": 0, "total": 0, "path": None}

            def per(cur, total, path):
                state["cur"] = int(cur or 0)
                state["total"] = int(total or 0)
                state["path"] = Path(path) if path else None
                frac = 0.0 if total <= 0 else float(cur) / float(total)
                def ui():
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(max(0.0, min(1.0, frac)))
                    self.task_percent_var.set(f"{frac:.0%}")
                    self._set_status(f"Media {cur}/{total}: {Path(path).name}")
                self.after(0, ui)

            def per_file(path, frac_in_file: float):
                try:
                    cur = int(state.get("cur") or 0)
                    total = int(state.get("total") or 0)
                    if total <= 0 or cur <= 0:
                        return
                    overall = (float(cur - 1) + max(0.0, min(1.0, float(frac_in_file)))) / float(total)
                except Exception:
                    return

                def ui():
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(max(0.0, min(1.0, overall)))
                    self.task_percent_var.set(f"{overall:.0%}")
                    self._set_status(f"Media {cur}/{total}: {Path(path).name}")

                self.after(0, ui)

            return convert_media_in_folder(
                folder,
                source_subfolder=source_sub,
                include_subfolders=bool(self.media_include_sub.get()),
                output_format=fmt,
                output_subfolder=out_sub,
                output_root="source" if output_root == "source" else "target",
                preserve_structure=bool(self.media_preserve_structure.get()),
                overwrite=bool(self.media_overwrite.get()),
                audio_bitrate=bitrate,
                video_crf=video_crf,
                video_codec=str(getattr(self, "media_video_codec", ctk.StringVar(value="h264")).get() or "h264").strip().lower(),
                scale_height=(720 if getattr(self, "media_scale", ctk.StringVar(value="keep")).get() == "720p" else 1080 if getattr(self, "media_scale", ctk.StringVar(value="keep")).get() == "1080p" else 2160 if getattr(self, "media_scale", ctk.StringVar(value="keep")).get() == "4k" else None),
                audio_bitrate_mode="cbr" if fmt == "mp3" else None,
                preserve_metadata=True,
                preserve_cover_art=bool(self.media_preserve_cover.get()),
                progress_cb=per,
                file_progress_cb=per_file,
                cancel_event=cancel_ev,
                use_gpu=use_gpu,
            )

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Media Conversion", err, parent=self)
                return
            r = result
            if not r or not getattr(r, "ok", False):
                messagebox.showerror("Media Conversion", getattr(r, "message", "Failed."), parent=self)
                return
            messagebox.showinfo("Media Conversion", r.message, parent=self)
            self._append_log(f"Convert Media -> {r.output_dir} (converted={r.converted}, skipped={r.skipped})")

        self._run_background_task(title="Converting media…", worker=worker, on_done=on_done)

    def _run_convert_single_media(self):
        if not get_ffmpeg_exe():
            messagebox.showerror("Media Conversion", "ffmpeg not available. Install imageio-ffmpeg.", parent=self)
            return

        folder = self._target_folder()
        inp_raw = (self.single_input_path.get() or "").strip()
        if not inp_raw:
            messagebox.showerror("Single Conversion", "Pick a media file first.", parent=self)
            return
        inp = Path(inp_raw)
        if not inp.exists():
            messagebox.showerror("Single Conversion", "Selected input file does not exist.", parent=self)
            return

        fmt = (self.single_format.get() or "mp3").strip().lower()
        out_sub = (self.single_out_sub.get() or "Converted_Media").strip() or "Converted_Media"
        out_root = (getattr(self, "single_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
        out_base = folder if out_root == "target" else inp.parent
        out_dir = out_base / out_sub
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{inp.stem}.{fmt}"

        bitrate = (self.single_bitrate.get() or "").strip()
        if bitrate and bitrate.isdigit():
            bitrate = f"{bitrate}k"
        bitrate = bitrate or None

        video_crf = (getattr(self, "single_video_crf", ctk.StringVar(value="20")).get() or "").strip() or None
        use_gpu = bool(getattr(self, "single_use_gpu", ctk.BooleanVar(value=False)).get())
        video_codec = str(getattr(self, "single_video_codec", ctk.StringVar(value="h264")).get() or "h264").strip().lower()
        scale_choice = str(getattr(self, "single_scale", ctk.StringVar(value="keep")).get() or "keep")
        scale_height = 720 if scale_choice == "720p" else 1080 if scale_choice == "1080p" else 2160 if scale_choice == "4k" else None

        def worker(cancel_ev):
            def per_single(frac: float):
                try:
                    frac = max(0.0, min(1.0, float(frac)))
                except Exception:
                    frac = 0.0

                def ui():
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(frac)
                    self.task_percent_var.set(f"{frac:.0%}")
                    self._set_status(f"Converting: {inp.name} ({frac:.0%})")

                self.after(0, ui)

            return convert_media_file(
                inp,
                output_path=out_path,
                overwrite=bool(self.single_overwrite.get()),
                audio_bitrate=bitrate,
                video_crf=video_crf,
                video_codec=video_codec,
                scale_height=scale_height,
                use_gpu=use_gpu,
                preserve_metadata=True,
                preserve_cover_art=bool(self.single_preserve_cover.get()),
                cancel_event=cancel_ev,
                progress_cb=per_single,
            )

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Single Conversion", err, parent=self)
                return
            r = result
            if not r or not getattr(r, "ok", False):
                messagebox.showerror("Single Conversion", getattr(r, "message", "Failed."), parent=self)
                return
            messagebox.showinfo("Single Conversion", r.message, parent=self)
            self._append_log(f"Single convert -> {out_path}")

        self._run_background_task(title=f"Converting: {inp.name}…", worker=worker, on_done=on_done)

    def _run_zip_folder(self):
        folder = self._target_folder()
        src_sub = self._normalize_subfolder(getattr(self, "zip_source_sub", ctk.StringVar(value="")).get())
        if src_sub == "__invalid__":
            messagebox.showerror("Create Archive", "Invalid source subfolder. Use a path inside the Target folder.", parent=self)
            return
        src_folder = folder / src_sub if src_sub else folder

        fmt = (getattr(self, "zip_format", ctk.StringVar(value="zip")).get() or "zip").strip().lower()
        base = (getattr(self, "zip_name", ctk.StringVar(value="Archive")).get() or "Archive").strip() or "Archive"
        ext = ".zip" if fmt == "zip" else ".7z" if fmt == "7z" else ".tar.gz" if fmt == "tar.gz" else ".tar.xz" if fmt == "tar.xz" else ".tar.bz2" if fmt == "tar.bz2" else ".zip"
        name = base + ext
        if bool(getattr(self, "zip_timestamp", ctk.BooleanVar(value=False)).get()):
            from datetime import datetime
            if name.lower().endswith(".tar.gz"):
                stem = name[:-7]
                suffix = ".tar.gz"
            elif name.lower().endswith(".tar.xz"):
                stem = name[:-7]
                suffix = ".tar.xz"
            elif name.lower().endswith(".tar.bz2"):
                stem = name[:-8]
                suffix = ".tar.bz2"
            else:
                stem = Path(name).stem
                suffix = Path(name).suffix or ".zip"
            name = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"

        out_root = (getattr(self, "zip_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
        out_base = folder if out_root == "target" else src_folder
        out_zip = out_base / name
        split_enabled = bool(getattr(self, "zip_split", ctk.BooleanVar(value=False)).get())
        part_mb_raw = (getattr(self, "zip_part_mb", ctk.StringVar(value="100")).get() or "").strip()
        part_bytes = None
        if split_enabled:
            try:
                part_mb = float(part_mb_raw)
                part_bytes = int(part_mb * 1024 * 1024)
            except Exception:
                messagebox.showerror("Create Archive", "Invalid part size MB.", parent=self)
                return

        def worker(cancel_ev):
            def per(cur, total, path):
                frac = 0.0 if total <= 0 else float(cur) / float(total)

                def ui():
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(max(0.0, min(1.0, frac)))
                    self.task_percent_var.set(f"{frac:.0%}")
                    self._set_status(f"Zipping {cur}/{total}: {Path(path).name}")

                self.after(0, ui)

            if fmt == "zip" and not split_enabled:
                return zip_folder_with_progress(
                    src_folder,
                    zip_path=out_zip,
                    include_subfolders=bool(self.zip_include_sub.get()),
                    overwrite=bool(self.zip_overwrite.get()),
                    progress_cb=per,
                    cancel_event=cancel_ev,
                )
            return create_archive(
                src_folder,
                archive_path=out_zip,
                fmt=fmt,
                include_subfolders=bool(self.zip_include_sub.get()),
                overwrite=bool(self.zip_overwrite.get()),
                progress_cb=per,
                cancel_event=cancel_ev,
                part_size_bytes=part_bytes,
            )

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Create Archive", err, parent=self)
                return
            r = result
            if not r or not getattr(r, "ok", False):
                messagebox.showerror("Create Archive", getattr(r, "message", "Failed."), parent=self)
                return
            messagebox.showinfo("Create Archive", r.message, parent=self)
            if getattr(r, "parts_dir", None):
                self._append_log(f"Archive parts -> {r.parts_dir}")
            else:
                self._append_log(f"Archive -> {r.output_path}")

        self._run_background_task(title="Creating ZIP…", worker=worker, on_done=on_done)

    def _run_unzip(self):
        folder = self._target_folder()
        inp = self._resolve_input(self.unzip_input.get())
        if not inp:
            messagebox.showerror("Extract Archive", "Select an archive file.", parent=self)
            return
        out_name = (getattr(self, "unzip_out_sub", ctk.StringVar(value="Extracted")).get() or "Extracted").strip() or "Extracted"
        out_root = (getattr(self, "unzip_output_root", ctk.StringVar(value="target")).get() or "target").strip().lower()
        out_base = folder if out_root == "target" else inp.parent
        out_dir = out_base / out_name

        def worker(cancel_ev):
            def per(cur, total, name):
                frac = 0.0 if total <= 0 else float(cur) / float(total)

                def ui():
                    if not getattr(self, "_task_determinate", False):
                        try:
                            self.task_progress.stop()
                            self.task_progress.configure(mode="determinate")
                        except Exception:
                            pass
                        self._task_determinate = True
                    self.task_progress.set(max(0.0, min(1.0, frac)))
                    self.task_percent_var.set(f"{frac:.0%}")
                    self._set_status(f"Extracting {cur}/{total}: {Path(name).name}")

                self.after(0, ui)

            if inp.suffix.lower() == ".zip" and not (inp.suffix[1:].isdigit() and inp.parent.name.endswith(".parts")):
                return unzip_archive_with_progress(
                    inp,
                    output_dir=out_dir,
                    overwrite=bool(self.unzip_overwrite.get()),
                    progress_cb=per,
                    cancel_event=cancel_ev,
                )
            return extract_archive(
                inp,
                output_dir=out_dir,
                overwrite=bool(self.unzip_overwrite.get()),
                progress_cb=per,
                cancel_event=cancel_ev,
            )

        def on_done(result, err):
            self._set_status("Ready")
            if err:
                messagebox.showerror("Extract Archive", err, parent=self)
                return
            r = result
            if not r or not getattr(r, "ok", False):
                messagebox.showerror("Extract Archive", getattr(r, "message", "Failed."), parent=self)
                return
            messagebox.showinfo("Extract Archive", r.message, parent=self)
            self._append_log(f"Extract -> {r.output_path}")

        self._run_background_task(title="Extracting…", worker=worker, on_done=on_done)

    def _run_remove_pages(self):
        folder = self._target_folder()
        inp = self._resolve_input(self.pdf_source.get())
        if not inp:
            messagebox.showerror("Remove Pages", "Select an input PDF (PDF Source).", parent=self)
            return
        ranges = simpledialog.askstring("Remove Pages", "Enter pages to remove (e.g. 2,5-7):", parent=self)
        if not ranges:
            return
        out_pdf = folder / f"{inp.stem}_removed_pages.pdf"
        try:
            self._set_status("Removing pages…")
            r = remove_pages(inp, output_pdf=out_pdf, remove_ranges=ranges, overwrite=True)
            messagebox.showinfo("Remove Pages", r.message, parent=self)
            self._append_log(f"Remove pages -> {out_pdf}")
        except Exception as e:
            messagebox.showerror("Remove Pages", str(e), parent=self)
        finally:
            self._set_status("Ready")


class FileToolsView(_FileToolsUI, ctk.CTkFrame):
    """Embeddable File Tools view (used in MainWindow)."""

    def __init__(self, parent, ai_manager=None, settings_manager=None):
        super().__init__(parent, fg_color="transparent")
        self._build_ui(self.winfo_toplevel(), ai_manager=ai_manager, settings_manager=settings_manager, embedded=True)


class FileToolsDialog(_FileToolsUI, ctk.CTkToplevel):
    """Standalone window wrapper (kept for compatibility)."""

    def __init__(self, parent, ai_manager=None, settings_manager=None):
        super().__init__(parent)
        self.title("Fylorra File Tools")
        self.geometry("980x720")
        self.minsize(940, 680)
        self._build_ui(parent, ai_manager=ai_manager, settings_manager=settings_manager, embedded=False)
