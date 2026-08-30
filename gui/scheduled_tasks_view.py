import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime


class ScheduledTasksView(ctk.CTkFrame):
    """
    In-page view for Scheduled Tasks (used in MainWindow).
    The dialog version remains available as a separate window.
    """

    def __init__(self, parent, monitor_manager):
        super().__init__(parent, fg_color="transparent")
        self.monitor_manager = monitor_manager
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=6, pady=6)

        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="Scheduled Tasks",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            anchor="w",
        ).pack(side="left")

        ctk.CTkButton(header, text="Refresh", width=120, command=self.refresh).pack(side="right")

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

        ctk.CTkCheckBox(top, text="", variable=enabled_var, command=toggle_enabled, width=22).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            top,
            text=str(getattr(t, "title", "Scheduled Task")),
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.pack(side="right")

        def run_now():
            ok = False
            try:
                ok = bool(self.monitor_manager.scheduled_tasks.run_now(getattr(t, "task_id", "")))
            except Exception:
                ok = False

            msg = "Completed successfully." if ok else "Completed with errors."
            extra = ""
            try:
                extra = getattr(self.monitor_manager.action_engine, "last_action_info", "") or ""
            except Exception:
                extra = ""
            if extra:
                msg = f"{msg}\n\n{extra}"
            try:
                messagebox.showinfo("Scheduled Task", msg, parent=self.winfo_toplevel())
            except Exception:
                pass
            self.refresh()

        def delete_task():
            try:
                if not messagebox.askyesno("Delete Task", "Delete this scheduled task?", parent=self.winfo_toplevel()):
                    return
            except Exception:
                return
            try:
                self.monitor_manager.scheduled_tasks.delete_task(getattr(t, "task_id", ""))
            except Exception:
                pass
            self.refresh()

        ctk.CTkButton(actions, text="Run now", width=120, command=run_now).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Delete", width=100, fg_color="#444", command=delete_task).pack(side="left")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=10, pady=(0, 10))

        def fmt_dt(ts):
            try:
                if not ts:
                    return "-"
                return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return "-"

        meta = [
            ("Schedule", str(getattr(t, "schedule", "-"))),
            ("Next", fmt_dt(getattr(t, "next_run_ts", None))),
            ("Last", fmt_dt(getattr(t, "last_run_ts", None))),
        ]

        for label, value in meta:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text=f"{label}:", width=80, anchor="w", text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=value, anchor="w").pack(side="left")
