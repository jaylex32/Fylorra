from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.pipeline.stage import PipelineStage, StageConfig
from core.pipeline.agent import PipelineAgent
from core.agents.registry import create_agent


@dataclass(frozen=True)
class PipelineMetadata:
    pipeline_id: str
    name: str
    description: str
    category: str
    author: str
    version: str
    created_date: str
    tags: list[str]


class AutomationPipeline:
    def __init__(
        self,
        metadata: PipelineMetadata,
        stages: list[PipelineStage],
        trigger: dict | None = None,
        global_config: dict[str, Any] | None = None,
    ) -> None:
        self.metadata = metadata
        self.stages = list(stages or [])
        self.trigger = trigger
        self.global_config = dict(global_config or {})

    def validate(self) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not self.stages:
            errors.append("Pipeline has no stages.")
        for stage in self.stages:
            if not stage.stage_id:
                errors.append("Stage missing stage_id.")
            if not stage.agent:
                errors.append(f"Stage {stage.stage_id} has no agent.")
        return (len(errors) == 0), errors

    def estimate_duration(self) -> int:
        total = 0
        for stage in self.stages:
            try:
                cap = stage.agent.capabilities[0]
                total += int(cap.estimated_time_seconds)
            except Exception:
                total += 30
        return total

    def to_json(self) -> dict:
        return {
            "metadata": asdict(self.metadata),
            "stages": [self._stage_to_dict(s) for s in self.stages],
            "trigger": self.trigger,
            "global_config": self.global_config,
        }

    def _stage_to_dict(self, stage: PipelineStage) -> dict:
        return {
            "stage_id": stage.stage_id,
            "name": stage.name,
            "agent": stage.agent.agent_id,
            "config": asdict(stage.config),
            "input_mapping": stage.input_mapping,
        }

    @classmethod
    def from_json(cls, data: dict) -> "AutomationPipeline":
        try:
            from core.pipeline.models import PipelineTemplateModel

            PipelineTemplateModel.model_validate(data)
        except Exception:
            pass

        md = data.get("metadata", {})
        metadata = PipelineMetadata(
            pipeline_id=str(md.get("pipeline_id") or ""),
            name=str(md.get("name") or ""),
            description=str(md.get("description") or ""),
            category=str(md.get("category") or ""),
            author=str(md.get("author") or ""),
            version=str(md.get("version") or "1.0"),
            created_date=str(md.get("created_date") or ""),
            tags=list(md.get("tags") or []),
        )

        stages: list[PipelineStage] = []
        for s in list(data.get("stages") or []):
            agent_id = str(s.get("agent") or "")
            agent_cfg = dict(s.get("agent_config") or {})
            agent = create_agent(agent_id, agent_cfg)
            cfg_raw = dict(s.get("config") or {})
            cfg = StageConfig(**cfg_raw) if cfg_raw else StageConfig()
            st = PipelineStage(
                stage_id=str(s.get("stage_id") or agent_id),
                name=str(s.get("name") or agent_id),
                agent=agent,
                config=cfg,
                input_mapping=dict(s.get("input_mapping") or {}),
            )
            stages.append(st)

        return cls(
            metadata=metadata,
            stages=stages,
            trigger=data.get("trigger"),
            global_config=dict(data.get("global_config") or {}),
        )
