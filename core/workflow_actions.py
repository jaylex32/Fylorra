"""
Fylorra - Workflow Actions
Wrap existing tools (dialogs + headless ops) as reusable workflow actions.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.ai_command import CommandPlan, CommandStep, run_plan
from core.ai_categorizer import AICategorizer
from core.workflow_runner import ActionReport, WorkflowAction, WorkflowContext


@dataclass
class HeadlessCommandAction:
    """
    Runs a subset of ai_command steps that are safe to execute headlessly.
    """

    action_id: str
    title: str
    plan: CommandPlan

    def run(
        self,
        ctx: WorkflowContext,
        *,
        progress: Callable[[str, float], None],
        done: Callable[[ActionReport], None],
    ) -> None:
        def worker():
            try:
                def emit(msg: str, frac: float) -> None:
                    try:
                        progress(msg, frac)
                    except Exception:
                        pass

                report = run_plan(self.plan, target_folder=ctx.target_folder, ai_manager=ctx.ai_manager, progress=emit)
                ok = bool(report.get("ok"))
                done(ActionReport(action_id=self.action_id, ok=ok, message="Completed", data=report))
            except Exception as e:
                done(ActionReport(action_id=self.action_id, ok=False, message=str(e)))

        threading.Thread(target=worker, daemon=True).start()


@dataclass
class SmartRenameAction:
    action_id: str = "smart_rename"
    title: str = "Smart Rename"

    def run(self, ctx: WorkflowContext, *, progress, done) -> None:
        from gui.smart_rename_dialog import SmartRenameDialog

        def on_complete(renamed_count: int):
            done(ActionReport(action_id=self.action_id, ok=True, message=f"Renamed {renamed_count} files"))

        dialog = SmartRenameDialog(
            ctx.parent,
            ctx.ai_manager,
            [],
            on_complete,
            folder_mode=True,
            folder_path=ctx.target_folder,
        )
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()


@dataclass
class AutoCategorizeAction:
    action_id: str = "auto_categorize"
    title: str = "Auto-Categorize"

    def run(self, ctx: WorkflowContext, *, progress, done) -> None:
        from gui.ai_categorize_dialog import AICategorizeDialog

        dialog = AICategorizeDialog(ctx.parent, ctx.ai_manager, None, ctx.target_folder)
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()

        def poll_closed():
            try:
                if not dialog.winfo_exists():
                    done(ActionReport(action_id=self.action_id, ok=True, message="Completed"))
                    return
            except Exception:
                done(ActionReport(action_id=self.action_id, ok=True, message="Completed"))
                return
            ctx.parent.after(400, poll_closed)

        ctx.parent.after(400, poll_closed)


@dataclass
class SecurityScanAction:
    action_id: str = "security_scan"
    title: str = "Security Scan"

    def run(self, ctx: WorkflowContext, *, progress, done) -> None:
        from gui.ai_security_scan_dialog import AISecurityScanDialog

        categorizer = AICategorizer(ctx.ai_manager)
        dialog = AISecurityScanDialog(ctx.parent, ctx.ai_manager, categorizer, ctx.target_folder)
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()

        def poll_closed():
            try:
                if not dialog.winfo_exists():
                    done(ActionReport(action_id=self.action_id, ok=True, message="Completed"))
                    return
            except Exception:
                done(ActionReport(action_id=self.action_id, ok=True, message="Completed"))
                return
            ctx.parent.after(400, poll_closed)

        ctx.parent.after(400, poll_closed)


@dataclass
class ContentAnalysisAction:
    action_id: str = "content_analysis"
    title: str = "Content Analysis"

    def run(self, ctx: WorkflowContext, *, progress, done) -> None:
        from core.semantic_analyzer import SemanticAnalyzer
        from gui.semantic_analysis_dialog import SemanticAnalysisDialog

        semantic_analyzer = SemanticAnalyzer(ctx.ai_manager)
        dialog = SemanticAnalysisDialog(
            ctx.parent,
            semantic_analyzer,
            ctx.target_folder,
            on_action=None,
            folder_mode=True,
        )
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()

        def poll_closed():
            try:
                if not dialog.winfo_exists():
                    done(ActionReport(action_id=self.action_id, ok=True, message="Completed"))
                    return
            except Exception:
                done(ActionReport(action_id=self.action_id, ok=True, message="Completed"))
                return
            ctx.parent.after(400, poll_closed)

        ctx.parent.after(400, poll_closed)


def actions_from_command_plan(plan: CommandPlan) -> tuple[list[WorkflowAction], CommandPlan]:
    """
    Split a CommandPlan into:
    - dialog-based workflow actions
    - remaining headless plan steps (index/search/zip/convert)
    """
    dialog_tools = {"smart_rename", "auto_categorize", "security_scan", "content_analysis"}
    ui_actions: list[WorkflowAction] = []
    remaining_steps: list[CommandStep] = []

    for step in plan.steps:
        if step.tool in dialog_tools:
            if step.tool == "smart_rename":
                ui_actions.append(SmartRenameAction())
            elif step.tool == "auto_categorize":
                ui_actions.append(AutoCategorizeAction())
            elif step.tool == "security_scan":
                ui_actions.append(SecurityScanAction())
            elif step.tool == "content_analysis":
                ui_actions.append(ContentAnalysisAction())
        else:
            remaining_steps.append(step)

    remaining_plan = CommandPlan(intent_summary=plan.intent_summary, steps=remaining_steps)
    return ui_actions, remaining_plan
