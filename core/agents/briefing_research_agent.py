from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
import re

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


class BriefingResearchAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="briefing_research_agent",
            role="researcher",
            system_prompt=(
                "You are a research assistant. Produce structured research notes.\n"
                "Return findings as bullet points and cite sources when provided.\n"
                "If no sources are provided, clearly state that the summary is based on general knowledge."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="briefing_research",
                    name="Briefing Aggregation",
                    description="Collect recent sources and summarize key developments.",
                    input_types=["text", "file"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=35,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        data = dict(inputs or {})
        request = str(data.get("user_request") or context.user_request or "").strip()
        req_lower = request.lower()
        freq_match = re.search(r"frequency\s*:\s*([a-z]+)", req_lower)
        if freq_match:
            freq = freq_match.group(1).strip()
        elif "weekly" in req_lower:
            freq = "weekly"
        elif "daily" in req_lower:
            freq = "daily"
        else:
            freq = "daily"
        if freq not in {"daily", "weekly", "any"}:
            freq = "daily"
        max_age_hours = 24 if freq == "daily" else (24 * 7 if freq == "weekly" else None)
        source_files = list(data.get("source_files") or [])
        source_text = str(data.get("source_text") or "")
        allow_web = bool(data.get("allow_web_research") or context.initial_parameters.get("allow_web_research"))
        max_results = int(data.get("web_max_results") or context.initial_parameters.get("web_max_results") or 5)
        allow_stale = bool(data.get("allow_stale_sources") or context.initial_parameters.get("allow_stale_sources"))
        if freq == "any":
            allow_stale = True
        try:
            settings = context.services.get("settings")
            wf_settings = settings.get_workflow_settings() if settings else {}
            allow_web = bool(allow_web or wf_settings.get("allow_web_research", False))
            max_results = int(wf_settings.get("web_max_results", max_results))
            allow_stale = bool(allow_stale or wf_settings.get("allow_stale_sources", False))
        except Exception:
            pass

        collected: list[str] = []
        sources: list[str] = []
        source_blocks: list[str] = []
        source_meta: list[dict[str, Any]] = []
        source_records: list[dict[str, Any]] = []
        source_count = 0
        seen_urls: set[str] = set()
        recency_warning = ""
        recent_sources = 0
        stale_sources = 0
        undated_sources = 0
        fallback_used = False

        def _extract_terms(label: str) -> list[str]:
            if not request:
                return []
            match = re.search(rf"{label}\\s*:\\s*(.+)", request, re.I)
            if not match:
                return []
            raw = match.group(1)
            parts = re.split(r"[,\n;/|]+", raw)
            return [p.strip() for p in parts if p.strip()]

        def _parse_date_from_text(text: str) -> datetime | None:
            if not text:
                return None
            month_names = (
                "january|february|march|april|may|june|july|august|september|october|november|december"
            )
            month_rx = re.compile(rf"\\b({month_names})\\s+\\d{{1,2}},\\s*20\\d{{2}}\\b", re.I)
            candidates: list[datetime] = []
            for match in month_rx.finditer(text):
                raw = match.group(0)
                try:
                    candidates.append(datetime.strptime(raw, "%B %d, %Y").replace(tzinfo=timezone.utc))
                    continue
                except Exception:
                    pass
                try:
                    candidates.append(datetime.strptime(raw, "%b %d, %Y").replace(tzinfo=timezone.utc))
                except Exception:
                    continue
            iso_rx = re.compile(r"\\b(20\\d{2})[-/](\\d{1,2})[-/](\\d{1,2})\\b")
            for match in iso_rx.finditer(text):
                try:
                    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
                    candidates.append(datetime(year, month, day, tzinfo=timezone.utc))
                except Exception:
                    continue
            if not candidates:
                return None
            return max(candidates)

        def _parse_date_from_url(url: str) -> datetime | None:
            if not url:
                return None
            url_rx = re.compile(r"/(20\\d{2})[/-](\\d{1,2})[/-](\\d{1,2})/")
            match = url_rx.search(url)
            if match:
                try:
                    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
                    return datetime(year, month, day, tzinfo=timezone.utc)
                except Exception:
                    return None
            return None

        def _extract_publish_date(text: str, url: str) -> datetime | None:
            return _parse_date_from_url(url) or _parse_date_from_text(text)

        def _format_pub_date(value: datetime | None, age_hours: float | None) -> str:
            if not value:
                return ""
            try:
                if age_hours is not None and age_hours < 24:
                    if age_hours < 1:
                        minutes = max(1, int(age_hours * 60))
                        return f"{minutes} minutes ago"
                    hours = max(1, int(age_hours))
                    return f"{hours} hours ago"
                return value.astimezone(timezone.utc).strftime("%B %d, %Y")
            except Exception:
                return ""

        def _ensure_tz(dt: datetime | None) -> datetime | None:
            if not dt:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        def _parse_rss(xml_text: str) -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            if not xml_text:
                return items
            try:
                root = ET.fromstring(xml_text)
            except Exception:
                return items
            for node in root.findall(".//item"):
                title = (node.findtext("title") or "").strip()
                link = (node.findtext("link") or "").strip()
                desc = (node.findtext("description") or "").strip()
                pub_raw = (node.findtext("pubDate") or "").strip()
                source_name = ""
                source_node = node.find("source")
                if source_node is not None and source_node.text:
                    source_name = str(source_node.text).strip()
                published_at = None
                if pub_raw:
                    try:
                        published_at = _ensure_tz(parsedate_to_datetime(pub_raw))
                    except Exception:
                        published_at = None
                items.append(
                    {
                        "title": title,
                        "url": link,
                        "summary": desc,
                        "published_at": published_at,
                        "source": source_name,
                    }
                )
            return items

        def _fetch_rss(url: str, timeout: int = 8) -> str:
            try:
                import requests

                resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            except Exception:
                return ""
            if resp.status_code != 200:
                return ""
            return resp.text or ""

        def _collect_rss_results(queries: list[str], max_items: int) -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            seen: set[str] = set()
            for query in queries:
                rss_urls = [
                    f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss",
                    f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en",
                ]
                for rss_url in rss_urls:
                    xml_text = _fetch_rss(rss_url)
                    for item in _parse_rss(xml_text):
                        url = str(item.get("url") or "")
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        results.append(item)
                        if len(results) >= max_items:
                            return results
            return results

        def add_source(
            *,
            title: str,
            url: str,
            text: str,
            origin: str,
            published_at: datetime | None = None,
            age_hours: float | None = None,
            recency: str = "",
        ) -> None:
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
            published_label = _format_pub_date(published_at, age_hours)
            source_meta.append(
                {
                    "id": source_count,
                    "title": title,
                    "url": url,
                    "type": src_type,
                    "origin": origin,
                    "published_at": published_label,
                    "age_hours": age_hours,
                    "recency": recency,
                }
            )
            source_records.append(
                {
                    "id": source_count,
                    "title": title,
                    "url": url,
                    "origin": origin,
                    "text": text or "",
                    "published_at": published_label,
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
            topics = _extract_terms("topics")
            companies = _extract_terms("companies")
            terms = [t for t in topics + companies if t]
            if not terms:
                terms = [request]
            terms = terms[:6]
            month_year = datetime.now(timezone.utc).strftime("%B %Y")
            if freq == "daily":
                query_templates = [
                    "{term} news today",
                    "{term} latest news",
                    "{term} breaking news",
                    f"{{term}} {month_year} news",
                ]
            elif freq == "weekly":
                query_templates = [
                    "{term} news this week",
                    "{term} latest developments",
                    f"{{term}} {month_year} news",
                ]
            else:
                query_templates = [
                    "{term} latest news",
                    "{term} industry news",
                    f"{{term}} {month_year} news",
                ]
            queries = []
            for term in terms:
                for template in query_templates:
                    queries.append(template.format(term=term))
            web_added = 0
            fallback: list[tuple[str, str, str, datetime | None]] = []
            rss_items = _collect_rss_results(queries, max_results * 4)
            for item in rss_items:
                if web_added >= max_results:
                    break
                url = str(item.get("url") or "")
                title = str(item.get("title") or url)
                source_name = str(item.get("source") or "").strip()
                if source_name:
                    title = f"{source_name} - {title}"
                published_at = _ensure_tz(item.get("published_at"))
                age_hours = None
                if published_at:
                    try:
                        age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600.0
                    except Exception:
                        age_hours = None
                enforce_recency = max_age_hours is not None
                is_recent = bool(
                    published_at and age_hours is not None and (not enforce_recency or age_hours <= max_age_hours)
                )
                is_undated = published_at is None
                if enforce_recency and (is_undated or not is_recent):
                    fallback.append((title or url, url, str(item.get("summary") or ""), published_at))
                    continue
                text = fetch_url_text(url, max_chars=4000) if url else ""
                if not text:
                    text = str(item.get("summary") or "")
                if is_undated:
                    undated_sources += 1
                else:
                    recent_sources += 1
                add_source(
                    title=title or url,
                    url=url,
                    text=text,
                    origin="web",
                    published_at=published_at,
                    age_hours=age_hours,
                    recency="recent" if is_recent else "unknown",
                )
                web_added += 1
            for query in queries:
                if web_added >= max_results:
                    break
                results = search_web(query, max_results=max_results)
                for result in results:
                    if web_added >= max_results:
                        break
                    url = str(result.get("url") or "")
                    title = str(result.get("title") or url)
                    text = fetch_url_text(url, max_chars=4000)
                    if not text:
                        continue
                    published_at = _extract_publish_date(text, url)
                    age_hours = None
                    if published_at:
                        try:
                            age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600.0
                        except Exception:
                            age_hours = None
                    enforce_recency = max_age_hours is not None
                    is_recent = bool(
                        published_at and age_hours is not None and (not enforce_recency or age_hours <= max_age_hours)
                    )
                    is_undated = published_at is None
                    if enforce_recency and (is_undated or not is_recent):
                        fallback.append((title or url, url, text, published_at))
                        continue
                    if is_undated:
                        undated_sources += 1
                    else:
                        recent_sources += 1
                    add_source(
                        title=title or url,
                        url=url,
                        text=text,
                        origin="web",
                        published_at=published_at,
                        age_hours=age_hours,
                        recency="recent" if is_recent else "unknown",
                    )
                    web_added += 1
            if max_age_hours is not None and web_added == 0 and fallback:
                fallback_used = True
                if allow_stale:
                    recency_warning = (
                        f"No sources found within the last {max_age_hours} hours; including older or undated sources."
                    )
                else:
                    recency_warning = (
                        f"No sources found within the last {max_age_hours} hours; using most recent available sources."
                    )
                for title, url, text, published_at in fallback[:max_results]:
                    age_hours = None
                    if published_at:
                        try:
                            age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600.0
                        except Exception:
                            age_hours = None
                    if published_at is None:
                        undated_sources += 1
                    else:
                        stale_sources += 1
                    add_source(
                        title=title or url,
                        url=url,
                        text=text,
                        origin="web",
                        published_at=published_at,
                        age_hours=age_hours,
                        recency="stale" if published_at else "unknown",
                    )
                    web_added += 1

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
        recency_policy = "any" if max_age_hours is None else f"{freq} {max_age_hours}h"
        source_analysis = {
            "source_count": len(source_meta),
            "quality_warnings": quality_warning,
            "diversity_score": diversity,
            "source_breakdown": breakdown,
            "web_sources_found": web_count,
            "local_sources_found": local_count,
            "web_search_enabled": bool(allow_web),
            "recency_policy": recency_policy,
            "recency_warning": recency_warning,
            "recent_sources": recent_sources,
            "stale_sources": stale_sources,
            "undated_sources": undated_sources,
            "fallback_used": fallback_used,
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
