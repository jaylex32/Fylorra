from __future__ import annotations

from pathlib import Path
from typing import Any
import re
from difflib import SequenceMatcher

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent, _safe_json
from core.text_extractor import extract_text_from_file
from core.integrations.web_search import search_web, fetch_url_text


_BASE_SOURCE_TYPES = ("academic", "industry", "technical", "news", "critical")
_MIN_SOURCES = 3
_RECOMMENDED_SOURCES = 5
_OPTIMAL_SOURCES = 7


def _classify_source(title: str, url: str, origin: str) -> str:
    if origin == "local_file":
        return "local_files"
    text = f"{title} {url}".lower()
    if any(k in text for k in ("arxiv", "scholar", ".edu", "ac.uk", "researchgate")):
        return "academic"
    if any(k in text for k in ("gartner", "forrester", "mckinsey", "ibm", "accenture", "deloitte")):
        return "industry"
    if any(k in text for k in ("blog", "engineering", "developer", "github", "docs")):
        return "technical"
    if any(k in text for k in ("news", "reuters", "bloomberg", "nytimes", "bbc", "wsj")):
        return "news"
    if any(k in text for k in ("overhype", "hype", "skeptic", "critique", "risk", "limitations")):
        return "critical"
    return "other"


def _source_breakdown(metas: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for meta in metas:
        key = str(meta.get("type") or "other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _diversity_score(breakdown: dict[str, int]) -> float:
    unique = len([t for t in breakdown.keys() if t in _BASE_SOURCE_TYPES])
    return round(unique / float(len(_BASE_SOURCE_TYPES)), 2)


def _source_quality_warning(count: int, diversity: float) -> str:
    warning = ""
    if count < 3:
        warning = "Limited sources - findings should be considered preliminary."
    elif count < 5:
        warning = "Moderate source coverage - consider increasing for complex topics."
    if diversity < 0.3:
        extra = "Low source diversity - consider adding different perspective types."
        warning = f"{warning}\n{extra}".strip() if warning else extra
    return warning


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    out = []
    for part in parts:
        frag = " ".join(part.strip().split())
        if len(frag.split()) < 6:
            continue
        out.append(frag)
    return out


def _extract_sentence_with_phrase(text: str, phrase: str) -> str:
    if not text or not phrase:
        return ""
    phrase_l = phrase.lower()
    for sent in _split_sentences(text):
        if phrase_l in sent.lower():
            return sent
    return ""


def _infer_theme(claim_text: str) -> str:
    claim_lower = (claim_text or "").lower()
    if any(word in claim_lower for word in ["timeline", "2026", "2027", "2028", "2030", "tipping point", "by "]):
        return "timeline"
    if any(word in claim_lower for word in ["battery", "solid-state", "range", "charging", "technology"]):
        return "technology"
    if any(word in claim_lower for word in ["infrastructure", "charging station", "grid", "ports"]):
        return "infrastructure"
    if any(word in claim_lower for word in ["consumer", "adoption", "buyers", "demand", "preference"]):
        return "consumer"
    if any(word in claim_lower for word in ["cost", "price", "affordable", "expensive"]):
        return "cost"
    if any(word in claim_lower for word in ["policy", "regulation", "government", "mandate", "incentive"]):
        return "policy"
    return "general"


def _format_theme_name(theme: str) -> str:
    mapping = {
        "timeline": "Adoption Timeline",
        "technology": "Technology Readiness",
        "infrastructure": "Infrastructure Adequacy",
        "consumer": "Consumer Readiness",
        "cost": "Cost & Economics",
        "policy": "Policy & Regulation",
        "general": "General Perspectives",
    }
    return mapping.get(theme, "General Perspectives")


def _get_theme_keywords(theme: str) -> list[str]:
    theme_keyword_map = {
        "timeline": ["2026", "2030", "timeline", "years", "tipping point", "by "],
        "technology": ["battery", "charging", "range", "solid-state", "technology"],
        "infrastructure": ["infrastructure", "charging station", "grid", "ports"],
        "consumer": ["consumer", "adoption", "buyers", "demand", "preference"],
        "cost": ["cost", "price", "affordable", "expensive"],
        "policy": ["policy", "regulation", "government", "mandate", "incentive"],
    }
    return theme_keyword_map.get(theme, [theme])


def _is_simple_statistical_negation(text1: str, text2: str) -> bool:
    if not text1 or not text2:
        return False
    nums1 = re.findall(r"\d+(?:\.\d+)?", text1)
    nums2 = re.findall(r"\d+(?:\.\d+)?", text2)
    if nums1 and nums1 == nums2:
        up_down = (
            ("up" in text1.lower() and "down" in text2.lower())
            or ("down" in text1.lower() and "up" in text2.lower())
            or ("increase" in text1.lower() and "decrease" in text2.lower())
            or ("decrease" in text1.lower() and "increase" in text2.lower())
        )
        if up_down:
            return True
    if "will not" in text2.lower() and "will" in text1.lower() and len(text2.split()) < 15:
        return True
    return False


def _is_substantive_alternative(alt_text: str, main_text: str) -> bool:
    if not alt_text or not main_text:
        return False
    reasoning_words = ["because", "due to", "given", "since", "as", "barriers", "limitations", "challenges"]
    has_reasoning = any(word in alt_text.lower() for word in reasoning_words)
    similarity = SequenceMatcher(None, alt_text.lower(), main_text.lower()).ratio()
    if _is_simple_statistical_negation(main_text, alt_text):
        return False
    return has_reasoning and similarity < 0.6


def _build_dissenting_views(topic: str, sources: list[dict]) -> list[dict]:
    if not sources:
        return []

    optimistic_markers = [
        "will accelerate",
        "expected to",
        "projected to",
        "poised to",
        "tipping point",
        "mainstream by",
        "ready by",
        "likely to",
    ]
    cautious_markers = [
        "however",
        "but",
        "challenges",
        "barriers",
        "obstacles",
        "limitations",
        "concerns",
        "slower",
        "delayed",
        "not yet",
        "unlikely",
    ]

    optimistic_claims = []
    cautious_claims = []

    for src in sources:
        text = str(src.get("text") or "")
        if not text:
            continue
        for marker in optimistic_markers:
            sent = _extract_sentence_with_phrase(text, marker)
            if sent:
                optimistic_claims.append(
                    {
                        "text": sent,
                        "source_id": int(src.get("id") or 0),
                        "theme": _infer_theme(sent),
                    }
                )
        for marker in cautious_markers:
            sent = _extract_sentence_with_phrase(text, marker)
            if sent:
                cautious_claims.append(
                    {
                        "text": sent,
                        "source_id": int(src.get("id") or 0),
                        "theme": _infer_theme(sent),
                    }
                )

    if not optimistic_claims or not cautious_claims:
        return []

    by_theme = {}
    for claim in optimistic_claims:
        by_theme.setdefault(claim["theme"], {"main": [], "alt": []})["main"].append(claim)
    for claim in cautious_claims:
        by_theme.setdefault(claim["theme"], {"main": [], "alt": []})["alt"].append(claim)

    themes_order = ["timeline", "technology", "infrastructure", "consumer", "cost", "policy", "general"]
    perspectives = []
    for theme in themes_order:
        bucket = by_theme.get(theme)
        if not bucket:
            continue
        if not bucket["main"] or not bucket["alt"]:
            continue
        main = max(bucket["main"], key=lambda c: len(c["text"]))
        alt_candidates = bucket["alt"]
        alt = None
        for cand in alt_candidates:
            if cand["source_id"] != main["source_id"] and _is_substantive_alternative(cand["text"], main["text"]):
                alt = cand
                break
        if alt is None:
            for cand in alt_candidates:
                if _is_substantive_alternative(cand["text"], main["text"]):
                    alt = cand
                    break
        if not alt:
            continue
        perspectives.append(
            {
                "topic": _format_theme_name(theme),
                "mainstream": f"{main['text']} [{main['source_id']}]",
                "alternative": f"{alt['text']} [{alt['source_id']}]",
                "sources": [main["source_id"], alt["source_id"]],
            }
        )
        if len(perspectives) >= 4:
            break

    if perspectives:
        return perspectives

    for main in optimistic_claims:
        for alt in cautious_claims:
            if main["source_id"] == alt["source_id"]:
                continue
            if _is_substantive_alternative(alt["text"], main["text"]):
                return [
                    {
                        "topic": _format_theme_name(main["theme"]),
                        "mainstream": f"{main['text']} [{main['source_id']}]",
                        "alternative": f"{alt['text']} [{alt['source_id']}]",
                        "sources": [main["source_id"], alt["source_id"]],
                    }
                ]
    return []


def _should_enhance_ethics(topic: str, ethics_text: str) -> bool:
    if not ethics_text or len(ethics_text.strip()) < 160:
        return True
    low = ethics_text.lower()
    if "not a major concern" in low or "not currently a primary barrier" in low:
        return True
    if "ethic" not in low and "bias" not in low and "privacy" not in low:
        return True
    return False


def _enhance_ethics_section(topic: str) -> str | None:
    topic_lower = (topic or "").lower()
    if any(word in topic_lower for word in ["ev", "electric vehicle", "battery", "charging", "automotive"]):
        return (
            "Supply chain ethics (cobalt/lithium sourcing and labor practices), environmental justice "
            "(benefits accrue to higher-income adopters while extraction impacts fall on producing regions), "
            "labor transition risks in legacy auto manufacturing, and battery recycling/end-of-life governance "
            "remain important ethical considerations."
        )
    if any(word in topic_lower for word in ["ai", "artificial intelligence", "machine learning", "model"]):
        return (
            "Key ethics concerns include bias and discrimination in automated decisions, privacy and data "
            "consent, transparency for high-impact use cases, and accountability for model failures. "
            "Workforce displacement and unequal distribution of benefits are also material."
        )
    if any(word in topic_lower for word in ["health", "medical", "drug", "cannabis", "marijuana"]):
        return (
            "Ethical issues include patient safety, informed consent, equitable access, marketing to vulnerable "
            "populations, and balancing public health with commercialization incentives."
        )
    return None


def _extract_keywords(text: str) -> list[str]:
    if not text:
        return []
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "will",
        "into",
        "over",
        "than",
        "also",
        "such",
        "their",
        "they",
        "them",
        "has",
        "have",
        "had",
        "its",
        "these",
        "those",
        "about",
        "more",
        "most",
        "less",
        "some",
        "many",
        "among",
        "across",
        "which",
        "while",
        "due",
        "because",
        "write",
        "create",
        "make",
        "generate",
        "website",
        "blog",
        "article",
        "report",
        "project",
        "assignment",
        "homework",
        "topic",
        "daily",
        "weekly",
        "current",
        "status",
        "latest",
        "update",
    }
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9%-]+", text.lower())
    keywords = []
    for w in words:
        if w in {"ai", "ml", "ev", "vr", "ar"}:
            keywords.append(w)
            continue
        if w.isdigit() and len(w) < 2:
            continue
        if w.isalpha() and len(w) < 4:
            continue
        if w in stop:
            continue
        keywords.append(w)
    # De-duplicate while preserving order.
    unique: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        if kw in seen:
            continue
        seen.add(kw)
        unique.append(kw)
    return unique[:24]


