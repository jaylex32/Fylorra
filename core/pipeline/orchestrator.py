from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.pipeline.context import PipelineContext
from core.pipeline.pipeline import AutomationPipeline


@dataclass
class PipelineResult:
    execution_id: str
    pipeline_id: str
    success: bool
    outputs: dict[str, Any]
    errors: list[dict]
    total_duration_seconds: float
    completed_at: str | None
    aborted: bool = False
    abort_reason: str | None = None


class PipelineOrchestrator:
    def __init__(self, ai_manager: Any, settings_manager: Any):
        self.ai_manager = ai_manager
        self.settings = settings_manager
        self.running_pipelines: dict[str, PipelineContext] = {}

    def execute_pipeline(
        self,
        pipeline: AutomationPipeline,
        initial_params: dict[str, Any],
        progress_callback: Callable[[str, int, dict], None],
        approval_callback: Callable[[dict], bool] | None,
        completion_callback: Callable[[PipelineResult], None],
    ) -> str:
        execution_id = str(uuid.uuid4())

        work_dir = self._create_workspace(execution_id)
        context = PipelineContext(
            pipeline_id=pipeline.metadata.pipeline_id,
            user_request=str(initial_params.get("user_request", "")),
            initial_parameters=dict(initial_params or {}),
            services={"ai_manager": self.ai_manager, "settings": self.settings},
            stage_outputs={},
            stage_metadata={},
            working_directory=work_dir,
            temp_files=[],
            current_stage=0,
            total_stages=len(pipeline.stages),
            should_abort=False,
            abort_reason=None,
            approval_pending=False,
            approval_data=None,
        )

        self.running_pipelines[execution_id] = context

        thread = threading.Thread(
            target=self._run_pipeline_thread,
            args=(execution_id, pipeline, context, progress_callback, approval_callback, completion_callback),
            daemon=True,
        )
        thread.start()

        return execution_id

    def _run_pipeline_thread(
        self,
        execution_id: str,
        pipeline: AutomationPipeline,
        context: PipelineContext,
        progress_callback: Callable[[str, int, dict], None],
        approval_callback: Callable[[dict], bool] | None,
        completion_callback: Callable[[PipelineResult], None],
    ) -> None:
        result = PipelineResult(
            execution_id=execution_id,
            pipeline_id=pipeline.metadata.pipeline_id,
            success=False,
            outputs={},
            errors=[],
            total_duration_seconds=0.0,
            completed_at=None,
        )

        start_time = time.time()
        try:
            total = max(1, len(pipeline.stages))
            for i, stage in enumerate(pipeline.stages):
                if context.should_abort:
                    result.aborted = True
                    result.abort_reason = context.abort_reason
                    break

                context.current_stage = i
                if not stage.should_execute(context):
                    progress_callback(
                        f"Skipping {stage.name}",
                        int((i / total) * 100),
                        {"stage": stage.name, "skipped": True},
                    )
                    continue

                # Emit a "stage started" progress event so the UI updates even if the stage
                # itself doesn't produce incremental progress messages.
                progress_callback(
                    f"Running {stage.name}...",
                    int((i / total) * 100),
                    {"stage": stage.name},
                )

                stage_start = time.time()
                stage_result = stage.execute(
                    context,
                    lambda msg, pct: progress_callback(
                        msg,
                        int((i / total) * 100) + int(float(pct) / max(1, total)),
                        {"stage": stage.name},
                    ),
                    approval_callback=approval_callback,
                )
                duration = time.time() - stage_start

                context.stage_metadata[stage.stage_id] = {
                    "duration_seconds": duration,
                    "timestamp": datetime.now().isoformat(),
                    "success": bool(stage_result.success),
                    "skipped": bool(stage_result.skipped),
                }

                if stage_result.success:
                    context.stage_outputs[stage.stage_id] = stage_result.data
                else:
                    result.errors.append(
                        {"stage": stage.name, "error": stage_result.error or "Stage failed"}
                    )
                    if stage_result.aborted:
                        result.aborted = True
                        result.abort_reason = stage_result.abort_reason
                        break
                    if stage.config.skip_if_previous_failed:
                        break

            result.success = len(result.errors) == 0 and not result.aborted
            result.outputs = dict(context.stage_outputs)
            result.total_duration_seconds = time.time() - start_time
            result.completed_at = datetime.now().isoformat()
        except Exception as e:
            result.errors.append({"stage": "orchestrator", "error": str(e)})
        finally:
            try:
                context.cleanup()
            except Exception:
                pass
            try:
                if execution_id in self.running_pipelines:
                    del self.running_pipelines[execution_id]
            except Exception:
                pass
            completion_callback(result)

    def cancel_pipeline(self, execution_id: str) -> None:
        ctx = self.running_pipelines.get(execution_id)
        if not ctx:
            return
        ctx.should_abort = True
        ctx.abort_reason = "User cancelled"

    def get_status(self, execution_id: str) -> dict | None:
        ctx = self.running_pipelines.get(execution_id)
        if not ctx:
            return None
        total = max(1, int(ctx.total_stages or 1))
        pct = int((int(ctx.current_stage) / total) * 100)
        return {
            "current_stage": ctx.current_stage,
            "total_stages": ctx.total_stages,
            "progress_percent": pct,
            "approval_pending": bool(ctx.approval_pending),
        }

    def _create_workspace(self, execution_id: str) -> Path:
        base = Path(getattr(self.settings, "app_folder", Path.home() / ".fylorra"))
        work = base / "pipelines" / "executions" / execution_id
        try:
            work.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return work
