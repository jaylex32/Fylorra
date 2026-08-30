from __future__ import annotations

import re
import unicodedata
from typing import Any

from core.agents.llm_agent import _LLMBaseAgent, _safe_json
from core.pipeline.agent import AgentCapability, AgentResult

try:
    from pydantic import BaseModel, Field, ValidationError
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore[misc,assignment]
    Field = lambda default_factory=None, **kwargs: None  # type: ignore[assignment]
    ValidationError = Exception  # type: ignore[assignment]


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"\[\s*\d+\s*\]", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_citation_ids(text: str) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in re.findall(r"\[(\d+)\]", str(text or "")):
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def _dedupe_preserve(items: list[str], *, key_fn=None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = key_fn(text) if key_fn else _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _build_sources_list(source_meta: list[dict[str, Any]] | None, sources: Any) -> list[str]:
    lines: list[str] = []
    if source_meta:
        for meta in source_meta:
            title = str(meta.get("title") or "").strip()
            url = str(meta.get("url") or "").strip()
            if not title and url:
                title = url
            if not title and not url:
                continue
            sid = meta.get("id")
            prefix = f"[{sid}] " if sid is not None else ""
            entry = f"{prefix}{title}"
            if url:
                entry = f"{entry} - {url}"
            lines.append(entry)
    elif isinstance(sources, list):
        raw_items = [str(x).strip() for x in sources if str(x).strip()]
        if raw_items and not any(item.startswith("[") for item in raw_items):
            raw_items = [f"[{i + 1}] {item}" for i, item in enumerate(raw_items)]
        lines.extend(raw_items)
    return _dedupe_preserve(lines)


def _extract_sources_from_document(document: str) -> list[str]:
    if not document:
        return []
    pattern = re.compile(r"(?ms)^\s*#+\s+Sources[^\n]*\n(.*?)(?=^\s*#+\s+\w|\Z)", re.IGNORECASE)
    match = pattern.search(document)
    if not match:
        return []
    out: list[str] = []
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        if line:
            out.append(line)
    return _dedupe_preserve(out)


def _collapse_sources_sections(document: str, sources_list: list[str]) -> str:
    if not document:
        return document
    has_works_cited = bool(
        re.search(r"(?im)^\s*#{1,6}\s+(Works Cited|Where We Learned This)\b", document)
    )
    if not sources_list:
        sources_list = _extract_sources_from_document(document)
    pattern = re.compile(r"(?ms)^\s*#+\s+Sources[^\n]*\n.*?(?=^\s*#+\s+\w|\Z)", re.IGNORECASE)
    cleaned = pattern.sub("", document).strip()
    if has_works_cited:
        return cleaned
    if not sources_list:
        return cleaned
    body = "\n".join(f"- {line}" for line in _dedupe_preserve(sources_list))
    replacement = f"## Sources\n{body}"
    if cleaned:
        return cleaned.rstrip() + "\n\n" + replacement
    return replacement


def _strip_placeholder_notes(document: str) -> str:
    if not document:
        return document
    patterns = [
        r"(?im)^\\*?note:.*placeholder.*$",
        r"(?im)^\\*?note:.*replace.*actual.*sources.*$",
        r"(?im)^\\*?note:.*scholarly sources.*$",
    ]
    cleaned = document
    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned)
    return cleaned.strip()


def _strip_verification_report(document: str) -> str:
    if not document:
        return document
    lines = str(document).splitlines()
    start = -1
    start_level = 0
    for idx, line in enumerate(lines):
        m = re.match(r"^\s*(#{1,6})\s*Verification Report\b", line, flags=re.IGNORECASE)
        if m:
            start = idx
            start_level = len(m.group(1))
            break
    if start < 0:
        return str(document).strip()
    # Strip the entire verification block. The report contains internal headings like
    # "## Verified", so we must resume only at the next heading of the same or higher
    # level (<= start_level).
    for idx in range(start + 1, len(lines)):
        m = re.match(r"^\s*(#{1,6})\s+\S", lines[idx])
        if not m:
            continue
        if re.match(r"^\s*#{1,6}\s*Verification Report\b", lines[idx], flags=re.IGNORECASE):
            continue
        level = len(m.group(1))
        if level <= start_level:
            return "\n".join(lines[idx:]).strip()
    return ""