def _source_topic_score(request_terms: list[str], *, title: str, url: str, text: str) -> int:
    if not request_terms:
        return 0
    hay_title = f"{title} {url}".lower()
    hay_text = f"{title} {url} {str(text or '')[:1800]}".lower()
    title_tokens = set(re.findall(r"[a-z0-9][a-z0-9%-]+", hay_title))
    all_tokens = set(re.findall(r"[a-z0-9][a-z0-9%-]+", hay_text))
    score = 0
    for term in request_terms:
        matched = False
        if term in title_tokens or term in all_tokens:
            matched = True
        stem = term[:5]
        if not matched and stem and any(tok.startswith(stem) for tok in title_tokens):
            matched = True
        if not matched and stem and any(tok.startswith(stem) for tok in all_tokens):
            matched = True
        if matched:
            score += 1
    return score


def _best_source_for_text(text: str, sources: list[dict[str, Any]]) -> int | None:
    if not text or not sources:
        return None
    keywords = _extract_keywords(text)
    if not keywords:
        return None
    best_id = None
    best_score = 0
    for src in sources:
        src_text = str(src.get("text") or "").lower()
        if not src_text:
            continue
        score = 0
        for kw in keywords:
            if kw in src_text:
                score += 2
        if score > best_score:
            best_score = score
            best_id = int(src.get("id") or 0) or None
    if best_score < 2:
        return None
    return best_id


