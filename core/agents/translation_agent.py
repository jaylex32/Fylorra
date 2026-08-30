from __future__ import annotations

from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent


class TranslationAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="translation_agent",
            role="translator",
            system_prompt="You translate text accurately while preserving meaning.",
            capabilities=[
                AgentCapability(
                    capability_id="translation",
                    name="Translation",
                    description="Translate text to a target language.",
                    input_types=["text"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=30,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        text = payload.get("document") or payload.get("text") or ""
        target_lang = str(payload.get("target_language") or self.config.get("target_language") or "English")
        user_msg = (
            f"Translate the text into {target_lang}.\n"
            "Preserve formatting where possible.\n\n"
            f"Text:\n{text}"
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=1200,
            temperature=0.2,
        )
        if not res.ok:
            return res
        out = str(res.data.get("text") or "")
        return AgentResult(ok=True, data={"document": out, "language": target_lang})