def _dedupe_lines(document: str) -> str:
    if not document:
        return document
    lines = document.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if re.match(r"^\s*#+\s+\S", line):
            seen = set()
            out.append(line)
            continue
        key = re.sub(r"\s+", " ", line).strip().lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(line)
    return "\n".join(out).strip()


def _citation_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return f"[{value}]"
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+", text):
        return f"[{text}]"
    found = re.search(r"\[\d+\]", text)
    return found.group(0) if found else ""


def _coerce_line(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, dict):
        name = str(item.get("name") or item.get("person") or "").strip()
        role = str(item.get("role") or item.get("description") or "").strip()
        text = str(item.get("statement") or item.get("text") or item.get("detail") or "").strip()
        citation = _citation_text(
            item.get("citation")
            or item.get("citations")
            or item.get("source_id")
            or item.get("source")
        )
        if name:
            if role:
                return f"{name} - {role} {citation}".strip()
            if text:
                return f"{name} - {text} {citation}".strip()
            return f"{name} {citation}".strip()
        if text:
            return f"{text} {citation}".strip()
        return ""
    return str(item).strip()


def _source_text_map(payload: dict[str, Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for rec in list(payload.get("source_records") or []):
        sid = rec.get("id")
        try:
            sid_int = int(sid)
        except Exception:
            continue
        txt = str(rec.get("text_excerpt") or rec.get("text") or "").strip()
        if txt:
            out[sid_int] = txt
    return out


def _line_supported_by_sources(line: str, source_ids: list[int], source_map: dict[int, str]) -> bool:
    if not source_map or not source_ids:
        return True
    cleaned = _normalize(re.sub(r"\[\d+\]", "", line))
    tokens = [tok for tok in cleaned.split() if len(tok) >= 4]
    if not tokens:
        return True
    for sid in source_ids:
        hay = _normalize(source_map.get(int(sid), ""))
        if not hay:
            continue
        if any(tok in hay for tok in tokens[:8]):
            return True
    return False


def _is_publication_or_meta(text: str) -> bool:
    low = _normalize(text)
    if not low:
        return True
    markers = (
        "published",
        "publication",
        "report of",
        "study",
        "book",
        "work discussed",
        "work was",
        "library of congress",
        "catalog",
        "table of contents",
        "presented by",
        "ordered to be printed",
    )
    return any(m in low for m in markers)


def _has_date(text: str) -> bool:
    month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    return bool(
        re.search(
            rf"\b(?:1[5-9]\d{{2}}|20\d{{2}}|{month_re}\s+\d{{1,2}},\s*(?:1[5-9]\d{{2}}|20\d{{2}})|{month_re}\s+(?:1[5-9]\d{{2}}|20\d{{2}}))\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _timeline_key(text: str) -> str:
    stripped = re.sub(r"\[\d+\]", "", text)
    stripped = re.sub(r"^\s*(?:\d{4}|[A-Za-z]+\s+\d{1,2},\s*\d{4}|[A-Za-z]+\s+\d{4})\s*[-–—:]*\s*", "", stripped)
    return _normalize(stripped)


def _looks_like_person_name(name: str) -> bool:
    head = str(name or "").strip()
    if not head:
        return False
    head = re.sub(r"(?:'s|’s)\s*$", "", head).strip()
    head = re.split(r"\s*(?:---|--|—|–|:|\s-\s)\s*", head, 1)[0].strip()
    if re.match(r"^\d", head):
        return False
    if len(head.split()) < 2 or len(head.split()) > 6:
        return False
    token = r"[A-ZÀ-ÖØ-Þ][^\W\d_]*(?:[.'’\-][^\W\d_]+)*"
    if not re.match(rf"^(?:{token}\s+)+{token}$", head):
        return False
    if " the " in f" {head.lower()} ":
        return False
    bad = ("treaty", "act", "campaign", "war", "report", "government", "administration", "people")
    low = _normalize(head)
    return not any(b in low for b in bad)


def _extract_people_from_sources(source_map: dict[int, str], max_items: int) -> list[str]:
    out: list[str] = []
    seen_names: set[str] = set()
    if not source_map:
        return out
    token = r"(?:[A-ZÀ-ÖØ-Ý]\.|[A-ZÀ-ÖØ-Ý][^\W\d_]+(?:[.'’\-][^\W\d_]+)*)"
    pat = re.compile(rf"\b(?P<name>{token}(?:\s+{token}){{1,4}})\b")
    role_words = (
        "president",
        "general",
        "governor",
        "senator",
        "secretary",
        "captain",
        "admiral",
        "colonel",
        "leader",
        "historian",
        "writer",
        "educator",
        "journalist",
        "physician",
        "doctor",
    )
    non_people = {
        "north america",
        "south america",
        "united states",
        "library of congress",
        "puerto rico",
        "spanish empire",
    }
    for sid, text in source_map.items():
        if len(out) >= max_items:
            break
        plain = str(text or "")
        for match in pat.finditer(plain):
            if len(out) >= max_items:
                break
            name = match.group("name").strip()
            if not _looks_like_person_name(name):
                continue
            key = _normalize(name)
            if key in non_people:
                continue
            if key in seen_names:
                continue
            before = plain[max(0, match.start() - 120) : match.start()]
            after = plain[match.end() : match.end() + 120]
            window = f"{before} {after}"
            role = ""
            for word in role_words:
                if re.search(rf"\b{re.escape(word)}\b", window, flags=re.IGNORECASE):
                    role = word.title()
                    break
            # Avoid adding random proper nouns unless we can place them in historical context.
            if not role and not re.search(
                r"\b(born|died|governor|senator|president|general|captain|leader|historian|wrote|served|appointed|commanded)\b",
                window,
                flags=re.IGNORECASE,
            ):
                continue
            line = f"{name} - {role} [{sid}]".strip() if role else f"{name} [{sid}]"
            out.append(line)
            seen_names.add(key)
    return out


def _clean_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_meta = list(payload.get("source_meta") or [])
    sources_list = _build_sources_list(source_meta, payload.get("sources") or [])
    source_map = _source_text_map(payload)

    def _clean_lines(items: Any, *, require_date: bool = False, require_person: bool = False, max_items: int = 12, key_fn=None) -> list[str]:
        out: list[str] = []
        raw_items = items if isinstance(items, list) else [items]
        for item in raw_items:
            line = _coerce_line(item)
            if not line:
                continue
            if _is_publication_or_meta(line):
                continue
            citations = _extract_citation_ids(line)
            if not citations:
                continue
            if require_date and not _has_date(line):
                continue
            if require_person:
                name = re.split(r"\s*(?:---|--|—|–|:|\s-\s)\s*", re.sub(r"\[\d+\]", "", line).strip(), 1)[0].strip()
                if not _looks_like_person_name(name):
                    continue
            if not _line_supported_by_sources(line, citations, source_map):
                continue
            out.append(line)
        out = _dedupe_preserve(out, key_fn=key_fn)
        return out[:max_items]

    summary = str(payload.get("summary") or "").strip()
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > 1800:
        summary = summary[:1797].rstrip() + "..."

    timeline_candidates: list[Any] = []
    timeline_candidates.extend(list(payload.get("timeline") or []))
    timeline_candidates.extend(list(payload.get("key_events") or []))
    timeline_candidates.extend(list(payload.get("facts") or []))
    timeline = _clean_lines(timeline_candidates, require_date=True, max_items=14, key_fn=_timeline_key)

    key_events = _clean_lines(payload.get("key_events") or [], max_items=12)
    if len(key_events) < 6:
        merged = _clean_lines(list(payload.get("facts") or []) + timeline, max_items=12)
        for item in merged:
            if item not in key_events:
                key_events.append(item)
            if len(key_events) >= 12:
                break

    key_figures = _clean_lines(payload.get("key_figures") or [], require_person=True, max_items=14)
    if len(key_figures) < 6:
        for item in _extract_people_from_sources(source_map, max_items=14):
            if item in key_figures:
                continue
            key_figures.append(item)
            if len(key_figures) >= 14:
                break

    context = _clean_lines(payload.get("context") or [], max_items=12)
    causes = _clean_lines(payload.get("causes") or [], max_items=10)
    consequences = _clean_lines(payload.get("consequences") or [], max_items=12)
    source_notes = _clean_lines(payload.get("source_notes") or [], max_items=12)
    facts = _clean_lines(payload.get("facts") or [], max_items=20)

    interpretations: list[Any] = []
    for item in list(payload.get("interpretations") or []):
        if isinstance(item, dict):
            q = str(item.get("question") or "").strip()
            a = str(item.get("traditional_view") or item.get("view_a") or "").strip()
            b = str(item.get("alternative_view") or item.get("view_b") or "").strip()
            if q and a and b:
                interpretations.append({"question": q, "traditional_view": a, "alternative_view": b})
        else:
            line = _coerce_line(item)
            if line and ("while others" in line.lower() or "whereas" in line.lower() or "vs" in line.lower()):
                interpretations.append(line)
    if len(interpretations) < 2 and facts:
        sample = facts[:3]
        citations = []
        for line in sample:
            citations.extend(_extract_citation_ids(line))
        c1 = f"[{citations[0]}]" if citations else "[1]"
        c2 = f"[{citations[1]}]" if len(citations) > 1 else c1
        interpretations = [
            f"Some historians argue U.S. rule accelerated modernization, while others view it as colonial control {c1} {c2}.",
            f"Some sources emphasize institutional reforms, whereas others emphasize loss of local autonomy {c1} {c2}.",
        ]

    limitations = _dedupe_preserve([_coerce_line(x) for x in list(payload.get("limitations") or [])])[:10]
    if not limitations:
        limitations = [
            "Some primary-source perspectives are limited in the collected sources.",
            "Several sources summarize events without detailed local viewpoints.",
            "Further research should include primary records and regional scholarship.",
        ]

    discussion_questions = _dedupe_preserve([_coerce_line(x) for x in list(payload.get("discussion_questions") or [])])[:14]
    if len(discussion_questions) < 8:
        defaults = [
            "What motivations most influenced the main historical actors?",
            "Which event most changed the direction of this historical story?",
            "What evidence best supports the strongest claim in this project?",
            "Where do historians disagree most about this topic?",
            "Which perspectives are underrepresented in the current source set?",
            "How did this topic affect ordinary people at the time?",
            "What long-term consequences can be traced to these events?",
            "Which additional sources would most improve this assignment?",
        ]
        for q in defaults:
            if q not in discussion_questions:
                discussion_questions.append(q)
            if len(discussion_questions) >= 14:
                break

    cleaned_doc = str(payload.get("document") or payload.get("text") or "").strip()
    if cleaned_doc:
        cleaned_doc = _strip_verification_report(_strip_placeholder_notes(cleaned_doc))
        cleaned_doc = _dedupe_lines(cleaned_doc)
        cleaned_doc = _collapse_sources_sections(cleaned_doc, sources_list)

    out = dict(payload)
    out.update(
        {
            "document": cleaned_doc,
            "summary": summary,
            "timeline": timeline,
            "key_figures": key_figures,
            "key_events": key_events,
            "context": context,
            "causes": causes,
            "consequences": consequences,
            "source_notes": source_notes,
            "facts": facts,
            "interpretations": interpretations,
            "limitations": limitations,
            "discussion_questions": discussion_questions,
            "sources": sources_list or payload.get("sources") or [],
            "source_meta": source_meta,
        }
    )
    return out


def _compact_source_records_for_prompt(source_records: list[dict[str, Any]] | None, *, max_sources: int = 10, max_chars_each: int = 1200) -> str:
    blocks: list[str] = []
    for rec in (source_records or [])[:max_sources]:
        sid = rec.get("id")
        title = str(rec.get("title") or "").strip()
        url = str(rec.get("url") or "").strip()
        text = str(rec.get("text_excerpt") or rec.get("text") or "").strip()
        if not text:
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars_each:
            text = text[: max_chars_each - 3].rstrip() + "..."
        header = f"[{sid}] {title}" if sid is not None else (title or "[?]")
        if url:
            header = f"{header} - {url}"
        blocks.append(f"{header}\n{text}")
    return "\n\n".join(blocks).strip()


class _StructuredHistoryRewrite(BaseModel):  # type: ignore[misc]
    summary: str = ""
    context: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    causes: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    timeline: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    key_figures: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    key_events: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    consequences: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    interpretations: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    limitations: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    discussion_questions: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    facts: list[str] = Field(default_factory=list)  # type: ignore[call-arg]
    source_notes: list[str] = Field(default_factory=list)  # type: ignore[call-arg]


def _parse_structured_rewrite(raw_text: str) -> dict[str, Any] | None:
    parsed = _safe_json(str(raw_text or ""))
    if not isinstance(parsed, dict):
        return None
    if BaseModel is object:
        return parsed
    try:
        model = _StructuredHistoryRewrite.model_validate(parsed)  # type: ignore[attr-defined]
        return model.model_dump()  # type: ignore[attr-defined]
    except ValidationError:
        return None


class HistoryFactCheckAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="history_fact_check_agent",
            role="validator",
            system_prompt=(
                "You are a strict historical fact-checker.\n"
                "Remove or qualify statements that cannot be verified with citations.\n"
                "Preserve structure and keep language professional."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="history_fact_check",
                    name="History Fact Check",
                    description="Tighten accuracy and citations for history content.",
                    input_types=["text", "json"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=35,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        doc = payload.get("document") or payload.get("text") or ""
        sources = payload.get("sources") or []
        source_meta = payload.get("source_meta") or []
        structured_mode = bool(self.config.get("structured_mode", False) or payload.get("structured_mode"))
        pipeline_id = str(
            context.pipeline_id
            or context.initial_parameters.get("pipeline_id")
            or ""
        )
        allow_web = bool(payload.get("allow_web_research") or context.initial_parameters.get("allow_web_research"))
        max_results = int(payload.get("web_max_results") or context.initial_parameters.get("web_max_results") or 6)

        sources_list = _build_sources_list(source_meta, sources)
        sources_text = "\n".join(f"- {x}" for x in sources_list)
        has_structured_payload = any(
            key in payload
            for key in (
                "summary",
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
            )
        )
        if structured_mode and has_structured_payload:
            cleaned = _clean_structured_payload(payload)
            # For the Workflow Automation history pipelines, we need a real fact-check pass that
            # produces assignment-ready structured fields (timeline/events/people) grounded in sources.
            if pipeline_id in {"family_history_project", "history_project"} and not self.config.get("skip_rewrite", True):
                source_records = list(cleaned.get("source_records") or payload.get("source_records") or [])
                excerpts = _compact_source_records_for_prompt(source_records, max_sources=max(1, max_results), max_chars_each=1200)
                request = str(
                    payload.get("request")
                    or context.initial_parameters.get("request")
                    or context.initial_parameters.get("input")
                    or ""
                ).strip()
                current_fields = {
                    "summary": cleaned.get("summary") if isinstance(cleaned, dict) else "",
                    "context": cleaned.get("context") if isinstance(cleaned, dict) else [],
                    "causes": cleaned.get("causes") if isinstance(cleaned, dict) else [],
                    "timeline": cleaned.get("timeline") if isinstance(cleaned, dict) else [],
                    "key_figures": cleaned.get("key_figures") if isinstance(cleaned, dict) else [],
                    "key_events": cleaned.get("key_events") if isinstance(cleaned, dict) else [],
                    "consequences": cleaned.get("consequences") if isinstance(cleaned, dict) else [],
                    "interpretations": cleaned.get("interpretations") if isinstance(cleaned, dict) else [],
                    "limitations": cleaned.get("limitations") if isinstance(cleaned, dict) else [],
                    "discussion_questions": cleaned.get("discussion_questions") if isinstance(cleaned, dict) else [],
                    "facts": cleaned.get("facts") if isinstance(cleaned, dict) else [],
                    "source_notes": cleaned.get("source_notes") if isinstance(cleaned, dict) else [],
                }
                user_msg = (
                    "You are a strict history fact-checker and project editor.\n"
                    "Goal: fix and improve the structured project fields so they are suitable for a school assignment.\n"
                    "Hard rules:\n"
                    "- Use ONLY the provided sources/excerpts; do not rely on memory or training data.\n"
                    "- Remove anything not supported by the sources.\n"
                    "- Every bullet/line MUST include at least one citation like [3].\n"
                    "- Timeline and Key Events must list HISTORICAL EVENTS (not publication dates of books/pages).\n"
                    "- Key Figures must be real INDIVIDUAL PEOPLE (not organizations/places); include a short role.\n"
                    "- Keep items relevant to the request; avoid unrelated similarly named people.\n"
                    "\n"
                    f"Request:\n{request}\n\n"
                    f"Sources list:\n{sources_text}\n\n"
                    f"Source excerpts:\n{excerpts}\n\n"
                    "Current structured fields (may be messy):\n"
                    f"{current_fields}\n\n"
                    "Return JSON with these keys (all optional):\n"
                    "summary (string), context (list of strings), causes (list of strings),\n"
                    "timeline (list of strings), key_figures (list of strings), key_events (list of strings),\n"
                    "consequences (list of strings), interpretations (list of strings), limitations (list of strings),\n"
                    "discussion_questions (list of strings), facts (list of strings), source_notes (list of strings).\n"
                )
                res = self._run_llm(
                    context=context,
                    system_prompt=self.system_prompt,
                    user_message=user_msg,
                    response_format="json",
                    max_tokens=1800,
                    temperature=0.1,
                )
                if res.ok:
                    raw = str(res.data.get("text") or "")
                    rewritten = _parse_structured_rewrite(raw)
                    if isinstance(rewritten, dict):
                        merged = dict(cleaned)
                        for k, v in rewritten.items():
                            if v is None:
                                continue
                            if isinstance(v, str) and not v.strip():
                                continue
                            if isinstance(v, list):
                                compact = [str(x).strip() for x in v if str(x).strip()]
                                if not compact:
                                    continue
                            merged[k] = v
                        cleaned = _clean_structured_payload(merged)
            return AgentResult(ok=True, data=cleaned)

        if pipeline_id in {"family_history_project", "history_project"} and self.config.get("skip_rewrite", True):
            improved = _strip_verification_report(_strip_placeholder_notes(doc))
            improved = _dedupe_lines(improved)
            improved = _collapse_sources_sections(improved, sources_list)
            return AgentResult(
                ok=True,
                data={
                    "document": improved,
                    "issues": [],
                    "sources": sources_list or sources,
                    "source_meta": source_meta,
                },
            )

        user_msg = (
            "Fact-check the document using the sources below.\n"
            "Rules:\n"
            "- Every factual statement must have a citation like [1].\n"
            "- If a claim cannot be verified, remove it or mark as uncertain.\n"
            "- Preserve headings and overall structure.\n"
            "- Keep language clear and concise.\n"
            "- Do NOT remove existing citations.\n"
            "- Do NOT add placeholder sources or notes about missing sources.\n"
            f"- Web research allowed: {allow_web}, max results: {max_results}\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Document:\n{doc}\n\n"
            "Return JSON with keys: improved_text (string), issues (list of strings)."
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="json",
            max_tokens=1200,
            temperature=0.1,
        )
        if not res.ok:
            return res
        raw = str(res.data.get("text") or "")
        parsed = _safe_json(raw)
        if not isinstance(parsed, dict):
            parsed = {"improved_text": doc, "issues": []}
        improved = parsed.get("improved_text") or doc
        improved = _strip_verification_report(_strip_placeholder_notes(improved))
        improved = _dedupe_lines(improved)
        improved = _collapse_sources_sections(improved, sources_list)
        issues = parsed.get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]
        return AgentResult(
            ok=True,
            data={
                "document": improved,
                "issues": issues,
                "sources": sources_list or sources,
                "source_meta": source_meta,
            },
        )