def _assign_claim_sources(claims: list, sources: list[dict[str, Any]]) -> list:
    if not claims or not sources:
        return claims
    updated = []
    for claim in claims:
        if not isinstance(claim, dict):
            updated.append(claim)
            continue
        supporting = claim.get("supporting_sources") or []
        contradicting = claim.get("contradicting_sources") or []
        if not supporting:
            best = _best_source_for_text(str(claim.get("text") or ""), sources)
            if best:
                supporting = [best]
        claim["supporting_sources"] = supporting
        claim["contradicting_sources"] = contradicting or []
        updated.append(claim)
    return updated


def _attach_finding_sources(findings: list, sources: list[dict[str, Any]]) -> list:
    if not findings or not sources:
        return findings
    out = []
    for item in findings:
        if not isinstance(item, str):
            out.append(item)
            continue
        if re.search(r"\[\d+\]", item):
            out.append(item)
            continue
        best = _best_source_for_text(item, sources)
        if best:
            out.append(f"{item} [{best}]")
        else:
            out.append(item)
    return out


def _suggest_queries(topic: str) -> list[str]:
    text = str(topic or "").strip()
    if not text:
        return []
    base = text.split()
    core = " ".join(base[:3]) if base else text
    return [
        f"{core} trends",
        f"{core} predictions",
        f"{core} forecast 2025 2026",
        f"{core} industry analysis",
        f"{core} research paper",
        f"{core} challenges limitations",
    ]


