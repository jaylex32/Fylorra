"""
Import-light re-exports for the pipeline package.

Avoid importing `core.pipeline.pipeline` at import time because it depends on
`core.agents.registry`, which imports agent modules that import `core.pipeline.*`.
We expose the same names via lazy `__getattr__` to prevent circular imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.pipeline.agent import AgentCapability, AgentResult, PipelineAgent
from core.pipeline.context import PipelineContext
from core.pipeline.stage import StageConfig, StageResult, PipelineStage
from core.pipeline.storage import (
    ensure_pipeline_dirs,
    install_builtin_templates,
    load_all_pipelines,
    save_custom_pipeline,
    save_execution,
)

try:  # pragma: no cover - optional dependency
    from core.pipeline.models import PipelineTemplateModel
except Exception:  # pragma: no cover - optional dependency
    PipelineTemplateModel = None


def __getattr__(name: str) -> Any:  # PEP 562
    if name in {"PipelineMetadata", "AutomationPipeline"}:
        from core.pipeline.pipeline import AutomationPipeline, PipelineMetadata

        return {"PipelineMetadata": PipelineMetadata, "AutomationPipeline": AutomationPipeline}[name]
    if name in {"PipelineOrchestrator", "PipelineResult"}:
        from core.pipeline.orchestrator import PipelineOrchestrator, PipelineResult

        return {"PipelineOrchestrator": PipelineOrchestrator, "PipelineResult": PipelineResult}[name]
    raise AttributeError(name)


__all__ = [
    "AgentCapability",
    "AgentResult",
    "PipelineAgent",
    "PipelineContext",
    "StageConfig",
    "StageResult",
    "PipelineStage",
    "PipelineTemplateModel",
    "PipelineMetadata",
    "AutomationPipeline",
    "PipelineOrchestrator",
    "PipelineResult",
    "ensure_pipeline_dirs",
    "install_builtin_templates",
    "load_all_pipelines",
    "save_custom_pipeline",
    "save_execution",
]
