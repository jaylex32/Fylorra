import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
from datetime import datetime


class ScheduledTasksDialog(ctk.CTkToplevel):
    def __init__(self, parent, monitor_manager):
        super().__init__(parent)
        self.title("Scheduled Tasks")
        self.geometry("1000x650")
        self.minsize(880, 520)

        self._app_root = parent
        self.monitor_manager = monitor_manager

        self._build_ui()
        self._bring_to_front()
        self.refresh()

    def _bring_to_front(self):
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x")
        title = ctk.CTkLabel(
            header,
            text="Scheduled Tasks",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            anchor="w",
        )
        title.pack(side="left")

        btns = ctk.CTkFrame(header, fg_color="transparent")
        btns.pack(side="right")
        ctk.CTkButton(btns, text="Refresh", width=120, command=self.refresh).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="Close", width=120, fg_color="#444", command=self.destroy).pack(
            side="right", padx=(8, 0)
        )

        info = ctk.CTkLabel(
            outer,
            text="Time-based tasks run only while Fylorra is open. They are saved to your profile folder.",
            text_color="gray",
            anchor="w",
        )
        info.pack(fill="x", pady=(2, 10))

        try:
            path = getattr(self.monitor_manager.settings_manager, "scheduled_tasks_file", None)
            if path:
                ctk.CTkLabel(outer, text=f"Saved to: {path}", text_color="gray", anchor="w").pack(fill="x", pady=(0, 10))
        except Exception:
            pass

        self.scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

    def refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        tasks = []
        try:
            tasks = list(self.monitor_manager.scheduled_tasks.list_tasks() or [])
        except Exception:
            tasks = []

        if not tasks:
            ctk.CTkLabel(self.scroll, text="No scheduled tasks yet.", text_color="gray").pack(anchor="w", pady=12, padx=6)
            return

        for t in tasks:
            self._render_task_card(t)

    def _render_task_card(self, t):
        card = ctk.CTkFrame(self.scroll, fg_color="#2b2b2b", corner_radius=10)
        card.pack(fill="x", padx=6, pady=6)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 6))

        enabled_var = ctk.BooleanVar(value=bool(getattr(t, "enabled", True)))

        def toggle_enabled():
            try:
                t.enabled = bool(enabled_var.get())
                self.monitor_manager.scheduled_tasks.upsert_task(t)
            except Exception:
                pass

        cb = ctk.CTkCheckBox(top, text="", variable=enabled_var, command=toggle_enabled, width=22)
        cb.pack(side="left", padx=(0, 8))

        title = ctk.CTkLabel(
            top,
            text=str(getattr(t, "title", "Scheduled Task")),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        )
        title.pack(side="left", fill="x", expand=True)

        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.pack(side="right")

        def run_now():
            ok = False
            try:
                ok = bool(self.monitor_manager.scheduled_tasks.run_now(getattr(t, "task_id", "")))
            except Exception:
                ok = False
            info = ""
            try:
                info = str(getattr(self.monitor_manager.action_engine, "last_action_info", "") or "")
            except Exception:
                info = ""
            try:
                msg = "Task completed successfully." if ok else "Task completed with errors."
                if info:
                    msg += f"\n\n{info}"
                messagebox.showinfo("Run Now", msg, parent=self)
            except Exception:
                pass
            self.refresh()

        def delete_task():
            if not messagebox.askyesno("Delete Task?", "Delete this scheduled task?", parent=self):
                return
            try:
                self.monitor_manager.scheduled_tasks.delete_task(getattr(t, "task_id", ""))
            except Exception:
                pass
            self.refresh()

        ctk.CTkButton(actions, text="Run Now", width=120, command=run_now).pack(side="right", padx=(8, 0))
        ctk.CTkButton(actions, text="Delete", width=120, fg_color="#6b2b2b", hover_color="#853838", command=delete_task).pack(
            side="right", padx=(8, 0)
        )

        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(fill="x", padx=10, pady=(0, 10))

        schedule = getattr(t, "schedule", {}) or {}
        action_type = (getattr(t, "action_type", "") or "").upper()
        target = str(getattr(t, "target_path", "") or "")
        last_run = getattr(t, "last_run_iso", None)
        try:
            next_run = t.next_run(now=datetime.now())
            next_s = next_run.strftime("%Y-%m-%d %H:%M") if next_run else "—"
        except Exception:
            next_s = "—"

        details = [
            f"Action: {action_type}",
            f"Schedule: {schedule}",
            f"Target: {target}",
            f"Next run: {next_s}",
            f"Last run: {last_run or '—'}",
        ]

        ctk.CTkLabel(meta, text="\n".join(details), text_color="gray", justify="left", anchor="w").pack(
            side="left", fill="x", expand=True
        )
