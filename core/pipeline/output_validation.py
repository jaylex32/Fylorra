from __future__ import annotations

from typing import Any


def coerce_output(agent_id: str, data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    try:
        from core.pipeline.models import (
            ResearchOutputModel,
            WritingOutputModel,
            ValidationOutputModel,
            ExportOutputModel,
            SummaryOutputModel,
        )
    except Exception:
        return data

    mapping = {
        "research_agent": ResearchOutputModel,
        "market_research_agent": ResearchOutputModel,
        "briefing_research_agent": ResearchOutputModel,
        "history_research_agent": ResearchOutputModel,
        "writing_agent": WritingOutputModel,
        "market_writing_agent": WritingOutputModel,
        "briefing_writing_agent": WritingOutputModel,
        "family_history_writing_agent": WritingOutputModel,
        "school_assignment_writing_agent": WritingOutputModel,
        "web_article_writing_agent": WritingOutputModel,
        "kids_history_writing_agent": WritingOutputModel,
        "history_project_writing_agent": WritingOutputModel,
        "history_fact_check_agent": WritingOutputModel,
        "validation_agent": ValidationOutputModel,
        "export_agent": ExportOutputModel,
        "translation_agent": WritingOutputModel,
        "summarization_agent": SummaryOutputModel,
    }
    model = mapping.get(str(agent_id or "").strip())
    if not model:
        return data
    try:
        validated = model.model_validate(data)
    except Exception:
        return data
    return validated.model_dump(exclude_none=True)
