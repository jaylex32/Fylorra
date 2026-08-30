from __future__ import annotations

from pathlib import Path
from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent, _safe_json
from core.agents.research_agent import (
    _classify_source,
    _source_breakdown,
    _diversity_score,
    _source_quality_warning,
    _build_dissenting_views,
    _validate_sources,
    _assign_claim_sources,
    _attach_finding_sources,
    _should_enhance_ethics,
    _enhance_ethics_section,
)
from core.text_extractor import extract_text_from_file
from core.integrations.web_search import search_web, fetch_url_text


class MarketResearchAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="market_research_agent",
            role="researcher",
            system_prompt=(
                "You are a research assistant. Produce structured research notes.\n"
                "Return findings as bullet points and cite sources when provided.\n"
                "If no sources are provided, clearly state that the summary is based on general knowledge."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="market_research",
                    name="Market Discovery",
                    description="Collect market sources and summarize opportunities.",
                    input_types=["text", "file"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=45,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        data = dict(inputs or {})
        request = str(data.get("user_request") or context.user_request or "").strip()
        source_files = list(data.get("source_files") or [])
        source_text = str(data.get("source_text") or "")
        allow_web = bool(data.get("allow_web_research") or context.initial_parameters.get("allow_web_research"))
        max_results = int(data.get("web_max_results") or context.initial_parameters.get("web_max_results") or 5)
        try:
            settings = context.services.get("settings")
            wf_settings = settings.get_workflow_settings() if settings else {}
            allow_web = bool(allow_web or wf_settings.get("allow_web_research", False))
            max_results = int(wf_settings.get("web_max_results", max_results))
        except Exception:
            pass

        collected: list[str] = []
        sources: list[str] = []
        source_blocks: list[str] = []
        source_meta: list[dict[str, Any]] = []
        source_records: list[dict[str, Any]] = []
        source_count = 0
        seen_urls: set[str] = set()

        def add_source(*, title: str, url: str, text: str, origin: str) -> None:
            nonlocal source_count
            url = str(url or "").strip()
            if url and url in seen_urls:
                return
            if url:
                seen_urls.add(url)
            source_count += 1
            src_type = _classify_source(title, url, origin)
            label = f"[{source_count}] {title}"
            if url:
                label = f"{label} - {url}"
            if origin == "local_file":
                label = f"[{source_count}] Local file: {title}"
            sources.append(label)
            if text:
                header = f"[{source_count}] {title}"
                if url:
                    header = f"{header} ({url})"
                source_blocks.append(f"{header}\n{text}")
            source_meta.append(
                {
                    "id": source_count,
                    "title": title,
                    "url": url,
                    "type": src_type,
                    "origin": origin,
                }
            )
            source_records.append(
                {
                    "id": source_count,
                    "title": title,
                    "url": url,
                    "origin": origin,
                    "text": text or "",
                }
            )

        for f in source_files:
            try:
                path = Path(str(f))
            except Exception:
                continue
            if not path.exists():
                continue
            res = extract_text_from_file(path, ai_manager=context.services.get("ai_manager"))
            if res.ok and res.text:
                collected.append(f"[{path.name}]\n{res.text}")
                add_source(title=path.name, url="", text=res.text, origin="local_file")
        if collected:
            source_text = (source_text + "\n\n" + "\n\n".join(collected)).strip()

        if allow_web and request:
            queries = [
                f"{request} market opportunities 2026",
                f"{request} emerging markets",
                f"{request} market gaps",
                f"{request} growth segments",
                f"{request} underserved markets",
            ]
            for query in queries:
                if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                    break
                results = search_web(query, max_results=max_results)
                for result in results:
                    if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                        break
                    url = str(result.get("url") or "")
                    title = str(result.get("title") or url)
                    text = fetch_url_text(url, max_chars=4000)
                    if not text:
                        continue
                    add_source(title=title or url, url=url, text=text, origin="web")

        if source_blocks:
            max_total = 14000
            merged = []
            total = 0
            for block in source_blocks:
                if total + len(block) > max_total:
                    break
                merged.append(block)
                total += len(block)
            source_text = (source_text + "\n\n" + "\n\n".join(merged)).strip()

        breakdown = _source_breakdown(source_meta)
        diversity = _diversity_score(breakdown)
        quality_warning = _source_quality_warning(len(source_meta), diversity)
        web_count = len([m for m in source_meta if m.get("origin") == "web"])
        local_count = len([m for m in source_meta if m.get("origin") == "local_file"])
        source_analysis = {
            "source_count": len(source_meta),
            "quality_warnings": quality_warning,
            "diversity_score": diversity,
            "source_breakdown": breakdown,
            "web_sources_found": web_count,
            "local_sources_found": local_count,
            "web_search_enabled": bool(allow_web),
        }
        source_validation = _validate_sources(request, len(source_meta), sources)
        if source_validation.get("status") == "CRITICAL_ERROR":
            try:
                context.should_abort = True
                context.abort_reason = source_validation.get("message")
            except Exception:
                pass
            return AgentResult(ok=False, message=str(source_validation.get("message") or "No sources found."))

        sources_meta_text = "\n".join(
            f"[{m['id']}] {m['title']} | {m.get('url') or 'local'} | type: {m.get('type')}"
            for m in source_meta
        )
        dissenting_views = _build_dissenting_views(request, source_records)

        user_msg = (
            f"Research topic:\n{request}\n\n"
            "Sources metadata (use these ids for citations):\n"
            f"{sources_meta_text or '(no sources provided)'}\n\n"
            "Source contents:\n"
            f"{source_text or '(no sources provided)'}\n\n"
            "Return strict JSON with keys:\n"
            "- summary (string)\n"
            "- findings (list of strings)\n"
            "- sources (list of strings, same ids as above)\n"
            "- source_analysis (object with source_count, quality_warnings, diversity_score, source_breakdown)\n"
            "- temporal_context (object with already_achieved, in_development, planned, speculative lists)\n"
            "- claims (list of objects: id, text, supporting_sources [ids], contradicting_sources [ids], "
            "flags [TIMELINE_SENSITIVE, TECH_DEPENDENT, DISAGREEMENT, SINGLE_SOURCE], confidence_score 0-100, "
            "confidence_label)\n"
            "- critical_analysis (object with assumptions, dependencies, precedents, barriers, risks)\n"
            "- dissenting_views (list of objects: topic, mainstream, alternative, sources [ids])\n"
            "- context_sections (object: regulatory, safety, sustainability, ethics, implementation)\n\n"
            "Rules:\n"
            "1) For each major claim, look for counter-evidence in sources; if found, flag DISAGREEMENT.\n"
            "2) Assign confidence scores and labels; timelines should be conservative.\n"
            "3) Distinguish what is already achieved vs in development vs speculative.\n"
            "4) Use citations like [1], [2] for factual statements.\n"
            "5) If sources are limited, add warnings in source_analysis.quality_warnings.\n"
            "6) For dissenting_views: use genuine alternative viewpoints from sources; avoid simple negation."
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="json",
            max_tokens=1300,
            temperature=0.2,
        )
        if not res.ok:
            return res
        raw = str(res.data.get("text") or "")
        parsed = _safe_json(raw)
        if not parsed:
            parsed = {"summary": raw, "findings": [], "sources": sources}
        parsed.setdefault("sources", sources)
        parsed.setdefault("source_analysis", source_analysis)
        parsed.setdefault("temporal_context", {})
        parsed.setdefault("claims", [])
        parsed.setdefault("critical_analysis", {})
        parsed.setdefault("dissenting_views", [])
        parsed.setdefault("context_sections", {})
        parsed["source_meta"] = source_meta
        parsed["source_analysis"] = source_analysis
        parsed["source_validation"] = source_validation
        try:
            parsed["claims"] = _assign_claim_sources(parsed.get("claims") or [], source_records)
        except Exception:
            pass
        try:
            if isinstance(parsed.get("findings"), list):
                parsed["findings"] = _attach_finding_sources(parsed.get("findings") or [], source_records)
        except Exception:
            pass
        if dissenting_views:
            parsed["dissenting_views"] = dissenting_views
        try:
            ethics_text = ""
            if isinstance(parsed.get("context_sections"), dict):
                ethics_text = str(parsed["context_sections"].get("ethics") or "")
            if _should_enhance_ethics(request, ethics_text):
                enriched = _enhance_ethics_section(request)
                if enriched and isinstance(parsed.get("context_sections"), dict):
                    parsed["context_sections"]["ethics"] = enriched
        except Exception:
            pass
        return AgentResult(ok=True, data=parsed, raw_output=raw)
