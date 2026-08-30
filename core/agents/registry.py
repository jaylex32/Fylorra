from __future__ import annotations

from typing import Any, Callable

from core.agents.research_agent import ResearchAgent
from core.agents.writing_agent import WritingAgent
from core.agents.market_research_agent import MarketResearchAgent
from core.agents.market_writing_agent import MarketWritingAgent
from core.agents.briefing_research_agent import BriefingResearchAgent
from core.agents.briefing_writing_agent import BriefingWritingAgent
from core.agents.history_research_agent import HistoryResearchAgent
from core.agents.history_project_writing_agent import HistoryProjectWritingAgent
from core.agents.history_fact_check_agent import HistoryFactCheckAgent
from core.agents.family_history_writing_agent import FamilyHistoryWritingAgent
from core.agents.school_assignment_writing_agent import SchoolAssignmentWritingAgent
from core.agents.title_suggestion_agent import TitleSuggestionAgent
from core.agents.web_article_writing_agent import WebArticleWritingAgent
from core.agents.validation_agent import ValidationAgent
from core.agents.export_agent import ExportAgent
from core.agents.summarization_agent import SummarizationAgent
from core.agents.translation_agent import TranslationAgent


_AGENT_FACTORIES: dict[str, Callable[[dict[str, Any]], object]] = {
    "research_agent": lambda cfg: ResearchAgent(cfg),
    "writing_agent": lambda cfg: WritingAgent(cfg),
    "market_research_agent": lambda cfg: MarketResearchAgent(cfg),
    "market_writing_agent": lambda cfg: MarketWritingAgent(cfg),
    "briefing_research_agent": lambda cfg: BriefingResearchAgent(cfg),
    "briefing_writing_agent": lambda cfg: BriefingWritingAgent(cfg),
    "history_research_agent": lambda cfg: HistoryResearchAgent(cfg),
    "history_project_writing_agent": lambda cfg: HistoryProjectWritingAgent(cfg),
    "family_history_writing_agent": lambda cfg: FamilyHistoryWritingAgent(cfg),
    "school_assignment_writing_agent": lambda cfg: SchoolAssignmentWritingAgent(cfg),
    "title_suggestion_agent": lambda cfg: TitleSuggestionAgent(cfg),
    "web_article_writing_agent": lambda cfg: WebArticleWritingAgent(cfg),
    "history_fact_check_agent": lambda cfg: HistoryFactCheckAgent(cfg),
    "validation_agent": lambda cfg: ValidationAgent(cfg),
    "export_agent": lambda cfg: ExportAgent(cfg),
    "summarization_agent": lambda cfg: SummarizationAgent(cfg),
    "translation_agent": lambda cfg: TranslationAgent(cfg),
}


def create_agent(agent_id: str, config: dict[str, Any] | None = None):
    key = str(agent_id or "").strip()
    cfg = dict(config or {})
    template_id = str(cfg.get("template_id") or "").strip().lower()
    # Backward-compatible routing for legacy template configs.
    if key == "research_agent":
        if template_id == "market_opportunity":
            key = "market_research_agent"
            cfg.pop("template_id", None)
        elif template_id == "executive_briefing":
            key = "briefing_research_agent"
            cfg.pop("template_id", None)
    elif key == "writing_agent":
        if template_id == "market_opportunity":
            key = "market_writing_agent"
            cfg.pop("template_id", None)
        elif template_id == "executive_briefing":
            key = "briefing_writing_agent"
            cfg.pop("template_id", None)
    if key in _AGENT_FACTORIES:
        return _AGENT_FACTORIES[key](cfg)
    raise ValueError(f"Unknown agent: {key}")


def list_agents() -> list[str]:
    return sorted(_AGENT_FACTORIES.keys())