def _validate_sources(topic: str, count: int, sources: list[str]) -> dict[str, Any]:
    if count <= 0:
        return {
            "status": "CRITICAL_ERROR",
            "proceed": False,
            "source_count": 0,
            "message": f"Cannot generate report - no sources found for: {topic}",
            "suggestions": _suggest_queries(topic),
            "sources": sources,
        }
    if count < _MIN_SOURCES:
        return {
            "status": "INSUFFICIENT",
            "proceed": "USER_CHOICE",
            "source_count": count,
            "message": f"Only {count} source(s) found. Minimum required is {_MIN_SOURCES}.",
            "suggestions": _suggest_queries(topic),
            "sources": sources,
        }
    if count < _RECOMMENDED_SOURCES:
        return {
            "status": "MINIMAL",
            "proceed": True,
            "source_count": count,
            "message": f"{count} sources found - minimum met, more recommended.",
            "sources": sources,
        }
    if count < _OPTIMAL_SOURCES:
        return {
            "status": "ADEQUATE",
            "proceed": True,
            "source_count": count,
            "message": f"{count} sources found - good coverage.",
            "sources": sources,
        }
    return {
        "status": "OPTIMAL",
        "proceed": True,
        "source_count": count,
        "message": f"{count} sources found - excellent coverage.",
        "sources": sources,
    }


class ResearchAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="research_agent",
            role="researcher",
            system_prompt=(
                "You are a research assistant. Produce structured research notes.\n"
                "Return findings as bullet points and cite sources when provided.\n"
                "If no sources are provided, clearly state that the summary is based on general knowledge."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="offline_research",
                    name="Offline Research",
                    description="Summarize provided sources into structured research notes.",
                    input_types=["text", "file"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=40,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        data = dict(inputs or {})
        request = str(data.get("user_request") or context.user_request or "").strip()
        if "_" in request and " " not in request:
            request = request.replace("_", " ").strip()
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
        request_terms = _extract_keywords(request)
        rejected_web_sources: list[dict[str, Any]] = []

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
            req_low = request.lower()
            is_article_mode = any(k in req_low for k in ("blog", "article", "website", "post"))
            if is_article_mode:
                queries = [
                    request,
                    f"{request} practical tools",
                    f"{request} examples",
                    f"{request} guide 2025",
                    f"{request} case study",
                ]
            else:
                queries = [
                    request,
                    f"{request} challenges",
                    f"{request} limitations",
                    f"{request} overhype",
                    f"{request} regulatory",
                    f"{request} safety risks",
                    f"{request} energy consumption",
                    f"{request} current status 2025",
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
                    # Relevance guard: skip weakly related web pages to reduce off-topic citations.
                    min_score = 1
                    if len(request_terms) >= 3:
                        min_score = 2
                    score = _source_topic_score(request_terms, title=title, url=url, text=text)
                    if score < min_score:
                        rejected_web_sources.append(
                            {
                                "score": score,
                                "title": title,
                                "url": url,
                                "text": text,
                            }
                        )
                        continue
                    add_source(title=title or url, url=url, text=text, origin="web")

            # Soft fallback: if strict filter rejects everything, keep the best partial matches.
            if len([m for m in source_meta if m.get("origin") == "web"]) == 0 and rejected_web_sources:
                rejected_web_sources.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
                for item in rejected_web_sources:
                    if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                        break
                    fallback_min = 2 if is_article_mode else 1
                    if int(item.get("score") or 0) < fallback_min:
                        continue
                    add_source(
                        title=str(item.get("title") or item.get("url") or ""),
                        url=str(item.get("url") or ""),
                        text=str(item.get("text") or ""),
                        origin="web",
                    )

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
        pipeline_id = str(
            context.pipeline_id
            or context.initial_parameters.get("pipeline_id")
            or ""
        )
        strict_publish_pipelines = {
            "website_blog_article",
            "website_product_update_article",
            "news_explainer_article",
        }
        if pipeline_id in strict_publish_pipelines:
            try:
                source_analysis["publish_ready"] = source_validation.get("status") not in {"CRITICAL_ERROR", "INSUFFICIENT"}
                source_analysis["strict_publish_mode"] = True
            except Exception:
                pass
            # Do not hard-fail in strict publish templates; downstream writer will switch to
            # safe no-citation mode when evidence quality is weak.
        if source_validation.get("status") == "CRITICAL_ERROR":
            if pipeline_id in strict_publish_pipelines:
                source_validation["proceed"] = True
            else:
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
            "6) For dissenting_views: use genuine alternative viewpoints from sources; avoid simple negation.\n"
            "7) Do not introduce specific product/tool/company names unless they appear in source contents."
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
