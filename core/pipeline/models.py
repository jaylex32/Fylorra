from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict, AliasChoices, field_validator


def _listify(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _coerce_sources(value: Any) -> list[str]:
    items = _listify(value)
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("url") or item.get("source_url") or item.get("title") or item.get("name") or str(item)
        else:
            text = str(item)
        text = str(text).strip()
        if text:
            out.append(text)
    return out


class PipelineMetadataModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    pipeline_id: str = Field(default="")
    name: str = Field(default="")
    description: str = Field(default="")
    category: str = Field(default="")
    author: str = Field(default="Fylorra")
    version: str = Field(default="1.0")
    created_date: str = Field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = Field(default_factory=list)


class StageConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    approval_required: bool = False
    approval_message: str = "Review output before continuing?"
    retry_on_failure: bool = True
    max_retries: int = Field(default=2, ge=1, le=10)
    fallback_agent: str | None = None
    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    skip_if_previous_failed: bool = False
    condition: dict | None = None


class PipelineStageModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, str_strip_whitespace=True, validate_assignment=True)

    stage_id: str | None = None
    name: str | None = None
    agent: str = Field(validation_alias=AliasChoices("agent", "agent_type", "agent_id"))
    agent_config: dict[str, Any] = Field(default_factory=dict)
    config: StageConfigModel = Field(default_factory=StageConfigModel)
    input_mapping: dict[str, Any] | None = None


class PipelineTemplateModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    metadata: PipelineMetadataModel
    stages: list[PipelineStageModel]
    trigger: dict | None = None
    global_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stages")
    @classmethod
    def _unique_stage_ids(cls, stages: list[PipelineStageModel]):
        ids = []
        for stage in stages:
            sid = stage.stage_id or stage.name or stage.agent
            if sid:
                ids.append(str(sid))
        if len(ids) != len(set(ids)):
            raise ValueError("Stage IDs must be unique.")
        return stages


class ResearchOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    class InterpretationDebateModel(BaseModel):
        model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, validate_assignment=True)

        question: str = ""
        traditional_view: str = ""
        alternative_view: str = ""

    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    key_figures: list[str] = Field(default_factory=list)
    key_events: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    causes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    interpretations: list[InterpretationDebateModel | str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    discussion_questions: list[str] = Field(default_factory=list)
    source_analysis: dict[str, Any] = Field(default_factory=dict)
    temporal_context: dict[str, Any] = Field(default_factory=dict)
    claims: list[Any] = Field(default_factory=list)
    critical_analysis: dict[str, Any] = Field(default_factory=dict)
    dissenting_views: list[Any] = Field(default_factory=list)
    context_sections: dict[str, Any] = Field(default_factory=dict)
    source_meta: list[Any] = Field(default_factory=list)
    source_validation: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "findings",
        "timeline",
        "key_figures",
        "key_events",
        "facts",
        "context",
        "causes",
        "consequences",
        "source_notes",
        "interpretations",
        "limitations",
        "discussion_questions",
        "claims",
        "dissenting_views",
        "source_meta",
        mode="before",
    )
    @classmethod
    def _ensure_list(cls, value):
        return _listify(value)

    @field_validator("sources", mode="before")
    @classmethod
    def _ensure_sources(cls, value):
        return _coerce_sources(value)


class WritingOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    document: str = Field(default="", validation_alias=AliasChoices("document", "text"))
    format: str = "markdown"
    sources: list[str] = Field(default_factory=list)
    claims: list[Any] = Field(default_factory=list)
    source_meta: list[Any] = Field(default_factory=list)
    source_analysis: dict[str, Any] = Field(default_factory=dict)
    audience: str | None = None

    @field_validator("claims", "source_meta", mode="before")
    @classmethod
    def _ensure_list(cls, value):
        return _listify(value)

    @field_validator("sources", mode="before")
    @classmethod
    def _ensure_sources(cls, value):
        return _coerce_sources(value)


class ValidationOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    improved_text: str = Field(default="", validation_alias=AliasChoices("improved_text", "document", "text"))
    document: str = ""
    issues: list[str] = Field(default_factory=list)
    overall_score: float | None = None
    verification_report: str | None = None
    verification: list[Any] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    source_meta: list[Any] = Field(default_factory=list)

    @field_validator("issues", "verification", "source_meta", mode="before")
    @classmethod
    def _ensure_list(cls, value):
        return _listify(value)

    @field_validator("sources", mode="before")
    @classmethod
    def _ensure_sources(cls, value):
        return _coerce_sources(value)


class ExportOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    files: list[str] = Field(default_factory=list)
    exported_files: list[Any] = Field(default_factory=list)

    @field_validator("files", "exported_files", mode="before")
    @classmethod
    def _ensure_list(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]


class SummaryOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, validate_assignment=True)

    summary: str = ""
