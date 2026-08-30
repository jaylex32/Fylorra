from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.pipeline.agent import PipelineAgent, AgentResult
from core.pipeline.context import PipelineContext


@dataclass(frozen=True)
class StageConfig:
    approval_required: bool = False
    approval_message: str = "Review output before continuing?"
    retry_on_failure: bool = True
    max_retries: int = 2
    fallback_agent: str | None = None
    timeout_seconds: int = 300
    skip_if_previous_failed: bool = False
    condition: dict | None = None


@dataclass(frozen=True)
class StageResult:
    success: bool
    data: Any | None = None
    error: str = ""
    aborted: bool = False
    abort_reason: str | None = None
    skipped: bool = False


def _get_nested(obj: Any, path: str) -> Any:
    cur = obj
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur.get(part)
            continue
        return None
    return cur


def _eval_condition(ctx: PipelineContext, cond: dict | None) -> bool:
    if not cond:
        return True
    field = str(cond.get("field") or "")
    if not field:
        return True
    op = str(cond.get("operator") or cond.get("op") or "equals").lower()
    expected = cond.get("value")
    actual = _get_nested(ctx.stage_outputs, field)
    if op in {"equals", "eq"}:
        return actual == expected
    if op in {"ne", "not_equals"}:
        return actual != expected
    if op in {"gt", "greater"}:
        try:
            return float(actual) > float(expected)
        except Exception:
            return False
    if op in {"gte", "ge"}:
        try:
            return float(actual) >= float(expected)
        except Exception:
            return False
    if op in {"lt", "less"}:
        try:
            return float(actual) < float(expected)
        except Exception:
            return False
    if op in {"lte", "le"}:
        try:
            return float(actual) <= float(expected)
        except Exception:
            return False
    if op == "contains":
        try:
            return expected in actual
        except Exception:
            return False
    return True


class PipelineStage:
    def __init__(
        self,
        stage_id: str,
        name: str,
        agent: PipelineAgent,
        config: StageConfig,
        input_mapping: dict[str, Any] | None = None,
    ) -> None:
        self.stage_id = str(stage_id)
        self.name = str(name)
        self.agent = agent
        self.config = config
        self.input_mapping = dict(input_mapping or {})

    def should_execute(self, context: PipelineContext) -> bool:
        return _eval_condition(context, self.config.condition)

    def execute(
        self,
        context: PipelineContext,
        progress_callback: Callable[[str, int], None],
        approval_callback: Callable[[dict], bool] | None = None,
    ) -> StageResult:
        attempt = 0
        last_err = ""
        while attempt < max(1, int(self.config.max_retries or 1)):
            if context.should_abort:
                return StageResult(success=False, aborted=True, abort_reason=context.abort_reason or "Cancelled")
            try:
                agent_input = self._prepare_input(context)
                progress_callback(f"Running {self.name}...", 0)
                res = self.agent.execute(context, agent_input)
                if not res.ok:
                    raise RuntimeError(res.message or "Agent failed.")

                try:
                    from core.pipeline.output_validation import coerce_output

                    coerced = coerce_output(self.agent.agent_id, res.data or {})
                    if coerced is not None:
                        res = AgentResult(
                            ok=res.ok,
                            data=coerced if isinstance(coerced, dict) else res.data,
                            message=res.message,
                            raw_output=res.raw_output,
                        )
                except Exception:
                    pass

                if self.config.approval_required and approval_callback:
                    context.approval_pending = True
                    payload = {
                        "pipeline_id": context.pipeline_id,
                        "stage_id": self.stage_id,
                        "stage_name": self.name,
                        "message": self.config.approval_message,
                        "output": res.data or {},
                    }
                    context.approval_data = payload
                    approved = approval_callback(payload)
                    context.approval_pending = False
                    context.approval_data = None
                    if not approved:
                        return StageResult(
                            success=False,
                            aborted=True,
                            abort_reason="User rejected output",
                            data=res.data,
                        )

                return StageResult(success=True, data=res.data)
            except Exception as e:
                last_err = str(e)
                attempt += 1
                if not self.config.retry_on_failure or attempt >= int(self.config.max_retries or 1):
                    return StageResult(success=False, error=last_err)
        return StageResult(success=False, error=last_err or "Stage failed.")

    def _prepare_input(self, context: PipelineContext) -> dict[str, Any]:
        if self.input_mapping:
            mapped: dict[str, Any] = {}
            for agent_key, src in self.input_mapping.items():
                if isinstance(src, (list, tuple)) and len(src) == 2:
                    stage_id, field = src
                    mapped[agent_key] = _get_nested(context.stage_outputs.get(stage_id, {}), str(field))
                else:
                    mapped[agent_key] = _get_nested(context.stage_outputs, str(src))
            return mapped

        # Default: use last stage output, else initial parameters.
        if context.stage_outputs:
            last_key = list(context.stage_outputs.keys())[-1]
            last = context.stage_outputs.get(last_key)
            if isinstance(last, dict):
                return dict(last)
            return {"text": "" if last is None else str(last)}

        base = dict(context.initial_parameters or {})
        base.setdefault("user_request", context.user_request)
        return base
