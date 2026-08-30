"""
Fylorra - AI Command Dialog
Natural language → multi-step plan → preview → run.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.ai_command import plan_from_nl, run_plan
from core.workflow_actions import HeadlessCommandAction, actions_from_command_plan
from core.workflow_runner import WorkflowContext, WorkflowRunner


class _AICommandUI:
    def _init_common(self, ai_manager=None):
        self.ai_manager = ai_manager
        self.plan = None
        self.target_folder: Path | None = None

    def _top(self):
        try:
            return self.winfo_toplevel()
        except Exception:
            return self

    def _setup_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 8))

        ctk.CTkLabel(header, text="AI Command Center", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")).pack(
            side="left"
        )
        ctk.CTkLabel(
            header,
            text="Natural language → workflow plan → run (local)",
            text_color=("#a7abb3", "#a7abb3"),
        ).pack(side="left", padx=(14, 0))

        folder_panel = ctk.CTkFrame(self, corner_radius=12)
        folder_panel.pack(fill="x", padx=22, pady=(0, 12))
        folder_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(folder_panel, text="Target Folder", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(14, 8)
        )

        self.folder_var = ctk.StringVar(value="")
        self.folder_entry = ctk.CTkEntry(folder_panel, textvariable=self.folder_var, height=40, placeholder_text="Select a folder…")
        self.folder_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(14, 8))

        ctk.CTkButton(folder_panel, text="Browse", width=110, height=40, command=self._browse_folder).grid(
            row=0, column=2, sticky="e", padx=14, pady=(14, 8)
        )

        prompt_panel = ctk.CTkFrame(self, corner_radius=12)
        prompt_panel.pack(fill="x", padx=22, pady=(0, 12))

        ctk.CTkLabel(prompt_panel, text="What do you want to do?", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).pack(
            anchor="w", padx=14, pady=(14, 6)
        )

        self.prompt = ctk.CTkTextbox(prompt_panel, height=110)
        self.prompt.pack(fill="x", padx=14, pady=(0, 12))
        self.prompt.insert(
            "1.0",
            "Examples:\n"
            "- Convert all Word/Excel/PowerPoint files to PDF, then zip the folder\n"
            "- Index this folder, then find invoices from Amazon\n",
        )

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=22, pady=(0, 10))

        self.plan_btn = ctk.CTkButton(btn_row, text="Generate Plan", width=160, height=40, command=self._generate_plan)
        self.plan_btn.pack(side="left")

        self.run_btn = ctk.CTkButton(
            btn_row,
            text="Run Plan",
            width=140,
            height=40,
            state="disabled",
            command=self._run_plan,
        )
        self.run_btn.pack(side="left", padx=(10, 0))

        self.status = ctk.CTkLabel(btn_row, text="", text_color=("#a7abb3", "#a7abb3"))
        self.status.pack(side="left", padx=(14, 0))

        self.progress = ctk.CTkProgressBar(btn_row, width=220)
        self.progress.set(0.0)
        # Show only while running
        self.progress.pack_forget()

        self.plan_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.plan_frame.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        self._render_empty()

    def _render_empty(self):
        for w in self.plan_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.plan_frame,
            text="No plan yet.\n\nPick a folder, type what you want, then click “Generate Plan”.",
            text_color=("#a7abb3", "#a7abb3"),
            justify="center",
        ).pack(pady=80)

    def _browse_folder(self):
        folder = filedialog.askdirectory(parent=self._top(), title="Select target folder")
        if folder:
            self.folder_var.set(folder)

    def _generate_plan(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("No folder", "Select a target folder first.", parent=self)
            return
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            messagebox.showerror("Invalid folder", "That folder does not exist.", parent=self)
            return
        instruction = self.prompt.get("1.0", "end").strip()
        if not instruction:
            return

        self.target_folder = p
        self.plan_btn.configure(state="disabled")
        self.run_btn.configure(state="disabled")
        self.status.configure(text="Planning…")

        def run():
            try:
                plan = plan_from_nl(self.ai_manager, instruction, target_folder=p)
                self.plan = plan
                self.after(0, lambda: self._render_plan(plan))
                self.after(0, lambda: self.run_btn.configure(state="normal"))
                self.after(0, lambda: self.status.configure(text=f"Plan ready: {plan.intent_summary}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Plan failed", str(e), parent=self))
                self.after(0, self._render_empty)
                self.plan = None
            finally:
                self.after(0, lambda: self.plan_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _render_plan(self, plan):
        for w in self.plan_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self.plan_frame,
            text=plan.intent_summary,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 12))

        for i, step in enumerate(plan.steps, start=1):
            card = ctk.CTkFrame(self.plan_frame, corner_radius=12)
            card.pack(fill="x", pady=8)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(card, text=f"Step {i}: {step.tool}", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).grid(
                row=0, column=0, sticky="w", padx=14, pady=(12, 4)
            )
            ctk.CTkLabel(card, text=step.description, text_color=("#a7abb3", "#a7abb3")).grid(
                row=1, column=0, sticky="w", padx=14, pady=(0, 10)
            )
            ctk.CTkLabel(card, text=str(step.args), text_color=("#a7abb3", "#a7abb3")).grid(
                row=2, column=0, sticky="w", padx=14, pady=(0, 12)
            )

    def _run_plan(self):
        if not self.plan or not self.target_folder:
            return

        self.run_btn.configure(state="disabled")
        self.plan_btn.configure(state="disabled")
        self.status.configure(text="Running…")
        self.progress.set(0.0)
        self.progress.pack(side="left", padx=(14, 0))

        ui_actions, headless_plan = actions_from_command_plan(self.plan)

        def finish_with_report(report: dict):
            self._show_report(report)
            self.plan_btn.configure(state="normal")
            self.run_btn.configure(state="normal")
            self.status.configure(text="")
            self.progress.set(0.0)
            try:
                self.progress.pack_forget()
            except Exception:
                pass

        def run_headless_only():
            try:
                def emit(msg: str, frac: float):
                    def ui():
                        self.status.configure(text=f"{msg} ({frac:.0%})")
                        self.progress.set(max(0.0, min(1.0, float(frac))))

                    self.after(0, ui)

                report = run_plan(headless_plan, target_folder=self.target_folder, ai_manager=self.ai_manager, progress=emit)
                self.after(0, lambda: finish_with_report(report))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Run failed", str(e), parent=self._top()))
                self.after(0, lambda: self.plan_btn.configure(state="normal"))
                self.after(0, lambda: self.run_btn.configure(state="normal"))
                self.after(0, lambda: self.status.configure(text=""))
                self.after(0, lambda: self.progress.set(0.0))
                self.after(0, lambda: self.progress.pack_forget())

        if not ui_actions:
            threading.Thread(target=run_headless_only, daemon=True).start()
            return

        # Run UI actions first (dialogs), then headless steps.
        ctx = WorkflowContext(
            parent=self._top(),
            ai_manager=self.ai_manager,
            target_folder=self.target_folder,
            include_subfolders=True,
        )
        runner = WorkflowRunner(ctx)

        actions = list(ui_actions)
        if headless_plan.steps:
            actions.append(HeadlessCommandAction(action_id="headless", title="Background Steps", plan=headless_plan))

        def on_progress(msg: str, frac: float):
            self.status.configure(text=f"{msg} ({frac:.0%})")
            self.progress.set(max(0.0, min(1.0, float(frac))))

        def on_done(reports):
            # Convert reports into the same report format used by _show_report
            ok = all(r.ok for r in reports if r.action_id != "workflow")
            flat_results = []
            for r in reports:
                if r.action_id == "headless" and r.data and isinstance(r.data, dict):
                    # splice in headless results
                    flat_results.extend(r.data.get("results", []))
                else:
                    flat_results.append({"tool": r.action_id, "ok": r.ok, "error": "" if r.ok else r.message})
            report = {"ok": ok, "intent_summary": self.plan.intent_summary, "results": flat_results}
            self.after(0, lambda: finish_with_report(report))

        runner.run(actions, progress=on_progress, done=on_done)

    def _show_report(self, report: dict):
        ok = report.get("ok")
        lines = []
        for r in report.get("results", []):
            status = "OK" if r.get("ok") else "FAIL"
            tool = r.get("tool")
            detail = r.get("error") or ""
            if tool == "index_folder" and r.get("ok"):
                detail = f"indexed={r.get('indexed')}"
            elif tool == "convert_office_to_pdf" and r.get("ok"):
                detail = f"converted={r.get('converted')} skipped={r.get('skipped')} out={r.get('output_dir')}"
            elif tool == "zip_folder" and r.get("ok"):
                detail = f"zip={r.get('zip')}"
            elif tool == "unzip_archive" and r.get("ok"):
                detail = f"out={r.get('output_dir') or r.get('output')}"
            elif tool == "convert_images" and r.get("ok"):
                detail = f"converted={r.get('converted')} skipped={r.get('skipped')} out={r.get('output_dir')}"
            elif tool == "convert_media" and r.get("ok"):
                detail = f"converted={r.get('converted')} skipped={r.get('skipped')} out={r.get('output_dir')}"
            elif tool == "merge_pdfs" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "extract_pdf_pages" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "split_pdf_pages" and r.get("ok"):
                detail = f"count={r.get('count')} out={r.get('output_dir')}"
            elif tool == "split_pdf_chunks" and r.get("ok"):
                detail = f"count={r.get('count')} out={r.get('output_dir')}"
            elif tool == "split_pdf_bookmarks" and r.get("ok"):
                detail = f"count={r.get('count')} out={r.get('output_dir')}"
            elif tool == "rotate_pdf" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "remove_pdf_pages" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "reorder_pdf_pages" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "watermark_pdf" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "search_pdf_text" and r.get("ok"):
                detail = f"count={r.get('count')}"
            elif tool == "move_files" and r.get("ok"):
                detail = f"moved={r.get('moved')}"
            elif tool == "copy_files" and r.get("ok"):
                detail = f"copied={r.get('copied')}"
            elif tool == "delete_files" and r.get("ok"):
                detail = f"deleted={r.get('deleted')}"
            elif tool == "make_folder" and r.get("ok"):
                detail = f"folder={r.get('folder')}"
            elif tool == "organize_audio_by_tags" and r.get("ok"):
                detail = f"moved={r.get('moved')} out={r.get('dest_root')}"
            elif tool == "convert_media_file" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "cut_video" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "convert_excel_to_csv" and r.get("ok"):
                detail = f"out={r.get('output')}"
            elif tool == "search_index" and r.get("ok"):
                detail = f"count={r.get('count')}"
            lines.append(f"{status} {tool} {detail}".strip())

        messagebox.showinfo(
            "AI Command Run",
            ("Completed successfully.\n\n" if ok else "Completed with errors.\n\n") + "\n".join(lines),
            parent=self._top(),
        )


class AICommandView(_AICommandUI, ctk.CTkFrame):
    """Embeddable AI Command Center view (used in MainWindow)."""

    def __init__(self, parent, ai_manager=None):
        super().__init__(parent, fg_color="transparent")
        self._init_common(ai_manager)
        self._setup_ui()


class AICommandDialog(_AICommandUI, ctk.CTkToplevel):
    """Standalone window wrapper (kept for compatibility)."""

    def __init__(self, parent, ai_manager=None):
        super().__init__(parent)
        self._init_common(ai_manager)

        self.title("AI Command Center")
        self.geometry("980x720")
        self.minsize(900, 650)
        try:
            self.transient(parent)
        except Exception:
            pass

        self._setup_ui()
