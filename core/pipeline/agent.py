from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentCapability:
    capability_id: str
    name: str
    description: str
    input_types: list[str]
    output_types: list[str]
    requires_internet: bool
    estimated_time_seconds: int


@dataclass(frozen=True)
class AgentResult:
    ok: bool
    data: dict[str, Any] | None = None
    message: str = ""
    raw_output: Any | None = None


class PipelineAgent(ABC):
    def __init__(
        self,
        *,
        agent_id: str,
        role: str,
        system_prompt: str,
        capabilities: list[AgentCapability],
        config: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = str(agent_id)
        self.role = str(role)
        self.system_prompt = str(system_prompt or "")
        self.capabilities = list(capabilities or [])
        self.config = dict(config or {})

    @abstractmethod
    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        raise NotImplementedError

    def validate_input(self, context, inputs: dict[str, Any] | None = None) -> bool:
        return True

    def transform_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"text": "" if raw_output is None else str(raw_output)}
