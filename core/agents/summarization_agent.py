from __future__ import annotations

from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent


class SummarizationAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="summarization_agent",
            role="summarizer",
            system_prompt="You summarize documents into concise bullet points.",
            capabilities=[
                AgentCapability(
                    capability_id="summarization",
                    name="Summarization",
                    description="Condense content into key points.",
                    input_types=["text"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=20,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        doc = payload.get("document") or payload.get("text") or payload.get("raw") or ""
        user_msg = (
            "Summarize the content into 5-10 bullet points. Keep it concise.\n\n"
            f"Content:\n{doc}"
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=600,
            temperature=0.2,
        )
        if not res.ok:
            return res
        text = str(res.data.get("text") or "")
        return AgentResult(ok=True, data={"summary": text})
