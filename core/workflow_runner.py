"""
Fylorra - Workflow Runner
Executes multi-step workflows (actions) sequentially with progress reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol


@dataclass(frozen=True)
class WorkflowContext:
    parent: Any  # CTk/Tk widget (used for .after and dialog parenting)
    ai_manager: Any
    target_folder: Path
    include_subfolders: bool = True
    file_filter: str = "all"  # reserved for future use


@dataclass(frozen=True)
class ActionReport:
    action_id: str
    ok: bool
    message: str = ""
    data: Optional[dict[str, Any]] = None


class WorkflowAction(Protocol):
    action_id: str
    title: str

    def run(
        self,
        ctx: WorkflowContext,
        *,
        progress: Callable[[str, float], None],
        done: Callable[[ActionReport], None],
    ) -> None: ...


class WorkflowRunner:
    def __init__(self, ctx: WorkflowContext):
        self.ctx = ctx
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(
        self,
        actions: list[WorkflowAction],
        *,
        progress: Optional[Callable[[str, float], None]] = None,
        done: Optional[Callable[[list[ActionReport]], None]] = None,
    ) -> None:
        reports: list[ActionReport] = []

        def emit(msg: str, frac: float) -> None:
            if progress:
                progress(msg, frac)

        def run_next(index: int) -> None:
            if self._cancelled:
                reports.append(ActionReport(action_id="workflow", ok=False, message="Cancelled"))
                if done:
                    done(reports)
                return

            if index >= len(actions):
                if done:
                    done(reports)
                return

            action = actions[index]

            def step_progress(msg: str, frac: float) -> None:
                overall = (index + frac) / max(1, len(actions))
                emit(f"{action.title}: {msg}", overall)

            def step_done(report: ActionReport) -> None:
                reports.append(report)
                # Schedule next action on UI thread.
                try:
                    self.ctx.parent.after(50, lambda: run_next(index + 1))
                except Exception:
                    run_next(index + 1)

            step_progress("Starting…", 0.0)
            try:
                action.run(self.ctx, progress=step_progress, done=step_done)
            except Exception as e:
                step_done(ActionReport(action_id=action.action_id, ok=False, message=str(e)))

        # Start on UI thread
        try:
            self.ctx.parent.after(0, lambda: run_next(0))
        except Exception:
            run_next(0)

