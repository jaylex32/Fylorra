from __future__ import annotations

import json
import re
from typing import Any

from core.pipeline.agent import PipelineAgent, AgentCapability, AgentResult


class _LLMBaseAgent(PipelineAgent):
    def _get_ai(self, context):
        try:
            return context.services.get("ai_manager")
        except Exception:
            return None

    def _resolve_model_kind(self, context) -> str:
        """
        Determine which model kind ("vision" | "text") to use for this workflow run.

        Priority:
        1) Explicit workflow override via context.initial_parameters["workflow_model_kind"]
        2) Saved workflow setting automation_workflows.model_preference ("vision" | "text" | "auto")
        3) Heuristic: if any source files look like images -> vision else text
        """
        try:
            params = context.initial_parameters or {}
        except Exception:
            params = {}

        requested = str(params.get("workflow_model_kind") or "").strip().lower()
        if requested in ("vision", "text"):
            return requested

        pref = ""
        try:
            settings = (context.services or {}).get("settings")
            wf_settings = settings.get_workflow_settings() if settings else {}
            pref = str((wf_settings or {}).get("model_preference") or "").strip().lower()
        except Exception:
            pref = ""

        if pref in ("vision", "text"):
            return pref

        # "auto" or unset: use a simple heuristic (images => vision, otherwise text)
        try:
            source_files = params.get("source_files") or []
            image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
            for p in source_files:
                s = str(p or "")
                dot = s.rfind(".")
                ext = s[dot:].lower() if dot != -1 else ""
                if ext in image_exts:
                    return "vision"
        except Exception:
            pass

        return "text"

    def _run_llm(
        self,
        *,
        context,
        system_prompt: str,
        user_message: str,
        response_format: str = "text",
        max_tokens: int = 600,
        temperature: float | None = None,
    ) -> AgentResult:
        ai = self._get_ai(context)
        if not ai:
            return AgentResult(ok=False, message="AI is not available.")

        model_kind = "text"
        try:
            model_kind = self._resolve_model_kind(context)
        except Exception:
            model_kind = "text"

        if not getattr(ai, "is_ready", False):
            try:
                if hasattr(ai, "ensure_kind"):
                    ai.ensure_kind(model_kind)
            except Exception:
                pass
        if not getattr(ai, "is_ready", False):
            return AgentResult(ok=False, message="AI model not loaded.")
        try:
            override = None
            try:
                override = (context.initial_parameters or {}).get("workflow_max_tokens")
            except Exception:
                override = None
            if not override:
                try:
                    settings = (context.services or {}).get("settings")
                    wf_settings = settings.get_workflow_settings() if settings else {}
                    override = (wf_settings or {}).get("max_output_tokens")
                except Exception:
                    override = None
            if override:
                override = int(override)
                if override > 0:
                    max_tokens = override
        except Exception:
            pass
        try:
            resp = ai.execute_with_context(
                system_prompt=system_prompt,
                user_message=user_message,
                context=None,
                response_format=response_format,
                max_tokens=max_tokens,
                model_kind=model_kind,
                temperature=temperature,
            )
        except Exception as e:
            return AgentResult(ok=False, message=str(e))

        if not resp.get("ok"):
            return AgentResult(ok=False, message=str(resp.get("error") or "AI call failed."))
        return AgentResult(ok=True, data=resp, raw_output=resp)


def _safe_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    raw = str(text).strip()
    if not raw:
        return {}

    def _try_load(candidate: str) -> dict[str, Any]:
        try:
            data = json.loads(candidate)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    # Fast path: direct JSON.
    loaded = _try_load(raw)
    if loaded:
        return loaded

    # Strip common Markdown code fences.
    fenced = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    loaded = _try_load(fenced)
    if loaded:
        return loaded

    # Extract the first JSON object from a larger response.
    start = fenced.find("{")
    end = fenced.rfind("}")
    if start != -1 and end != -1 and end > start:
        loaded = _try_load(fenced[start : end + 1])
        if loaded:
            return loaded

    return {}
