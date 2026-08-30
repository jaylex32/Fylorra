from __future__ import annotations

import re
from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent, _safe_json
from core.agents.family_history_writing_agent import FamilyHistoryWritingAgent


class HistoryProjectWritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="history_project_writing_agent",
            role="writer",
            system_prompt=(
                "You are a historian who adapts the writing level to the audience.\n"
                "Default to adult/general audience unless a kids/teen audience is requested.\n"
                "Always keep claims factual, source-grounded, and clearly cited."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="history_project_writing",
                    name="History Project Writing",
                    description="Create a history project that adapts for kids or adults.",
                    input_types=["json", "text"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=45,
                )
            ],
            config=config or {},
        )

    def _audience_level(self, request: str) -> str:
        """Detect target audience from request text"""
        text = request.lower()

        # Check for explicit adult/professional markers first
        adult_markers = [
            "adult",
            "college",
            "university",
            "graduate",
            "professional",
            "academic",
            "historian",
            "scholar",
            "research paper",
            "thesis",
            "dissertation",
        ]
        if any(marker in text for marker in adult_markers):
            return "adult"

        # Check for teen-specific markers
        teen_markers = [
            "teen",
            "teenager",
            "teenagers",
            "high school",
            "secondary school",
            "grade 9",
            "grade 10",
            "grade 11",
            "grade 12",
            "9th grade",
            "10th grade",
            "11th grade",
            "12th grade",
        ]
        if any(marker in text for marker in teen_markers):
            return "teen"

        # Check for kids/elementary markers
        kids_markers = [
            "kid",
            "kids",
            "child",
            "children",
            "elementary",
            "primary school",
            "school project",
            "classroom",
            "homework",
            "for kids",
            "for children",
            "grade 1",
            "grade 2",
            "grade 3",
            "grade 4",
            "grade 5",
            "grade 6",
            "grade 7",
            "grade 8",
            "1st grade",
            "2nd grade",
            "3rd grade",
            "4th grade",
            "5th grade",
            "6th grade",
            "7th grade",
            "8th grade",
            "first grade",
            "second grade",
            "third grade",
            "fourth grade",
            "fifth grade",
            "sixth grade",
            "seventh grade",
            "eighth grade",
        ]
        if any(marker in text for marker in kids_markers):
            return "kid"

        # Check for age ranges (e.g., "ages 8-12", "ages 5 to 10")
        age_range = re.search(r"\bages?\s*(\d{1,2})\s*(?:-|to)\s*(\d{1,2})", text)
        if age_range:
            try:
                start = int(age_range.group(1))
                end = int(age_range.group(2))
                if max(start, end) <= 12:
                    return "kid"
                if max(start, end) <= 17:
                    return "teen"
            except Exception:
                pass

        # Check for single age (e.g., "age 10", "10 years old")
        single_age = re.search(r"\b(?:age|ages)\s*(\d{1,2})\b|\b(\d{1,2})\s*years?\s+old", text)
        if single_age:
            try:
                age = int(single_age.group(1) or single_age.group(2))
                if age <= 12:
                    return "kid"
                if age <= 17:
                    return "teen"
                return "adult"
            except Exception:
                pass

        # Default to adult for unspecified audience
        return "adult"

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        # Unify history/biography quality across templates by delegating to the
        # polished school-assignment writer.
        return FamilyHistoryWritingAgent(config=dict(self.config or {})).execute(context, inputs)

        payload = dict(inputs or {})
        request = str(payload.get("user_request") or context.user_request or "").strip()
        summary = payload.get("summary") or ""
        timeline = payload.get("timeline") or []
        key_figures = payload.get("key_figures") or []
        key_events = payload.get("key_events") or []
        facts = payload.get("facts") or []
        claims = payload.get("claims") or []
        context_points = payload.get("context") or []
        causes = payload.get("causes") or []
        consequences = payload.get("consequences") or []
        source_notes = payload.get("source_notes") or []
        interpretations = payload.get("interpretations") or payload.get("historiography") or []
        dissenting_views = payload.get("dissenting_views") or payload.get("dissenting_perspectives") or []
        critical_analysis = payload.get("critical_analysis") or {}
        limitations = payload.get("limitations") or payload.get("further_research") or []
        discussion_questions = payload.get("discussion_questions") or payload.get("questions") or []
        sources = payload.get("sources") or []
        source_meta = payload.get("source_meta") or []
        source_records = payload.get("source_records") or []

        # === CLEAN ALL LIST FIELDS TO REMOVE RAW DICTIONARIES ===
        # The research agent may return structured data as dicts, which need to be converted to strings

        def _extract_text_from_item(item: Any) -> str:
            """Extract clean text from dict/string items (handles structured data from research agent)"""
            if item is None or item == "":
                return ""

            # Handle dictionary format from research agent
            if isinstance(item, dict):
                # Try to extract statement/text/description
                text = (
                    item.get("statement") or
                    item.get("text") or
                    item.get("description") or
                    item.get("detail") or
                    item.get("name") or
                    item.get("person") or
                    ""
                ).strip()

                # Try to extract citation
                citation = ""
                source_id = item.get("source_id") or item.get("citation") or item.get("source")
                if source_id:
                    citation = f" [{source_id}]"

                # Combine text and citation
                if text:
                    return f"{text}{citation}".strip()

                # Fallback: if dict has no recognized fields, convert to string and clean
                # But skip if it looks like a raw dict dump
                str_repr = str(item)
                if "{'statement':" in str_repr or '{"statement":' in str_repr:
                    return ""  # Skip malformed dicts
                return str_repr

            # Handle string
            text = str(item).strip()

            # Clean up if it's a stringified dict
            if text.startswith("{'") or text.startswith('{"'):
                # This shouldn't happen but if it does, try to extract statement
                import json
                try:
                    parsed = json.loads(text.replace("'", '"'))
                    if isinstance(parsed, dict):
                        return _extract_text_from_item(parsed)
                except:
                    return ""  # Skip unparseable dicts

            return text

        def _clean_list_field(items: list) -> list:
            """Convert list items (including dicts) to clean strings"""
            if not isinstance(items, list):
                return []
            cleaned = []
            for item in items:
                text = _extract_text_from_item(item)
                if text:
                    cleaned.append(text)
            return cleaned

        # Clean all list fields that might contain dictionaries
        # NOTE: interpretations is NOT cleaned here because _format_interpretations() expects dicts
        timeline = _clean_list_field(timeline)
        key_figures = _clean_list_field(key_figures)
        key_events = _clean_list_field(key_events)
        facts = _clean_list_field(facts)
        claims = _clean_list_field(claims)
        context_points = _clean_list_field(context_points)
        causes = _clean_list_field(causes)
        consequences = _clean_list_field(consequences)
        source_notes = _clean_list_field(source_notes)
        # interpretations: Keep as-is (dicts) for _format_interpretations() to handle
        dissenting_views = _clean_list_field(dissenting_views)
        limitations = _clean_list_field(limitations)
        discussion_questions = _clean_list_field(discussion_questions)

        if isinstance(summary, dict):
            summary = str(summary.get("summary") or "")
        elif isinstance(summary, str):
            # Guard: sometimes upstream stages accidentally pass the whole JSON blob as the "summary".
            maybe = _safe_json(summary)
            if maybe and isinstance(maybe.get("summary"), str):
                summary = maybe.get("summary") or ""

        if source_meta:
            sources = []
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
                sources.append(entry)

        def _norm_for_match(text: str) -> str:
            import unicodedata

            value = unicodedata.normalize("NFKC", str(text or ""))
            value = value.replace("\u00A0", " ")
            value = unicodedata.normalize("NFKD", value)
            value = "".join(ch for ch in value if not unicodedata.combining(ch))
            value = value.lower()
            value = re.sub(r"[^a-z0-9\s]", " ", value)
            value = re.sub(r"\s+", " ", value).strip()
            return value

        # Pre-normalize source excerpts for fast "name exists in source" checks.
        source_text_norm_by_id: dict[int, str] = {}
        try:
            for rec in source_records:
                sid = rec.get("id")
                if sid is None:
                    continue
                try:
                    sid_int = int(sid)
                except Exception:
                    continue
                excerpt = str(rec.get("text_excerpt") or rec.get("text") or "")
                if excerpt:
                    source_text_norm_by_id[sid_int] = _norm_for_match(excerpt)
        except Exception:
            source_text_norm_by_id = {}

        def _name_supported_by_sources(name: str, citation_ids: list[int]) -> bool:
            # If we don't have excerpts (older executions), don't block.
            if not source_text_norm_by_id or not citation_ids:
                return True
            needle = _norm_for_match(name)
            if not needle or len(needle) < 3:
                return False
            for sid in citation_ids:
                hay = source_text_norm_by_id.get(int(sid))
                if hay and needle in hay:
                    return True
            return False

        def _list(items: Any) -> str:
            """Convert list of items to formatted bullet list"""
            if isinstance(items, list):
                clean_items = []
                for item in items:
                    text = _extract_text_from_item(item)
                    if text:
                        clean_items.append(f"- {text}")
                return "\n".join(clean_items)
            return str(items)

        def _clean_document(doc: str) -> str:
            if not doc:
                return doc
            # Fix common UTF-8→cp1252 mojibake seen in scraped text (kept small/safe).
            mojibake_map = {
                "â€™": "’",
                "â€˜": "‘",
                "â€œ": "“",
                "â€�": "”",
                "â€”": "—",
                "â€“": "–",
                "â€¦": "…",
                "Â·": "·",
                "Â": "",
                "Ã±": "ñ",
                "Ã‘": "Ñ",
                "Ã¡": "á",
                "Ã©": "é",
                "Ã­": "í",
                "Ã³": "ó",
                "Ãº": "ú",
                "Ã¼": "ü",
                "Ã": "Á",
                "Ã‰": "É",
                "Ã": "Í",
                "Ã“": "Ó",
                "Ãš": "Ú",
                "Ãœ": "Ü",
            }
            for bad, good in mojibake_map.items():
                doc = doc.replace(bad, good)
            doc = re.sub(r"(?<!\n)(#{2,}\s+)", r"\n\1", doc)

            def _norm_line(text: str) -> str:
                # Remove both our citations and common scraped footnote markers.
                cleaned = re.sub(r"\[\s*\d+\s*\]", "", text)
                cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
                return cleaned

            lines = doc.splitlines()
            cleaned_lines: list[str] = []
            list_seen: set[str] = set()
            in_list = False
            for line in lines:
                stripped = line.strip()
                if stripped in {"#", "##", "###", "####"}:
                    continue
                if not stripped:
                    cleaned_lines.append(line)
                    list_seen = set()
                    in_list = False
                    continue
                is_list = stripped.startswith("-") or stripped.startswith("*")
                if is_list:
                    key = _norm_line(stripped.lstrip("-* ").strip())
                    if key in list_seen:
                        continue
                    list_seen.add(key)
                    cleaned_lines.append(line)
                    in_list = True
                    continue
                if in_list:
                    list_seen = set()
                    in_list = False
                cleaned_lines.append(line)

            text = "\n".join(cleaned_lines)

            def _dedupe_headers(text_block: str) -> str:
                targets = {
                    "sources",
                    "discussion questions",
                    "key people",
                    "key events",
                    "timeline",
                    "limitations and further research",
                    "different historical interpretations",
                    "different perspectives",
                }
                seen_headers: set[str] = set()
                output: list[str] = []
                skip = False
                for line in text_block.splitlines():
                    match = re.match(r"^\s*##+\s+(.+)$", line)
                    if match:
                        header_title = match.group(1).strip().lower()
                        if header_title in targets:
                            if header_title in seen_headers:
                                skip = True
                                continue
                            seen_headers.add(header_title)
                        skip = False
                        output.append(line)
                        continue
                    if skip:
                        continue
                    output.append(line)
                return "\n".join(output)

            text = _dedupe_headers(text)
            blocks = re.split(r"\n{2,}", text)
            cleaned_blocks: list[str] = []
            for block in blocks:
                block_strip = block.strip()
                if not block_strip:
                    continue
                first = block_strip.splitlines()[0].strip()
                if first.startswith("#") or first.startswith("-") or first.startswith("*"):
                    cleaned_blocks.append(block_strip)
                    continue
                safe = block_strip.replace("U.S.", "U_S_")
                sentences = re.split(r"(?<=[.!?])\s+", safe)
                seen_s: set[str] = set()
                out_s: list[str] = []
                for sentence in sentences:
                    s = sentence.strip()
                    if not s:
                        continue
                    key = _norm_line(s)
                    if key in seen_s:
                        continue
                    seen_s.add(key)
                    out_s.append(s)
                rebuilt = " ".join(out_s).replace("U_S_", "U.S.")
                cleaned_blocks.append(rebuilt.strip())
            return "\n\n".join(cleaned_blocks)

        def _coerce_list(items: Any) -> list[str]:
            if isinstance(items, list):
                return [str(x).strip() for x in items if str(x).strip()]
            if items:
                return [str(items).strip()]
            return []
        
        def _coerce_any_list(items: Any) -> list[Any]:
            if items is None:
                return []
            if isinstance(items, list):
                return [x for x in items if x is not None]
            return [items]

        def _coerce_citation(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, int):
                return f"[{value}]"
            text = str(value).strip()
            if not text:
                return ""
            if re.fullmatch(r"\d+", text):
                return f"[{text}]"
            match = re.search(r"\[\d+\]", text)
            return match.group(0) if match else text

        def _coerce_people(items: Any) -> list[str]:
            if not items:
                return []
            if not isinstance(items, list):
                items = [items]
            out: list[str] = []
            for item in items:
                if item is None:
                    continue
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("person") or "").strip()
                    role = str(item.get("role") or item.get("description") or "").strip()
                    citation = _coerce_citation(item.get("citation") or item.get("citations") or item.get("source") or item.get("source_id"))
                    if name and role:
                        out.append(f"{name} - {role} {citation}".strip())
                    elif name:
                        out.append(f"{name} {citation}".strip())
                    continue
                text = str(item).strip()
                if text:
                    out.append(text)
            return out

        def _coerce_events(items: Any) -> list[str]:
            if not items:
                return []
            if not isinstance(items, list):
                items = [items]
            out: list[str] = []
            for item in items:
                if item is None:
                    continue
                if isinstance(item, dict):
                    date = str(item.get("date") or item.get("year") or "").strip()
                    title = str(item.get("title") or "").strip()
                    desc = str(item.get("description") or item.get("detail") or "").strip()
                    citation = _coerce_citation(item.get("citation") or item.get("citations") or item.get("source") or item.get("source_id"))
                    head = ""
                    body = ""
                    if date:
                        head = f"{date}:"
                        body = " ".join(x for x in [title, desc] if x).strip()
                    elif title:
                        head = f"{title}:"
                        body = desc.strip()
                    else:
                        body = desc.strip()
                    if head and body:
                        out.append(f"{head} {body} {citation}".strip())
                    elif body:
                        out.append(f"{body} {citation}".strip())
                    continue
                text = str(item).strip()
                if text:
                    out.append(text)
            return out

        def _norm_for_filter(text: str) -> str:
            cleaned = re.sub(r"\[\d+\]", "", str(text or ""))
            cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
            return cleaned

        def _is_placeholder_timeline(item: str) -> bool:
            lowered = _norm_for_filter(item)
            banned = [
                "begins to consider",
                "began to consider",
                "starts to consider",
                "starts to",
                "tbd",
                "placeholder",
                "to be determined",
                "begins considering",
                "begins to debate",
                "political status",
                "establishes a new",
                "establishes new",
                "establishes a new system",
                "establishes a new legal system",
                "establishes a new education system",
                "establishes a new economic system",
                "establishes a new political system",
                "establishes a new social system",
            ]
            return any(phrase in lowered for phrase in banned)

        def _is_publication_line(item: str) -> bool:
            lowered = _norm_for_filter(item)
            if not lowered:
                return True
            publication_markers = [
                "published",
                "publication",
                "study",
                "book",
                "work discussed",
                "work was",
                "report was",
                "report discussed",
                "report of",
                "first major historical study",
                "in english",
                "library of congress",
                "special holiday hours",
                "top of page",
                "preservation microfilming",
                "photoduplication service",
                "available from",
                "catalog",
                "digital id",
                "the history of",
            ]
            if any(marker in lowered for marker in publication_markers):
                return True
            if "work" in lowered and "discussed" in lowered:
                return True
            if re.search(r"^\(?\s*\d{4}\s*\)?\s+(report|history|the history)\b", lowered):
                return True
            return False

        def _filter_events(items: list[str], *, max_items: int) -> list[str]:
            def _is_low_information_event_line(value: str) -> bool:
                text = str(value or "").strip()
                if not text:
                    return True
                stripped = re.sub(r"\[\d+\]", "", text).strip()
                if not stripped:
                    return True
                compact = re.sub(r"\s+", " ", stripped).strip()
                if re.fullmatch(
                    r"^\s*(?:\(?\s*)?(?:1[5-9]\d{2}|20\d{2})(?:\s*[-–—]\s*(?:1[5-9]\d{2}|20\d{2}))?(?:\)?\s*)[:\-–—]*\s*$",
                    stripped,
                ):
                    return True
                if stripped.endswith(("(", "[", "{", "-", "—", "–", ":", ",")):
                    return True
                if stripped.count("(") != stripped.count(")"):
                    return True
                if re.search(r"\(\s*\)", compact):
                    return True
                if len(stripped) < 8 and re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", stripped):
                    return True

                # Drop "blank hole" lines (missing date parts), e.g.:
                # - "began on , when ..."
                # - "served ... from  to May 1900"
                # - "Act of  granted ..."
                if re.search(r"\bbegan\s+on\s*,", stripped, flags=re.IGNORECASE):
                    return True
                if re.search(r"\b(?:in|since)\s*,", compact, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bin\s+after\b", compact, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bon\s*,\s*(?:when|which)\b", stripped, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bfrom\s*(?:,)?\s*to\b", stripped, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bin\s{2,}(?:and|to|from|when|which)\b", stripped, flags=re.IGNORECASE):
                    return True
                # After whitespace is collapsed, missing-date holes can appear as "in and subsequent ...".
                if re.search(r"\bin\s+and\s+(?:subsequent|later|after|then)\b", compact, flags=re.IGNORECASE):
                    return True
                # Another common missing-date hole: "… in during/under/via …" (a date was stripped upstream).
                if re.search(r"\bin\s+(?:during|under|via)\b", compact, flags=re.IGNORECASE):
                    return True
                # Dangling preposition at end after citations removed: "… in [2]." → "… in ."
                if re.search(r"\b(?:on|in|of|from|to|since|until)\s*[,.;)]?\s*$", compact, flags=re.IGNORECASE):
                    return True
                if re.search(
                    r"\bof\s+(?:granted|passed|signed|enacted|ratified|ceded|transferred|created|established)\b",
                    compact,
                    flags=re.IGNORECASE,
                ):
                    return True
                if "to the present" in compact.lower() or "encompasses the period" in compact.lower():
                    return True
                return False

            out: list[str] = []

            def _token_set(text: str) -> set[str]:
                base = _norm_for_filter(re.sub(r"\[\d+\]", "", text))
                tokens = [t for t in re.split(r"\s+", base) if len(t) > 2]
                stop = {
                    "the",
                    "and",
                    "for",
                    "with",
                    "from",
                    "into",
                    "after",
                    "before",
                    "between",
                    "under",
                    "over",
                    "about",
                    "that",
                    "this",
                    "were",
                    "was",
                    "are",
                    "been",
                    "then",
                    "than",
                    "when",
                    "which",
                    "their",
                    "they",
                }
                return {t for t in tokens if t not in stop}

            def _is_near_duplicate(candidate: str) -> bool:
                month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

                def _date_key(text: str) -> str:
                    raw = re.sub(r"\[\d+\]", "", str(text or "")).strip()
                    if not raw:
                        return ""
                    m = re.match(
                        rf"^\s*(?P<d>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[:\-–—]",
                        raw,
                        flags=re.IGNORECASE,
                    )
                    if m:
                        return m.group("d").strip().lower()
                    m = re.match(r"^\s*(?P<y>\d{4})\b", raw)
                    if m:
                        return m.group("y")
                    return ""

                cand_set = _token_set(candidate)
                if not cand_set:
                    return False
                cand_date = _date_key(candidate)
                for existing in out:
                    ex_set = _token_set(existing)
                    if not ex_set:
                        continue
                    ex_date = _date_key(existing)
                    if cand_date and ex_date and cand_date == ex_date:
                        inter = len(cand_set & ex_set)
                        union = len(cand_set | ex_set)
                        if union and (inter / union) >= 0.55:
                            return True
                    inter = len(cand_set & ex_set)
                    union = len(cand_set | ex_set)
                    if union and (inter / union) >= 0.85:
                        return True
                return False

            for item in items:
                text = str(item or "").strip()
                if not text:
                    continue
                if _is_publication_line(text) or _is_placeholder_timeline(text):
                    continue
                if _is_low_information_event_line(text):
                    continue
                if len(re.sub(r"\[\d+\]", "", text).strip()) < 8 and not re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text):
                    continue
                if _is_near_duplicate(text):
                    continue
                out.append(text)
                if len(out) >= max_items:
                    break
            return out

        def _has_event_keyword(item: str) -> bool:
            lowered = _norm_for_filter(item)
            keywords = [
                # General event cues (do not hardcode topic-specific names).
                "treaty",
                "act",
                "law",
                "constitution",
                "attack",
                "attacks",
                "bombard",
                "bombardment",
                "blockade",
                "armistice",
                "protocol",
                "decree",
                "order",
                "proclamation",
                "war",
                "campaign",
                "battle",
                "invasion",
                "occupation",
                "annex",
                "cession",
                "ceded",
                "transfer",
                "independence",
                "revolution",
                "uprising",
                "coup",
                "protest",
                "election",
                "referendum",
                "congress",
                "senate",
                "parliament",
                "assembly",
                "court",
                "governor",
                "president",
                "prime minister",
                "citizenship",
                "rights",
                "signed",
                "ratified",
                "passed",
                "approved",
                "declared",
                "began",
                "ended",
                "landed",
                "captured",
                "surrender",
                "appointed",
                "abolished",
                "granted",
            ]
            return any(key in lowered for key in keywords)

        def _topic_tokens_in_order(text: str) -> list[str]:
            raw = _norm_for_filter(text)
            if not raw:
                return []
            raw = re.sub(r"[^a-z0-9\s]", " ", raw)
            tokens = [t for t in raw.split() if 3 <= len(t) <= 24]
            if not tokens:
                return []
            stop = {
                "a",
                "an",
                "and",
                "are",
                "as",
                "at",
                "be",
                "by",
                "create",
                "essay",
                "for",
                "from",
                "history",
                "how",
                "in",
                "into",
                "is",
                "it",
                "make",
                "of",
                "on",
                "or",
                "paper",
                "project",
                "report",
                "the",
                "this",
                "to",
                "took",
                "over",
                "was",
                "were",
                "what",
                "when",
                "where",
                "which",
                "who",
                "with",
                "write",
                "writing",
                "your",
                "united",
                "states",
                "state",
                "government",
                "america",
                "american",
                "between",
                "during",
                "after",
                "before",
                "today",
                "yesterday",
                "tomorrow",
            }
            return [t for t in tokens if t not in stop]

        def _topic_keywords_for_filter(text: str) -> list[str]:
            tokens = _topic_tokens_in_order(text)
            if not tokens:
                return []
            # Prefer longer, more distinctive tokens to avoid accidental matches.
            tokens = sorted(set(tokens), key=lambda t: (-len(t), t))
            return tokens[:10]

        def _topic_phrases_for_filter(text: str) -> list[str]:
            ordered = _topic_tokens_in_order(text)
            if not ordered:
                return []
            phrases: list[str] = []
            for n in (2, 3):
                for i in range(0, max(0, len(ordered) - n + 1)):
                    phrase = " ".join(ordered[i : i + n]).strip()
                    if phrase and phrase not in phrases:
                        phrases.append(phrase)
            return phrases[:12]

        def _subject_phrases_from_request(text: str) -> list[str]:
            # Extract multi-word TitleCase phrases from the ORIGINAL request so we can filter
            # the subject itself (e.g., "Puerto Rico") from Key People without hardcoding facts.
            if not text:
                return []
            cleaned = re.sub(r"[\"“”]", "", str(text))
            candidates = re.findall(r"\b(?:[A-Z][a-z]{1,25}|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]{1,25}|[A-Z]{2,})){1,5}\b", cleaned)
            ignore = {
                "How",
                "What",
                "When",
                "Where",
                "Why",
                "Create",
                "Write",
                "History",
                "Project",
                "Essay",
                "Report",
                "Invasion",
                "Occupation",
                "Control",
            }
            out: list[str] = []
            for phrase in candidates:
                parts = [p for p in phrase.split() if p]
                if not parts:
                    continue
                if parts[0] in ignore:
                    continue
                norm = " ".join(parts).strip().lower()
                norm = re.sub(r"[^a-z0-9\\s]", "", norm)
                norm = re.sub(r"\\s+", " ", norm).strip()
                if len(norm.split()) < 2:
                    continue
                if norm and norm not in out:
                    out.append(norm)
            if not out:
                # Requests are often lowercased; fall back to topic tokens in order.
                ordered = _topic_tokens_in_order(text)
                for n in (2, 3):
                    for i in range(0, max(0, len(ordered) - n + 1)):
                        phrase = " ".join(ordered[i : i + n]).strip()
                        if phrase and phrase not in out:
                            out.append(phrase)
            # Common Spanish variant mapping: "Puerto X" is often written "Porto X" in older texts.
            variants: list[str] = []
            for phrase in out:
                if phrase.startswith("puerto "):
                    variants.append("porto " + phrase[len("puerto ") :])
                if phrase.startswith("porto "):
                    variants.append("puerto " + phrase[len("porto ") :])
            for v in variants:
                if v and v not in out:
                    out.append(v)
            return out[:10]

        def _starts_with_date_prefix(text: str) -> bool:
            month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            return bool(
                re.match(
                    rf"^\s*(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}})\s*[:\-–—]\s*",
                    str(text or ""),
                )
            )

        def _filter_timeline(items: list[str], *, max_items: int) -> list[str]:
            topic_keys = _topic_keywords_for_filter(request)
            month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

            date_pattern = re.compile(
                r"(?P<date>"
                r"(?:\d{4}(?:-\d{4})?)"
                rf"|(?:{month_re}\s+\d{{1,2}},\s*\d{{4}})"
                rf"|(?:{month_re}\s+\d{{4}})"
                rf"|(?:\d{{1,2}}\s+{month_re}\s+\d{{4}})"
                r")"
            )

            def _has_blank_hole(value: str) -> bool:
                text = re.sub(r"\[\d+\]", "", str(value or "")).strip()
                text = re.sub(r"\s+", " ", text).strip()
                if not text:
                    return True
                if re.search(r"\(\s*\)", text):
                    return True
                if re.search(r"\bbegan\s+on\s*,", text, flags=re.IGNORECASE):
                    return True
                # Common extraction failure: the date was removed, leaving "began in with ...".
                if re.search(r"\bbegan\s+in\s+with\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\b(?:in|since)\s*,", text, flags=re.IGNORECASE):
                    return True
                # Another blank-hole variant: "until , when ..." (missing the end date).
                if re.search(r"\buntil\s*,\s*(?:when|which)\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bin\s+after\b", text, flags=re.IGNORECASE):
                    return True
                # Another common artifact after stripping a date: "in following ..."
                if re.search(r"\bin\s+(?:the\s+)?following\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bon\s*,\s*(?:when|which)\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bfrom\s*(?:,)?\s*to\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bserved\s+from\s+to\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bin\s+and\s+(?:subsequent|later|after|then)\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(r"\bin\s+(?:during|under|via)\b", text, flags=re.IGNORECASE):
                    return True
                # Dangling preposition at end (common when a date got stripped upstream).
                if re.search(r"\b(?:on|in|of|from|to|since|until)\s*[,.;)]?\s*$", text, flags=re.IGNORECASE):
                    return True
                if re.search(
                    r"\b(?:Act\s+of|of)\s+(?:granted|passed|signed|enacted|ratified|ceded|transferred|created|established)\b",
                    text,
                    flags=re.IGNORECASE,
                ):
                    return True
                if "to the present" in text.lower() or "encompasses the period" in text.lower():
                    return True
                return False

            def _ensure_date_prefix(value: str) -> str | None:
                text = str(value or "").strip()
                if not text:
                    return None
                if _is_publication_line(text) or _is_placeholder_timeline(text):
                    return None
                if _starts_with_date_prefix(text):
                    # Date-prefixed lines can still be broken if upstream extraction removed a date
                    # and left a dangling preposition like "began on , when ...".
                    parts = re.split(r"\s*:\s*", text, 1)
                    if len(parts) == 2:
                        rhs = parts[1].strip()
                        # Clean common artifacts even when the line is already date-prefixed (e.g. upstream
                        # extraction removed an embedded date and left "began in and ..." or "until  with ...").
                        rhs = re.sub(r"\b(on|in)\s*,\s*", "", rhs, flags=re.IGNORECASE)
                        rhs = re.sub(r"\b(on|in)\s+(?=and\b)", "", rhs, flags=re.IGNORECASE)
                        # Salvage blank-hole phrases like "until , when ..." by dropping the missing date fragment.
                        rhs = re.sub(r"\buntil\s*,\s*(when|which)\b", r"\1", rhs, flags=re.IGNORECASE)
                        rhs = re.sub(r"\b(on|in)\s*,\s*(when|which)\b", r"\2", rhs, flags=re.IGNORECASE)
                        rhs = re.sub(
                            r"\b(on|in)\s+(?=(?:formally|officially|signed|ratified|passed|enacted|began|ended|started|established|created|issued|appointed)\b)",
                            "",
                            rhs,
                            flags=re.IGNORECASE,
                        )
                        rhs = re.sub(r"\buntil\s+(?:with|by)\s+(?=the\b)", "until ", rhs, flags=re.IGNORECASE)
                        rhs = re.sub(r"^([A-Z][A-Za-z.'’\-]{2,30}),\s+(?=was\b)", r"\1 ", rhs)
                        rhs = re.sub(r"\s{2,}", " ", rhs).strip()
                        if _has_blank_hole(rhs):
                            return None
                        if rhs and rhs[:1].islower():
                            # Salvage common lowercase starters like "the …"; otherwise treat as fragment.
                            if re.match(r"^(the|a|an)\b", rhs, flags=re.IGNORECASE):
                                rhs = rhs[:1].upper() + rhs[1:]
                                return f"{parts[0].strip()}: {rhs}"
                            return None
                        return f"{parts[0].strip()}: {rhs}" if rhs else None
                    return text
                if _has_blank_hole(text):
                    return None
                if not re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text):
                    return None
                # Drop broad "overview" lines that are not timeline events.
                lowered = _norm_for_filter(text)
                if "encompasses" in lowered or "to the present" in lowered:
                    return None
                # If we had to *extract* a date from the middle of the sentence and it contains multiple
                # distinct years, it's usually background context (e.g. "between 1860 and 1898"),
                # not a single timeline event.
                years = set(re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", text))
                if len(years) > 1:
                    return None
                # Handle leading date ranges like "Oct 1898 – Dec 9, 1898: ...".
                range_match = re.match(
                    rf"^\s*(?P<d1>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[-–—]\s*(?P<d2>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[:\-–—]\s*(?P<rest>.+)$",
                    text,
                )
                if range_match:
                    d1 = range_match.group("d1").strip()
                    d2 = range_match.group("d2").strip()
                    rest = range_match.group("rest").strip()
                    if rest:
                        return f"{d1} – {d2}: {rest}"
                match = date_pattern.search(text)
                if not match:
                    return None
                date = match.group("date").strip()
                remainder = (text[: match.start()] + text[match.end() :]).strip()
                remainder = remainder.lstrip(" ,;:-—–").strip()
                # If we removed a date from phrases like "began on <date>, ...", remove the dangling preposition+comma.
                remainder = re.sub(r"\b(on|in)\s*,\s*", "", remainder, flags=re.IGNORECASE)
                # If we removed a date from phrases like "began in <date> and ...", remove the dangling preposition.
                remainder = re.sub(r"\b(on|in)\s+(?=and\b)", "", remainder, flags=re.IGNORECASE)
                # If we removed a date from phrases like "until <date>, when ...", remove the dangling "until ,".
                remainder = re.sub(r"\buntil\s*,\s*(when|which)\b", r"\1", remainder, flags=re.IGNORECASE)
                # If we removed a date from "in <date> formally/officially ...", remove the dangling "in"/"on".
                remainder = re.sub(
                    r"\b(on|in)\s+(?=(?:formally|officially|signed|ratified|passed|enacted|began|ended|started|established|created|issued|appointed)\b)",
                    "",
                    remainder,
                    flags=re.IGNORECASE,
                )
                # If we removed a date from "in <date> following ...", remove the dangling "in"/"on".
                remainder = re.sub(
                    r"\b(on|in)\s+(?=(?:the\s+)?following\b)",
                    "",
                    remainder,
                    flags=re.IGNORECASE,
                )
                # Common artifact when an intervening date got stripped: "until  with the ...".
                remainder = re.sub(r"\buntil\s+(?:with|by)\s+(?=the\b)", "until ", remainder, flags=re.IGNORECASE)
                # If we removed a date from "in <date> [citation]" or "of <date> [citation]", remove the dangling preposition.
                remainder = re.sub(r"\b(of|in|on)\s+(?=\[\d+\])", "", remainder, flags=re.IGNORECASE)
                # If we removed a year from "Act of <year> established...", remove the dangling "of".
                remainder = re.sub(
                    r"\bof\s+(?=(?:formally|officially|signed|ratified|passed|enacted|began|ended|started|established|created|issued|appointed)\b)",
                    "",
                    remainder,
                    flags=re.IGNORECASE,
                )
                remainder = re.sub(r"\s{2,}", " ", remainder).strip()
                if not remainder:
                    return None
                if _has_blank_hole(remainder):
                    return None
                # Drop fragments like "Taft, appointed ..." (often leftover after a date was stripped upstream).
                if re.match(
                    r"^[A-Z][A-Za-z.'’\-]{2,30},\s*(?:was\s+)?(?:appointed|named|elected|selected|killed|born|died)\b",
                    remainder,
                ):
                    return None
                if remainder[:1].islower():
                    if re.match(r"^(the|a|an)\b", remainder, flags=re.IGNORECASE):
                        remainder = remainder[:1].upper() + remainder[1:]
                    else:
                        return None
                # Require citations for timeline items; prevents uncited/truncated lines from sneaking in.
                if not re.search(r"\[\d+\]", remainder) and not re.search(r"\[\d+\]", text):
                    return None
                return f"{date}: {remainder}"

            def _has_action_verb(text: str) -> bool:
                lowered = _norm_for_filter(text)
                verbs = [
                    "signed",
                    "ratified",
                    "passed",
                    "approved",
                    "enacted",
                    "declared",
                    "began",
                    "begins",
                    "ended",
                    "landed",
                    "land",
                    "invaded",
                    "occupied",
                    "surrender",
                    "surrendered",
                    "ceded",
                    "transferred",
                    "raised",
                    "lowered",
                    "appointed",
                    "served",
                    "serves",
                    "established",
                    "created",
                    "granted",
                    "became",
                    "becomes",
                    "formed",
                    "issued",
                    "implemented",
                    "reorganized",
                    "reorganized",
                    "annexed",
                ]
                return any(v in lowered for v in verbs)

            month_map = {
                "jan": 1,
                "january": 1,
                "feb": 2,
                "february": 2,
                "mar": 3,
                "march": 3,
                "apr": 4,
                "april": 4,
                "may": 5,
                "jun": 6,
                "june": 6,
                "jul": 7,
                "july": 7,
                "aug": 8,
                "august": 8,
                "sep": 9,
                "sept": 9,
                "september": 9,
                "oct": 10,
                "october": 10,
                "nov": 11,
                "november": 11,
                "dec": 12,
                "december": 12,
            }

            def _timeline_sort_key(value: str) -> tuple[int, int, int]:
                text = str(value or "").strip()
                text = re.sub(r"\s+", " ", text)
                date = re.split(r"\s*[:\-–—]\s*", text, 1)[0].strip()
                m = re.match(r"^(?P<y1>\d{4})(?:-(?P<y2>\d{4}))?$", date)
                if m:
                    return (int(m.group("y1")), 0, 0)
                m = re.match(r"^(?P<mon>[A-Za-z]+)\s+(?P<year>\d{4})$", date)
                if m:
                    mon = month_map.get(m.group("mon").lower(), 0)
                    return (int(m.group("year")), mon, 0)
                m = re.match(r"^(?P<mon>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})$", date)
                if m:
                    mon = month_map.get(m.group("mon").lower(), 0)
                    return (int(m.group("year")), mon, int(m.group("day")))
                m = re.match(r"^(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]+)\s+(?P<year>\d{4})$", date)
                if m:
                    mon = month_map.get(m.group("mon").lower(), 0)
                    return (int(m.group("year")), mon, int(m.group("day")))
                year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text)
                if year_match:
                    return (int(year_match.group(1)), 0, 0)
                return (9999, 0, 0)

            def _cap_by_year(values: list[str], *, max_per_year: int = 2) -> list[str]:
                def _date_prefix(text: str) -> str:
                    raw = str(text or "").strip()
                    # Prefer a full prefix up to ":" to preserve ranges like "Oct 1898 – Dec 9, 1898".
                    if ":" in raw:
                        return raw.split(":", 1)[0].strip()
                    return re.split(r"\s*[:\-–—]\s*", raw, 1)[0].strip()

                def _specificity_score(text: str) -> int:
                    prefix = _date_prefix(text)
                    # Prefer more precise dates (month+day > month > year).
                    def _base_for(d: str) -> int:
                        d = d.strip()
                        if re.match(rf"^{month_re}\s+\d{{1,2}},\s*\d{{4}}$", d, flags=re.IGNORECASE):
                            return 30
                        if re.match(rf"^\d{{1,2}}\s+{month_re}\s+\d{{4}}$", d, flags=re.IGNORECASE):
                            return 30
                        if re.match(rf"^{month_re}\s+\d{{4}}$", d, flags=re.IGNORECASE):
                            return 20
                        if re.match(r"^\d{4}(?:-\d{4})?$", d):
                            return 10
                        return 0

                    if re.search(r"\s[-–—]\s", prefix):
                        left, right = re.split(r"\s[-–—]\s", prefix, 1)
                        base = max(_base_for(left), _base_for(right)) + 5
                    else:
                        base = _base_for(prefix)
                    if re.search(r"\[\d+\]", text):
                        base += 3
                    if _has_action_verb(text):
                        base += 3
                    if _has_event_keyword(text):
                        base += 1
                    # Prefer well-formed sentences; fragments often start with lowercase after date stripping.
                    parts = re.split(r"\s*:\s*", text, 1)
                    if len(parts) == 2:
                        rhs = parts[1].strip()
                        if rhs and rhs[:1].islower():
                            base -= 4
                    # Penalize very long / summary-like lines.
                    plain = re.sub(r"\[\d+\]", "", text).strip()
                    if len(plain) > 220:
                        base -= 6
                    if "encompasses" in _norm_for_filter(text) or "to the present" in _norm_for_filter(text):
                        base -= 8
                    return base

                by_year: dict[int, list[str]] = {}
                for item in values:
                    year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", item)
                    if not year_match:
                        continue
                    year = int(year_match.group(1))
                    by_year.setdefault(year, []).append(item)

                out: list[str] = []
                for year in sorted(by_year.keys()):
                    candidates = by_year[year]
                    candidates = sorted(
                        candidates,
                        key=lambda t: (-_specificity_score(t), _timeline_sort_key(t), _norm_for_filter(t)),
                    )
                    seen_dates: set[str] = set()
                    for cand in candidates:
                        dkey = _date_prefix(cand).lower()
                        if dkey and dkey in seen_dates:
                            continue
                        if dkey:
                            seen_dates.add(dkey)
                        out.append(cand)
                        if len(seen_dates) >= max_per_year:
                            break
                return out

            def _dynamic_max_per_year(values: list[str]) -> int:
                years = {
                    int(m.group(1))
                    for text in values
                    if (m := re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", str(text or "")))
                }
                year_count = max(1, len(years))
                # Distribute across years, but allow more per year when there are few distinct years.
                per_year = max(2, (max_items + year_count - 1) // year_count)
                return min(6, per_year)

            def _collect(require_topic: bool, *, require_action: bool) -> list[str]:
                out: list[str] = []
                seen: set[str] = set()
                # Scan a larger pool so early low-signal candidates don't crowd out good late ones.
                for text in _filter_events(items, max_items=max_items * 80):
                    if not re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text):
                        continue
                    normalized = _ensure_date_prefix(text)
                    if not normalized:
                        continue
                    if not _has_event_keyword(normalized) and not _has_action_verb(normalized):
                        continue
                    if require_action and not _has_action_verb(normalized):
                        continue
                    if require_topic and topic_keys:
                        lowered = _norm_for_filter(normalized)
                        if not any(k in lowered for k in topic_keys):
                            continue
                    key = _norm_for_filter(normalized)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(normalized)
                    if len(out) >= max_items:
                        break
                return out

            strict = _collect(require_topic=True, require_action=True)
            if not topic_keys:
                strict.sort(key=lambda t: (_timeline_sort_key(t), _norm_for_filter(t)))
                return _cap_by_year(strict, max_per_year=_dynamic_max_per_year(strict))[:max_items]
            relaxed = _collect(require_topic=False, require_action=False)
            strict.sort(key=lambda t: (_timeline_sort_key(t), _norm_for_filter(t)))
            strict_capped = _cap_by_year(strict, max_per_year=_dynamic_max_per_year(strict))[:max_items]
            # If strict output is already sufficiently populated after capping, keep it; otherwise merge
            # in relaxed items so events without explicit topic tokens (e.g. battles) can appear.
            if len(strict_capped) >= min(max_items, 10):
                return strict_capped
            # Merge strict + relaxed, keeping strict first, to avoid missing relevant events like armistices.
            seen: set[str] = set()
            merged: list[str] = []
            for item in strict + relaxed:
                key = _norm_for_filter(item)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                # Collect extra candidates so the year-cap doesn't shrink the final output too much.
                if len(merged) >= max_items * 4:
                    break
            merged.sort(key=lambda t: (_timeline_sort_key(t), _norm_for_filter(t)))
            capped = _cap_by_year(merged, max_per_year=_dynamic_max_per_year(merged))
            return capped[:max_items]

        def _filter_background(items: list[str], *, max_items: int) -> list[str]:
            out: list[str] = []
            for item in items:
                text = str(item or "").strip()
                if not text:
                    continue
                if _is_publication_line(text) or _is_placeholder_timeline(text):
                    continue
                plain = re.sub(r"\[\d+\]", "", text).strip()
                if len(plain) < 10:
                    continue
                out.append(text)
                if len(out) >= max_items:
                    break
            return out

        def _is_generic_person(item: str) -> bool:
            lowered = _norm_for_filter(item)
            # Filter common "not-a-person" placeholders.
            if lowered.startswith("the ") and re.search(
                r"\b(people|government|administration|military|army|navy|congress|parliament|state|empire)\b",
                lowered,
            ):
                return True
            generic_phrases = [
                "the people",
                "people of",
                "the government",
                "government",
                "administration",
                "colonial administration",
                "military governor",
                "the military",
                "armed forces",
                "u s government",
                "us government",
                "u s military",
                "us military",
            ]
            # Only treat as "generic" when the whole entry is generic (or clearly starts with a determiner),
            # so role phrases like "John R. Brooke — military governor" are not filtered out.
            if lowered in generic_phrases:
                return True
            if lowered.startswith(("the ", "a ", "an ")):
                return any(phrase in lowered for phrase in generic_phrases)
            return False

        def _is_name_like(item: str) -> bool:
            text = re.sub(r"\[\d+\]", "", str(item or "")).strip()
            if not text:
                return False
            if text.lower().startswith("the "):
                return False
            head = re.split(r"\s*[-–—:]\s*", text, 1)[0].strip()
            if not head:
                return False
            token = r"[^\W\d_](?:[^\W\d_]|[.''\-]){0,23}"
            if not re.match(rf"^(?:{token}\s+)?{token}(?:\s+{token}){{1,4}}$", head):
                return False

            # Require proper-name capitalization for non-connector tokens so we don't accept prose fragments like
            # "officially transferring Puerto Rico".
            connectors = {
                "a",
                "an",
                "and",
                "as",
                "at",
                "bin",
                "da",
                "das",
                "de",
                "del",
                "della",
                "di",
                "do",
                "dos",
                "du",
                "el",
                "ibn",
                "la",
                "le",
                "los",
                "of",
                "or",
                "st",
                "st.",
                "van",
                "von",
                "y",
            }
            words = [w for w in re.split(r"\s+", head) if w]
            if len(words) < 2:
                return False
            if len(words) == 2 and re.fullmatch(r"[A-Z]\.?", words[1].strip()):
                return False
            # If the entry starts with a title, require a fuller name (avoid "General Bernardo").
            title_words = {
                "general",
                "captain",
                "admiral",
                "colonel",
                "col",
                "major",
                "brigadier",
                "lieutenant",
                "lt",
                "sergeant",
                "sgt",
                "dr",
            }
            if words and words[0].rstrip(".").lower() in title_words and len(words) < 3:
                return False
            if not any(ch.isupper() for ch in head):
                return False
            first_word = re.sub(r"[^\w'.-]", "", words[0]).rstrip(".").lower()
            if first_word in {"the", "a", "an", "and", "or"}:
                return False
            for word in words:
                w = re.sub(r"^[\"'“”‘’\\(\\)\\[\\]\\{\\}]+|[\"'“”‘’\\(\\)\\[\\]\\{\\}]+$", "", word)
                w = w.strip(",;:")
                if not w:
                    continue
                low = w.rstrip(".").lower()
                if low in connectors:
                    continue
                if re.fullmatch(r"[A-Z]\.", w):
                    continue
                if w.isupper():
                    continue
                if not w[0].isupper():
                    return False
            return True

        def _is_non_person_entity_name(value: str) -> bool:
            raw = str(value or "").strip()
            # Possessives like "Puerto Rico's" or "Spain's" are almost never person names in our lists.
            if re.search(r"['']s\b", raw):
                return True
            head = re.split(
                r"\s*(?:---|--|—|–|:|\s-\s)\s*",
                re.sub(r"\[\s*\d+\s*\]", "", raw).strip(),
                1,
            )[0].strip().lower()
            head = re.sub(r"[^a-z0-9\s]", "", head)
            head = re.sub(r"\s+", " ", head).strip()
            if not head:
                return True
            # Organizations / concepts often have "of" (e.g. "Treaty of Paris", "Report of ...") which is
            # almost never a person's name in this app's Key People lists.
            if " of " in f" {head} ":
                return True

            tokens = head.split()
            # Spanish articles ("El Morro", "La Fortaleza") are overwhelmingly place/thing labels.
            if tokens and tokens[0] in {"el", "la", "los", "las"} and len(tokens) <= 3:
                return True
            # Heads that contain both "puerto" and "rico" are overwhelmingly location/organization labels.
            if "puerto" in tokens and "rico" in tokens:
                return True
            # Reject common prepositions/determiners that indicate this is a prose fragment, not a name.
            if tokens and tokens[0] in {
                "on",
                "in",
                "at",
                "from",
                "by",
                "for",
                "to",
                "as",
                "with",
                "without",
                "after",
                "before",
                "during",
            }:
                return True
            # Common scraped UI fragments / metadata that can masquerade as "names".
            if any(
                tok in {"contents", "table", "editor", "editors", "updated", "last", "chatbot", "britannica", "ask", "anything"}
                for tok in tokens
            ):
                return True
            # "Porto/Puerto ..." are overwhelmingly location phrases in sources, not person names.
            if tokens and tokens[0] in {"porto", "puerto"}:
                return True
            # Filter common non-person labels that can be mistakenly extracted as a "name".
            non_person_heads = {
                "treaty",
                "act",
                "war",
                "campaign",
                "report",
                "manual",
                "civics",
                "revolution",
                "regiment",
                "infantry",
                "search",
                "results",
                "view",
                "item",
                "title",
                "names",
                "catalog",
                "collection",
                "collections",
                "manifest",
                "presentation",
                "iiif",
                "online",
                "board",
                "committee",
                "congress",
                "parliament",
                "government",
                "administration",
                "department",
                "ministry",
                "office",
                "army",
                "navy",
                "forces",
                "uss",
                "u.s.s",
                "hms",
                "ship",
                "battleship",
                "cruiser",
                "destroyer",
                "infantry",
                "regiment",
                "school",
                "university",
                "people",
                "population",
                "economy",
                "education",
                "health",
                "infrastructure",
                "civil",
                "affairs",
                "conditions",
                "resources",
                "work",
                "book",
            }
            if tokens and (tokens[0] in non_person_heads or tokens[-1] in non_person_heads):
                return True

            # Lightweight place-name heuristics to avoid treating geography as a person.
            # Keep generic; do not hardcode topic-specific entities.
            # Common location starters; keep generic (do not hardcode topic entities).
            place_prefixes = {"san", "saint", "st", "new", "fort", "mt", "mount", "lake", "porto", "puerto"}
            geo_features = {
                "hill",
                "bay",
                "harbor",
                "port",
                "river",
                "mountain",
                "valley",
                "gulf",
                "sea",
                "ocean",
                "cape",
                "peninsula",
                "strait",
            }
            place_suffixes = {
                "states",
                "kingdom",
                "republic",
                "empire",
                "island",
                "islands",
                "city",
                "province",
                "territory",
                "commonwealth",
            }
            if len(tokens) == 2 and (tokens[0] in place_prefixes or tokens[1] in place_suffixes):
                return True
            # Multi-token "Fort X ..." is overwhelmingly a place/structure, not a person.
            if tokens and tokens[0] in {"fort", "mt", "mount", "lake"} and len(tokens) >= 2:
                return True
            # Names starting with "San/Santa/Santo" are overwhelmingly places/saints in sources, not people.
            if tokens and tokens[0] in {"san", "santa", "santo"} and len(tokens) >= 2:
                return True
            # Geography like "Caribbean Sea" should never be a person.
            if tokens and tokens[-1] in geo_features:
                return True
            if len(tokens) >= 3 and tokens[0] in place_prefixes and tokens[-1] in geo_features:
                return True

            group_terms = {
                "people",
                "citizens",
                "residents",
                "population",
                "community",
                "communities",
                "locals",
                "inhabitants",
            }
            if any(t in group_terms for t in tokens):
                return True

            # Filter demonyms / group labels (e.g., "X Americans", "Y Ricans") without hardcoding topics.
            if len(tokens) <= 3 and tokens and tokens[-1].endswith(("ans", "ians", "ese", "ites", "ish", "ican")):
                return True

            keywords = (
                "treaty",
                "act",
                "law",
                "constitution",
                "war",
                "battle",
                "campaign",
                "revolution",
                "report",
                "manifest",
                "iiif",
                "catalog",
                "collection",
                "collections",
                "board",
                "affairs",
                "policy",
                "program",
                "manual",
                "guide",
                "committee",
                "congress",
                "senate",
                "parliament",
                "government",
                "administration",
                "department",
                "ministry",
                "commission",
                "court",
                "army",
                "navy",
                "infantry",
                "regiment",
                "church",
                "university",
                "school",
                "schools",
                "bay",
                "island",
                "city",
                "province",
                "territory",
                "commonwealth",
                "company",
                "corporation",
            )
            if any(k in head for k in keywords):
                return True

            # === CRITICAL FILTERS FOR GARBAGE EXTRACTION ===

            # Filter time periods (Mesozoic Era, Triassic Period, Bronze Age, etc.)
            time_period_words = {
                "era",
                "eon",
                "period",
                "age",
                "epoch",
                "dynasty",
                "century",
                "millennium",
                "paleozoic",
                "mesozoic",
                "cenozoic",
                "triassic",
                "jurassic",
                "cretaceous",
                "paleocene",
                "eocene",
                "oligocene",
                "miocene",
                "pliocene",
                "pleistocene",
                "holocene",
                "bronze",
                "iron",
                "stone",
                "medieval",
                "renaissance",
                "enlightenment",
                "victorian",
                "edwardian",
                "colonial",
                "antebellum",
                "reconstruction",
                "industrial",
                "atomic",
                "space",
                "information",
            }
            if any(t in tokens for t in time_period_words):
                return True

            # Filter navigation/UI garbage (from scraped websites)
            navigation_garbage = {
                "where",
                "what",
                "when",
                "how",
                "why",
                "who",
                "which",
                "see",
                "more",
                "about",
                "click",
                "here",
                "read",
                "view",
                "show",
                "hide",
                "expand",
                "collapse",
                "menu",
                "navigation",
                "nav",
                "search",
                "find",
                "browse",
                "home",
                "page",
                "site",
                "web",
                "website",
                "link",
                "links",
                "related",
                "articles",
                "posts",
                "categories",
                "tags",
                "archive",
                "archives",
                "subscribe",
                "follow",
                "share",
                "like",
                "comment",
                "comments",
                "reply",
                "contact",
                "privacy",
                "terms",
                "copyright",
                "login",
                "logout",
                "signup",
                "register",
                "account",
                "profile",
                "settings",
                "help",
                "faq",
                "support",
                "download",
                "upload",
                "submit",
                "send",
                "back",
                "next",
                "previous",
                "continue",
                "skip",
                "close",
                "cancel",
                "ok",
                "yes",
                "no",
            }
            # Check if ANY token is navigation garbage
            if any(t in navigation_garbage for t in tokens):
                return True

            # Filter common scraped metadata phrases
            if len(tokens) >= 2:
                # "Last Updated", "See More", "Read More", "Learn More", etc.
                two_word_garbage = {
                    ("last", "updated"),
                    ("see", "more"),
                    ("read", "more"),
                    ("learn", "more"),
                    ("find", "out"),
                    ("click", "here"),
                    ("show", "all"),
                    ("view", "all"),
                    ("back", "top"),
                    ("top", "page"),
                    ("related", "articles"),
                    ("related", "content"),
                    ("more", "information"),
                    ("additional", "resources"),
                    ("external", "links"),
                }
                if (tokens[0], tokens[1]) in two_word_garbage:
                    return True

            # Filter if it looks like a phrase fragment (lowercase start, or ends with lowercase)
            if tokens:
                # If first word is ALL lowercase (and not a connector like "de", "von"), likely not a name
                first_word_clean = tokens[0].strip(".,;:!?")
                if first_word_clean and first_word_clean.islower() and first_word_clean not in {"de", "von", "van", "del", "della", "di", "da", "la", "le", "el"}:
                    return True

            return False

        def _filter_people(items: list[str], *, max_items: int) -> list[str]:
            topic_phrases = _topic_phrases_for_filter(request)
            subject_phrases = _subject_phrases_from_request(request)
            month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            # Reject sentence fragments that leak through name extraction (e.g. "X. However", "Y. After").
            trailing_sentence_word = re.compile(
                r"\.\s*(?:After|However|But|And|Or|So|Then|When|While|Because|Since|Therefore|Thus|Meanwhile|Additionally|Moreover|In|On|At|By|For|To|From|With|Without|The|A|An|This|That|These|Those|His|Her|Their)\b",
                flags=re.IGNORECASE,
            )

            def _dedupe_citations_in_person_line(text: str) -> str:
                ids = re.findall(r"\[(\d+)\]", text)
                if not ids:
                    return text
                seen: set[str] = set()
                ordered: list[str] = []
                for cid in ids:
                    if cid in seen:
                        continue
                    seen.add(cid)
                    ordered.append(cid)
                base = re.sub(r"\s*\[\d+\]\s*", " ", text).strip()
                base = re.sub(r"\s{2,}", " ", base).rstrip(" .")
                return f"{base} {' '.join(f'[{cid}]' for cid in ordered)}".strip()

            out: list[str] = []
            seen_name_keys: set[str] = set()
            norm_topic_phrases = {re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", p)).strip() for p in topic_phrases}
            norm_subject_phrases = {
                re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", p)).strip() for p in subject_phrases
            }
            for item in items:
                text = str(item or "").strip()
                if not text:
                    continue
                text = _dedupe_citations_in_person_line(text)
                lowered = _norm_for_filter(text)
                if re.search(r"\[\s*uncertain\s*\]", text, flags=re.IGNORECASE):
                    continue
                # Keep Key People grounded in sources.
                if not re.search(r"\[\d+\]", text):
                    continue
                if _is_generic_person(text):
                    continue
                no_cit = re.sub(r"\[\d+\]", "", text).strip()
                # Validate "person-ness" against the NAME only (role/description often follows after a dash).
                name_part = re.split(r"\s*[-–—:]\s*", no_cit, maxsplit=1)[0].strip()
                # Strip possessive tails from prose-like items (e.g. "X's book describes ...").
                name_part = re.sub(r"(?:'s|'s)\b.*$", "", name_part).strip()
                # Strip trailing sentence fragments (e.g. "Juan Sánchez. After") if they leaked in.
                if trailing_sentence_word.search(name_part):
                    name_part = re.split(r"\.", name_part, maxsplit=1)[0].strip()
                if not name_part:
                    continue
                # Names should be short; if this is long prose, let the name-extractor handle it later.
                if len(name_part.split()) > 6:
                    continue
                first_tok = (name_part.split()[0] if name_part.split() else "").rstrip(".")
                if first_tok and re.fullmatch(month_re, first_tok, flags=re.IGNORECASE):
                    continue
                if re.search(r"(?:^|\W)(?:U\.?S\.?|UK|EU)(?:\W|$)", name_part, flags=re.IGNORECASE):
                    continue
                if re.search(r"\bthe\b", name_part, flags=re.IGNORECASE):
                    # "The" can leak in at the end (e.g. "Ponce The") even though we reject starters above.
                    continue
                if not _is_name_like(name_part):
                    continue
                # Prevent event/timeline sentences from appearing in Key People.
                if re.match(
                    rf"^\s*(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}})\s*[-–—:]",
                    text,
                ):
                    continue
                if _is_non_person_entity_name(name_part):
                    continue
                citation_ids = [int(x) for x in re.findall(r"\[(\d+)\]", text)]
                if not _name_supported_by_sources(name_part, citation_ids):
                    continue
                name_key = re.sub(r"[^a-z0-9]+", " ", name_part.lower()).strip()
                if name_key and name_key in seen_name_keys:
                    continue
                if name_key:
                    seen_name_keys.add(name_key)
                head = name_part.strip().lower()
                head = re.sub(r"[^a-z0-9\s]", "", head)
                head = re.sub(r"\s+", " ", head).strip()
                if norm_topic_phrases:
                    if head in norm_topic_phrases:
                        continue
                if norm_subject_phrases:
                    if head in norm_subject_phrases:
                        continue
                out.append(text)
                if len(out) >= max_items:
                    break
            return out

        def _split_interpretation(text: str) -> tuple[str | None, str | None]:
            lowered = text.lower()
            for splitter in ("while others", "whereas", "but others", "however"):
                if splitter in lowered:
                    parts = re.split(splitter, text, maxsplit=1, flags=re.IGNORECASE)
                    if len(parts) == 2:
                        return parts[0].strip(), parts[1].strip()
            for splitter in (" vs ", " versus "):
                if splitter in lowered:
                    parts = re.split(splitter, text, maxsplit=1, flags=re.IGNORECASE)
                    if len(parts) == 2:
                        return parts[0].strip(), parts[1].strip()
            return None, None

        def _render_section(title: str, lines: list[str]) -> str:
            clean_lines = [line for line in lines if line]
            if not clean_lines:
                return ""

            def _format_timeline_line(text: str) -> str:
                month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
                line = str(text or "").strip()
                if not line:
                    return line
                match = re.match(
                    rf"^\s*(?P<date>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[:\-–—]\s*(?P<rest>.+)$",
                    line,
                )
                if match:
                    date = match.group("date").strip()
                    rest = match.group("rest").strip()
                    rest_match = re.match(
                        rf"^\s*(?P<date>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[:\-–—]\s*(?P<rest>.+)$",
                        rest,
                    )
                    if rest_match:
                        d2 = rest_match.group("date").strip()
                        rest2 = rest_match.group("rest").strip()
                        if d2 and d2 != date:
                            return f"**{date} – {d2}:** {rest2}"
                        return f"**{d2}:** {rest2}"
                    return f"**{date}:** {rest}"
                return line

            def _format_person_line(text: str) -> str:
                line = str(text or "").strip()
                if not line:
                    return line
                citations = re.findall(r"\[\d+\]", line)
                citation = citations[-1] if citations else ""
                no_cit = re.sub(r"\s*\[\d+\]\s*$", "", line).strip()
                parts = re.split(r"\s*(?:—|–|:|-)\s*", no_cit, maxsplit=1)
                name = parts[0].strip()
                role = parts[1].strip() if len(parts) > 1 else ""
                if role:
                    return f"**{name}** — {role} {citation}".strip()
                return f"**{name}** {citation}".strip()

            formatted_lines = clean_lines
            if title.strip().lower().startswith("timeline"):
                formatted_lines = [_format_timeline_line(line) for line in clean_lines]
            elif title.strip().lower().startswith("key people"):
                formatted_lines = [_format_person_line(line) for line in clean_lines]
            body = "\n".join(f"- {line}" for line in formatted_lines)
            return f"## {title}\n{body}".strip()

        def _replace_section(doc: str, titles: list[str], new_section: str) -> str:
            if not new_section:
                return doc
            title_pattern = "|".join(re.escape(t) for t in titles)

            def _section_spans(text: str) -> list[tuple[int, int]]:
                header_re = re.compile(
                    rf"(?m)^(?P<h>#+)\s+(?P<title>{title_pattern})\b[^\n]*\n?",
                    re.IGNORECASE,
                )
                spans: list[tuple[int, int]] = []
                for m in header_re.finditer(text):
                    level = len(m.group("h") or "#")
                    # Stop at the next heading of the same or higher level; keep nested headings inside the section.
                    next_re = re.compile(rf"(?m)^#{{1,{level}}}\s+\S")
                    nxt = next_re.search(text, m.end())
                    end = nxt.start() if nxt else len(text)
                    spans.append((m.start(), end))
                return spans

            spans = _section_spans(doc)
            matches = spans
            if not matches:
                # Insert missing sections in a sensible place to preserve the expected outline.
                section_title = ""
                first_line = new_section.splitlines()[0].strip() if new_section else ""
                title_match = re.match(r"^\s*#+\s+(.+?)\s*$", first_line)
                if title_match:
                    section_title = title_match.group(1).strip().lower()

                insertion_candidates: list[str] = []
                if section_title.startswith("key people"):
                    insertion_candidates = [
                        "Key Events",
                        "Consequences & Legacy",
                        "Consequences",
                        "Different Historical Interpretations",
                        "Limitations and Further Research",
                        "Discussion Questions",
                        "Sources",
                    ]
                elif section_title.startswith("key events"):
                    insertion_candidates = [
                        "Consequences & Legacy",
                        "Consequences",
                        "Different Historical Interpretations",
                        "Limitations and Further Research",
                        "Discussion Questions",
                        "Sources",
                    ]
                elif section_title.startswith("timeline"):
                    insertion_candidates = [
                        "Key People",
                        "Key Events",
                        "Consequences & Legacy",
                        "Consequences",
                        "Sources",
                    ]
                elif section_title.startswith("key turning points"):
                    insertion_candidates = ["Timeline", "Key People", "Key Events", "Consequences & Legacy", "Sources"]

                for candidate in insertion_candidates:
                    m = re.search(rf"(?mi)^\s*#+\s+{re.escape(candidate)}\b", doc)
                    if m:
                        before = doc[: m.start()].rstrip()
                        after = doc[m.start() :].lstrip()
                        return (before + "\n\n" + new_section.strip() + "\n\n" + after).strip()
                return doc.rstrip() + "\n\n" + new_section
            pieces: list[str] = []
            last_end = 0
            for idx, (start, end) in enumerate(matches):
                pieces.append(doc[last_end:start])
                if idx == 0:
                    pieces.append(new_section)
                last_end = end
            pieces.append(doc[last_end:])
            return "".join(pieces).strip()

        def _dedupe_sections(doc: str, titles: list[str]) -> str:
            if not doc:
                return doc
            for title in titles:
                title_pattern = re.escape(title)
                header_re = re.compile(
                    rf"(?m)^(?P<h>#+)\s+(?P<title>{title_pattern})\b[^\n]*\n?",
                    re.IGNORECASE,
                )
                spans: list[tuple[int, int]] = []
                for m in header_re.finditer(doc):
                    level = len(m.group("h") or "#")
                    next_re = re.compile(rf"(?m)^#{{1,{level}}}\s+\S")
                    nxt = next_re.search(doc, m.end())
                    end = nxt.start() if nxt else len(doc)
                    spans.append((m.start(), end))
                if len(spans) <= 1:
                    continue
                kept = False
                pieces: list[str] = []
                last_end = 0
                for start, end in spans:
                    if not kept:
                        pieces.append(doc[last_end:end])
                        kept = True
                    else:
                        pieces.append(doc[last_end:start])
                    last_end = end
                pieces.append(doc[last_end:])
                doc = "".join(pieces)
            return doc

        def _format_interpretations(items: list[Any]) -> str:
            if not items:
                return ""
            blocks: list[str] = []

            def _labels_for_pair(left: str, right: str) -> tuple[str, str]:
                a_low = str(left or "").lower()
                if any(word in a_low for word in ["traditional", "mainstream", "official", "u.s.", "us ", "american", "government view"]):
                    return "Traditional/Mainstream View", "Critical/Alternative View"
                if any(word in a_low for word in ["development", "progress", "moderniz", "benefit", "stabiliz"]):
                    return "Development Argument", "Exploitation/Control Argument"
                return "Perspective A", "Perspective B"

            def _ensure_sentence(text: str) -> str:
                s = str(text or "").strip()
                if not s:
                    return ""
                s = re.sub(r"\s+", " ", s).strip()
                if not s.endswith((".", "!", "?")) and not re.search(r"\[\d+\]\s*$", s):
                    s = f"{s}."
                return s

            def _extract_citations(text: str) -> str:
                cites = re.findall(r"\[\d+\]", str(text or ""))
                if not cites:
                    return ""
                # Keep unique in first-seen order.
                seen_ids: set[str] = set()
                out: list[str] = []
                for c in cites:
                    if c in seen_ids:
                        continue
                    seen_ids.add(c)
                    out.append(c)
                return " ".join(out)

            def _require_cited(text: str, fallback_cites: str) -> str:
                s = str(text or "").strip()
                if not s:
                    return ""
                cites = _extract_citations(s) or fallback_cites
                s = re.sub(r"\s*\[\d+\]\s*", " ", s).strip()
                s = _ensure_sentence(s)
                if cites:
                    return f"{s} {cites}".strip()
                # No citations: skip to avoid hallucination.
                return ""

            # Prefer structured debates when provided by the research agent.
            structured: list[dict[str, Any]] = []
            if isinstance(items, list):
                for x in items:
                    if isinstance(x, dict):
                        structured.append(x)
                        continue
                    # Support pydantic models (e.g., InterpretationDebateModel) without importing pydantic here.
                    if hasattr(x, "model_dump"):
                        try:
                            dumped = x.model_dump()
                            if isinstance(dumped, dict):
                                structured.append(dumped)
                        except Exception:
                            pass
            if structured:
                for idx, entry in enumerate(structured[:3], start=1):
                    question = str(entry.get("question") or entry.get("prompt") or entry.get("topic") or "").strip()
                    traditional = str(entry.get("traditional_view") or entry.get("view_a") or entry.get("position_a") or "").strip()
                    alternative = str(entry.get("alternative_view") or entry.get("view_b") or entry.get("position_b") or "").strip()
                    if not (traditional or alternative):
                        continue
                    # If the entry includes citations separately, apply them; otherwise reuse any citations already in text.
                    entry_cites = _extract_citations(entry.get("citations") or entry.get("citation") or "")
                    if not entry_cites:
                        entry_cites = _extract_citations(traditional) or _extract_citations(alternative)
                    title = f"### Debate {idx}"
                    if question:
                        title = f"{title}: {question}"
                    label_a, label_b = _labels_for_pair(traditional, alternative)
                    chunk = [title]
                    rendered_a = _require_cited(traditional, entry_cites)
                    rendered_b = _require_cited(alternative, entry_cites)
                    if rendered_a:
                        chunk.append(f"**{label_a}:** {rendered_a}")
                    if rendered_b:
                        chunk.append(f"**{label_b}:** {rendered_b}")
                    if len(chunk) <= 1:
                        continue
                    blocks.append("\n\n".join(chunk))
                if blocks:
                    return "## Different Historical Interpretations\n" + "\n\n".join(blocks)

            # Fallback: split legacy single-line items into two perspectives.
            # Use _extract_text_from_item to handle both strings and dicts
            raw_items = _coerce_any_list(items)
            for idx, raw_item in enumerate(raw_items[:3], start=1):
                # Convert dict to text if needed
                line = _extract_text_from_item(raw_item) if isinstance(raw_item, dict) else str(raw_item).strip()
                if not line:
                    continue

                a, b = _split_interpretation(line)
                if a and b:
                    # Reuse citations from the source line for both perspectives.
                    cites = _extract_citations(line)
                    a = _require_cited(a, cites)
                    b = _require_cited(b, cites)
                    if not (a or b):
                        continue
                    label_a, label_b = _labels_for_pair(a, b)
                    blocks.append(
                        f"### Debate {idx}\n"
                        f"**{label_a}:** {a}\n\n"
                        f"**{label_b}:** {b}"
                    )
                else:
                    cites = _extract_citations(line)
                    rendered = _require_cited(line, cites)
                    if rendered:
                        blocks.append(f"### Interpretation {idx}\n{rendered}")
            return "## Different Historical Interpretations\n" + "\n\n".join(blocks) if blocks else ""

        def _format_limitations(items: list[Any]) -> str:
            lines = _coerce_list(items)
            if len(lines) < 4:
                lines.extend(
                    [
                        "Limited first-person accounts and oral histories in available sources.",
                        "Few perspectives from marginalized groups are documented in the collected materials.",
                        "Sources focus on governance and policy more than daily life and cultural impact.",
                        "More local newspaper archives and community records would strengthen the analysis.",
                    ]
                )
            source_limitations = lines[:4]
            gaps = lines[4:8] if len(lines) > 4 else []
            further = lines[8:12] if len(lines) > 8 else []
            section = ["## Limitations and Further Research"]
            section.append("### Source Limitations")
            section.append("\n".join(f"- {x}" for x in source_limitations))
            if gaps:
                section.append("\n### Historical Gaps")
                section.append("\n".join(f"- {x}" for x in gaps))
            if further:
                section.append("\n### Further Research Needed")
                section.append("\n".join(f"- {x}" for x in further))
            return "\n".join(section).strip()

        def _format_discussion_questions(items: list[Any]) -> str:
            lines = _coerce_list(items)
            # Remove hardcoded Puerto Rico questions - these should come from LLM based on the topic
            return _render_section("Discussion Questions", lines[:14])

        def _format_consequences(items: list[Any]) -> str:
            lines = _coerce_list(items)
            if not lines:
                return ""
            buckets = {
                "Economic": [],
                "Political": [],
                "Social & Cultural": [],
                "Contemporary Legacy": [],
            }
            for line in lines:
                lowered = line.lower()
                if any(k in lowered for k in ("econom", "sugar", "industry", "trade", "shipping", "tax", "corporation")):
                    buckets["Economic"].append(line)
                elif any(k in lowered for k in ("govern", "law", "constitution", "citizen", "status", "congress")):
                    buckets["Political"].append(line)
                elif any(k in lowered for k in ("school", "education", "language", "culture", "identity", "migration")):
                    buckets["Social & Cultural"].append(line)
                else:
                    buckets["Contemporary Legacy"].append(line)
            section = ["## Consequences & Legacy"]
            section.append("These were some major consequences and long-term impacts discussed in the sources:")
            for key, vals in buckets.items():
                if not vals:
                    continue
                section.append(f"### {key}")
                section.append("\n".join(f"- {v}" for v in vals))
            return "\n".join(section).strip()

        def _format_turning_points(items: list[Any], fallback: list[Any]) -> str:
            lines = _coerce_list(items)
            if not lines:
                lines = _coerce_list(fallback)
            lines = _filter_events(lines, max_items=8)
            return _render_section("Key Turning Points", lines)

        def _is_placeholder_line(text: str) -> bool:
            lowered = str(text or "").lower()
            placeholders = (
                "begins to consider",
                "began to consider",
                "starts to consider",
                "establishes a new",
                "establishes new",
                "published",
                "publication",
                "study",
                "book",
                "work discussed",
                "first major historical study",
                "library of congress",
                "special holiday hours",
                "top of page",
                "photoduplication service",
                "preservation microfilming",
                "available from",
                "catalog",
                "notice",
            )
            return any(p in lowered for p in placeholders)

        def _extract_dated(items: list[Any]) -> list[str]:
            lines = _coerce_list(items)
            dated: list[str] = []
            for line in lines:
                if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", line):
                    dated.append(line)
            return dated

        def _extract_dated_from_text(blocks: list[str]) -> list[str]:
            dated: list[str] = []
            for block in blocks:
                for sentence in re.split(r"(?<=[.!?])\s+", str(block or "")):
                    s = sentence.strip()
                    if not s:
                        continue
                    if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", s):
                        dated.append(s)
            return dated

        def _extract_background_sentences(blocks: list[str]) -> list[str]:
            out: list[str] = []
            for block in blocks:
                for sentence in re.split(r"(?<=[.!?])\s+", str(block or "")):
                    s = sentence.strip()
                    if not s:
                        continue
                    if len(s) < 30:
                        continue
                    if _is_publication_line(s) or _is_placeholder_timeline(s):
                        continue
                    out.append(s)
                    if len(out) >= 18:
                        return out
            return out

        def _derive_title(text: str) -> str:
            cleaned = re.sub(
                r"(?i)^(create|write|build|make)( a| an)? (history|historical)? (project|report|essay)( on| about| of)?",
                "",
                text.strip(),
            ).strip()
            if not cleaned:
                return "History Project"
            return cleaned[:160]

        def _build_sources_block(items: list[str]) -> str:
            lines = [line for line in items if line]
            if not lines:
                return ""
            body = "\n".join(f"- {line}" for line in lines)
            return f"## Sources\n{body}".strip()

        def _build_structured_document() -> str:
            # NOTE: This function builds adult/teen format only
            # Kid format is handled via LLM prompts (see lines 2881-2914)
            title = _derive_title(request)
            task = (
                f"To analyze {title} and its historical context, causes, and consequences."
                if title
                else "To analyze the historical topic and its context, causes, and consequences."
            )
            intro = summary.strip() or "This project summarizes the historical topic using verified sources."
            background_lines = _filter_background(_coerce_list(context_points) + _coerce_list(causes), max_items=10)
            if len(background_lines) < 4:
                background_lines = _filter_background(
                    _extract_background_sentences(
                        [summary]
                        + _coerce_list(context_points)
                        + _coerce_list(causes)
                        + _coerce_list(facts)
                        + _coerce_list(source_notes)
                    ),
                    max_items=10,
                )
            background_section = _render_section("Historical Background (Context + Causes)", background_lines)

            # Timeline often arrives as a list of dicts (date/event/citation). Coerce it through
            # the event formatter so filtering and date styling behave consistently.
            timeline_candidates: list[str] = []
            timeline_candidates.extend(_coerce_events(timeline))
            timeline_candidates.extend(_coerce_events(key_events))
            timeline_candidates.extend(_extract_dated(key_events))
            # Only fall back to pulling dated sentences from narrative text if the explicit timeline is too short.
            if len(timeline_candidates) < 8:
                timeline_candidates.extend(_extract_dated(source_notes))
                timeline_candidates.extend(_extract_dated(facts))
                timeline_candidates.extend(_extract_dated_from_text([summary] + _coerce_list(context_points)))
                timeline_candidates.extend(
                    _extract_dated_from_text(
                        [summary]
                        + _coerce_list(context_points)
                        + _coerce_list(causes)
                        + _coerce_list(consequences)
                        + _coerce_list(facts)
                        + _coerce_list(source_notes)
                    )
                )
            timeline_items = _filter_timeline(timeline_candidates, max_items=14)

            key_events_items = _filter_events(_coerce_events(key_events), max_items=12) or timeline_items
            if not key_events_items:
                key_events_items = _filter_events(_coerce_list(facts), max_items=12) or timeline_items
            if not key_events_items:
                key_events_items = _filter_events(
                    _extract_dated_from_text(
                        [summary]
                        + _coerce_list(context_points)
                        + _coerce_list(causes)
                        + _coerce_list(consequences)
                        + _coerce_list(facts)
                        + _coerce_list(source_notes)
                    ),
                    max_items=12,
                )
            key_people_items = _filter_people(_coerce_people(key_figures), max_items=14)
            # Drop hallucinated "people" that don't actually appear in the cited sources.
            if source_text_norm_by_id and key_people_items:
                kept: list[str] = []
                for item in key_people_items:
                    cit_ids = [int(x) for x in re.findall(r"\[(\d+)\]", item)]
                    name_part = re.split(r"\s*(?:—|–|-|:)\s*", re.sub(r"\[\d+\]", "", item).strip(), 1)[0].strip()
                    name_part = re.sub(r"(?:'s|'s)\b.*$", "", name_part).strip()
                    if _name_supported_by_sources(name_part, cit_ids):
                        kept.append(item)
                key_people_items = kept
            if source_notes or facts or timeline_items:
                pool = " ".join(
                    [summary]
                    + _coerce_list(context_points)
                    + _coerce_list(causes)
                    + _coerce_list(consequences)
                    + _coerce_list(source_notes)
                    + _coerce_list(facts)
                    + key_events_items
                    + timeline_items
                )
                seen = {_norm_for_filter(p) for p in key_people_items}
                topic_phrases = _topic_phrases_for_filter(request)
                subject_phrases = _subject_phrases_from_request(request)
                title_map = {
                    "president": "President",
                    "general": "General",
                    "governor": "Governor",
                    "senator": "Senator",
                    "secretary": "Secretary",
                    "minister": "Minister",
                    "prime": "Prime Minister",
                    "dr": "Dr.",
                    "doctor": "Dr.",
                    "prof": "Professor",
                    "professor": "Professor",
                    "king": "King",
                    "queen": "Queen",
                    "sir": "Sir",
                }

                def _split_title(name: str) -> tuple[str, str]:
                    parts = [p for p in re.split(r"\s+", name.strip()) if p]
                    if len(parts) < 2:
                        return name.strip(), ""
                    raw0 = parts[0].rstrip(".").lower()
                    if raw0 in title_map:
                        return " ".join(parts[1:]).strip(), title_map[raw0]
                    if len(parts) >= 2 and raw0 == "prime" and parts[1].lower().startswith("minister"):
                        return " ".join(parts[2:]).strip(), "Prime Minister"
                    return name.strip(), ""

                def _looks_like_person_strict(name: str) -> bool:
                    head = re.sub(r"[^\w\s.''\\-]", "", str(name or "")).strip()
                    if not head:
                        return False
                    # Avoid sentence fragments that come from naive regex name extraction.
                    if re.search(
                        r"\.\s*(?:After|However|But|And|Or|So|Then|When|While|Because|Since|Therefore|Thus|Meanwhile|Additionally|Moreover)\b",
                        head,
                        flags=re.IGNORECASE,
                    ):
                        return False
                    head = re.sub(r"(?:'s|’s)\s*$", "", head).strip()
                    # Require at least first+last name tokens to avoid capturing places like "Caribbean".
                    if len([t for t in head.split() if t]) < 2:
                        return False
                    first = head.split()[0]
                    first_clean = first.rstrip(".").lower()
                    if first_clean in {
                        "on",
                        "in",
                        "at",
                        "from",
                        "by",
                        "for",
                        "to",
                        "as",
                        "with",
                        "without",
                        "after",
                        "before",
                        "during",
                    }:
                        return False
                    if first_clean in {
                        "jan",
                        "january",
                        "feb",
                        "february",
                        "mar",
                        "march",
                        "apr",
                        "april",
                        "may",
                        "jun",
                        "june",
                        "jul",
                        "july",
                        "aug",
                        "august",
                        "sep",
                        "sept",
                        "september",
                        "oct",
                        "october",
                        "nov",
                        "november",
                        "dec",
                        "december",
                    }:
                        return False
                    # Reject verb/adjective-like starters that often leak in from prose.
                    if re.match(r"^[A-Z][a-z]{3,}(?:ed|ing)$", first):
                        return False
                    # Reject trailing abbreviations like "U.S." / "US" which are almost never a surname.
                    if re.search(r"(?:^|\W)(?:U\.?S\.?|UK|EU)(?:\W|$)", head, flags=re.IGNORECASE):
                        return False
                    if re.search(r"\bthe\b", head, flags=re.IGNORECASE):
                        return False
                    last = head.split()[-1]
                    # Reject truncated two-token outputs like "George W." which are almost never full names.
                    if len(head.split()) == 2 and re.fullmatch(r"[A-Z]\.?", last):
                        return False
                    # Reject truncated outputs like "Victor S" (single-letter last token without a dot).
                    if len(last) == 1 and not last.endswith("."):
                        return False
                    return True

                # Unicode-aware name extractor (supports accents like Muñoz / Piñero).
                token = r"[A-ZÀ-ÖØ-Þ](?:[^\W\d_]|[.'’\-]){0,23}"
                name_pat = re.compile(rf"(?P<name>(?:{token}\s+)?{token}(?:\s+{token}){{1,4}})")
                def _name_key(value: str) -> str:
                    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

                # Track dedupe by name, not by full "name - role [n]" text.
                seen_name_keys = {
                    _name_key(re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", x).strip(), 1)[0].strip())
                    for x in key_people_items
                }
                for match in name_pat.finditer(pool):
                    if len(key_people_items) >= 14:
                        break
                    name = match.group("name").strip()
                    name, role = _split_title(name)
                    name = re.sub(r"(?:'s|’s)\s*$", "", name).strip()
                    # If a sentence leaked into the captured name (e.g. "X. After"), trim at the period.
                    if re.search(
                        r"\.\s*(?:After|However|But|And|Or|So|Then|When|While|Because|Since|Therefore|Thus|Meanwhile|Additionally|Moreover)\b",
                        name,
                        flags=re.IGNORECASE,
                    ):
                        name = re.split(r"\.", name, maxsplit=1)[0].strip()
                    if not _looks_like_person_strict(name):
                        continue
                    nk = _name_key(name)
                    if nk and nk in seen_name_keys:
                        continue
                    # Find a nearby citation after the name without consuming the whole sentence,
                    # so multiple names can be extracted from the same cited sentence.
                    tail = pool[match.end() : match.end() + 800]
                    # Prefer a citation in the same sentence; fall back to the immediate window.
                    sentence_end = re.search(r"[.!?]", tail)
                    search_span = tail[: sentence_end.start()] if sentence_end else tail
                    cit_match = re.search(r"\[[0-9]+\]", search_span) or re.search(r"\[[0-9]+\]", tail)
                    if not cit_match:
                        continue
                    cit = cit_match.group(0).strip()
                    candidate = f"{name} — {role} {cit}".strip() if role else f"{name} {cit}".strip()
                    if _norm_for_filter(candidate) in seen:
                        continue
                    if _is_generic_person(candidate) or not _is_name_like(candidate):
                        continue
                    if _is_non_person_entity_name(candidate):
                        continue
                    cit_ids = [int(x) for x in re.findall(r"\[(\d+)\]", cit)]
                    if not _name_supported_by_sources(name, cit_ids):
                        continue
                    if topic_phrases:
                        head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                        if any(phrase == head for phrase in topic_phrases):
                            continue
                    if subject_phrases:
                        head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                        if any(phrase == head for phrase in subject_phrases):
                            continue
                    key_people_items.append(candidate)
                    seen.add(_norm_for_filter(candidate))
                    if nk:
                        seen_name_keys.add(nk)

                if len(key_people_items) < 6 and source_records:
                    # Fallback: mine names directly from the per-source excerpts so Key People doesn't
                    # depend on upstream narrative text containing citations.
                    connector = r"(?:de|del|da|di|van|von|la|le|du|st\.?|saint|y)"
                    name_token = r"(?:[A-ZÀ-ÖØ-Ý]\.|[A-ZÀ-ÖØ-Ý][^\W\d_]+(?:[.'’\-][^\W\d_]+)*)"
                    focus_years = {
                        y
                        for y in re.findall(
                            r"\b(1[5-9]\d{2}|20\d{2})\b",
                            " ".join(timeline_items + key_events_items + _coerce_list(facts) + _coerce_list(source_notes)),
                        )
                    }
                    trailing_connectors = {"de", "del", "da", "di", "van", "von", "la", "le", "du", "st", "st.", "saint", "y"}
                    title_tokens = {
                        "president",
                        "general",
                        "governor",
                        "senator",
                        "secretary",
                        "admiral",
                        "colonel",
                        "captain",
                        "major",
                        "lieutenant",
                        "judge",
                        "justice",
                        "representative",
                        "ambassador",
                        "dr",
                        "doctor",
                    }
                    titled_pat = re.compile(
                        rf"\b(?P<title>President|General|Governor|Senator|Secretary|Admiral|Colonel|Captain|Major|Lieutenant|Judge|Justice|Representative|Ambassador|Commissioner|Dr\.?|Doctor)\s+(?P<name>{name_token}(?:\s+(?:{connector}|{name_token})){{1,5}})",
                        flags=re.UNICODE,
                    )
                    plain_pat = re.compile(
                        rf"(?P<name>{name_token}(?:\s+(?:{connector}|{name_token})){{1,4}})",
                        flags=re.UNICODE,
                    )
                    role_context_re = re.compile(
                        r"\b(governor|general|president|senator|secretary|admiral|colonel|captain|major|lieutenant|judge|justice|representative|ambassador|commissioner|commander|leader|politician|journalist|writer|author|poet|educator|activist|physician|doctor)\b",
                        flags=re.IGNORECASE,
                    )

                    for rec in source_records:
                        if len(key_people_items) >= 14:
                            break
                        sid = rec.get("id")
                        try:
                            sid_int = int(sid)
                        except Exception:
                            continue
                        excerpt = str(rec.get("text_excerpt") or rec.get("text") or "")
                        if not excerpt:
                            continue
                        added_here = 0
                        for match in titled_pat.finditer(excerpt):
                            if len(key_people_items) >= 14 or added_here >= 3:
                                break
                            title = re.sub(r"\s+", " ", match.group("title").strip()).rstrip(".")
                            name = re.sub(r"\s+", " ", match.group("name").strip()).strip(" ,;:.)(")
                            # If we matched "Major General X", title=Major and name starts with "General ...".
                            parts = [p for p in re.split(r"\s+", name) if p]
                            while parts and parts[0].rstrip(".").lower() in title_tokens:
                                parts = parts[1:]
                            while parts and parts[-1].rstrip(".").lower() in trailing_connectors:
                                parts = parts[:-1]
                            name = " ".join(parts).strip()
                            if not name:
                                continue
                            if focus_years:
                                window = excerpt[max(0, match.start() - 250) : match.end() + 250]
                                if not any(y in window for y in focus_years):
                                    continue
                            if not _looks_like_person_strict(name):
                                continue
                            if _is_non_person_entity_name(name):
                                continue
                            if not _is_name_like(name):
                                continue
                            nk = _name_key(name)
                            if nk and nk in seen_name_keys:
                                continue
                            if not _name_supported_by_sources(name, [sid_int]):
                                continue
                            candidate = f"{name} - {title} [{sid_int}]".strip()
                            if _norm_for_filter(candidate) in seen:
                                continue
                            if _is_generic_person(candidate):
                                continue
                            if topic_phrases:
                                head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                                if any(phrase == head for phrase in topic_phrases):
                                    continue
                            if subject_phrases:
                                head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                                if any(phrase == head for phrase in subject_phrases):
                                    continue
                            key_people_items.append(candidate)
                            seen.add(_norm_for_filter(candidate))
                            if nk:
                                seen_name_keys.add(nk)
                            added_here += 1
                        if added_here >= 2:
                            continue
                        for match in plain_pat.finditer(excerpt):
                            if len(key_people_items) >= 14 or added_here >= 3:
                                break
                            name = re.sub(r"\s+", " ", match.group("name").strip()).strip(" ,;:.)(")
                            parts = [p for p in re.split(r"\s+", name) if p]
                            while parts and parts[-1].rstrip(".").lower() in trailing_connectors:
                                parts = parts[:-1]
                            name = " ".join(parts).strip()
                            if not name:
                                continue
                            if focus_years:
                                window = excerpt[max(0, match.start() - 250) : match.end() + 250]
                                if not any(y in window for y in focus_years):
                                    continue
                            # Avoid listing non-people entities (places, organizations, events) when no role
                            # word appears near the extracted name.
                            before = excerpt[max(0, match.start() - 180) : match.start()]
                            after = excerpt[match.end() : match.end() + 180]
                            if not (role_context_re.search(before) or role_context_re.search(after)):
                                continue
                            if not _looks_like_person_strict(name):
                                continue
                            if _is_non_person_entity_name(name):
                                continue
                            if not _is_name_like(name):
                                continue
                            nk = _name_key(name)
                            if nk and nk in seen_name_keys:
                                continue
                            if not _name_supported_by_sources(name, [sid_int]):
                                continue
                            candidate = f"{name} [{sid_int}]".strip()
                            if _norm_for_filter(candidate) in seen:
                                continue
                            if _is_generic_person(candidate):
                                continue
                            if topic_phrases:
                                head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                                if any(phrase == head for phrase in topic_phrases):
                                    continue
                            if subject_phrases:
                                head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                                if any(phrase == head for phrase in subject_phrases):
                                    continue
                            key_people_items.append(candidate)
                            seen.add(_norm_for_filter(candidate))
                            if nk:
                                seen_name_keys.add(nk)
                            added_here += 1

            sections: list[str] = [
                "# Project Title",
                title,
                "",
                "# Project Task",
                task,
                "",
                "## Introduction",
                intro,
            ]
            if background_section:
                sections.extend(["", background_section])
            turning_points = _format_turning_points(key_events_items, timeline_items)
            if turning_points:
                sections.extend(["", turning_points])
            timeline_section = _render_section("Timeline", timeline_items)
            if timeline_section:
                sections.extend(["", timeline_section])
            key_people_section = _render_section("Key People", key_people_items)
            if key_people_section:
                sections.extend(["", key_people_section])
            key_events_section = _render_section("Key Events", key_events_items)
            if key_events_section:
                sections.extend(["", key_events_section])

            consequences_section = _format_consequences(consequences)
            if consequences_section:
                sections.extend(["", consequences_section])
            merged_interpretations: list[Any] = []
            merged_interpretations.extend(_coerce_any_list(interpretations))
            merged_interpretations.extend(_coerce_any_list(dissenting_views))
            if isinstance(critical_analysis, dict):
                for key in ("interpretations", "dissenting_views", "dissenting_perspectives", "debates"):
                    merged_interpretations.extend(_coerce_any_list(critical_analysis.get(key)))
            interpretations_section = _format_interpretations(merged_interpretations)
            if interpretations_section:
                sections.extend(["", interpretations_section])
            limitations_section = _format_limitations(limitations)
            if limitations_section:
                sections.extend(["", limitations_section])
            questions_section = _format_discussion_questions(discussion_questions)
            if questions_section:
                sections.extend(["", questions_section])

            sources_block = _build_sources_block(sources)
            if sources_block:
                sections.extend(["", sources_block])

            # Convert to kid-friendly section titles if needed
            doc = "\n".join(sections).strip()
            if audience == "kid":
                # Replace adult section titles with kid-friendly ones
                doc = doc.replace("# Project Title\n", "# ")  # Remove "Project Title" header
                doc = doc.replace("# Project Task\n", "## What You'll Learn\n")
                doc = doc.replace("## Introduction\n", "## The Story\n")
                doc = doc.replace("## Historical Background (Context + Causes)\n", "## Why It Happened\n")
                doc = doc.replace("## Key Turning Points\n", "## Important Moments\n")
                doc = doc.replace("## Timeline\n", "## When Things Happened\n")
                doc = doc.replace("## Key People\n", "## Important People\n")
                doc = doc.replace("## Key Events\n", "## What Happened\n")
                doc = doc.replace("## Consequences & Legacy\n", "## What Changed\n")
                doc = doc.replace("## Different Historical Interpretations\n", "## Different Ideas\n")
                doc = doc.replace("## Limitations and Further Research\n", "## Questions We Still Have\n")
                doc = doc.replace("## Discussion Questions\n", "## Think About This\n")
                doc = doc.replace("## Sources\n", "## Where We Learned This\n")

            return doc

        sources_block = _list(sources) or "(no sources provided)"
        audience = self._audience_level(request)
        if audience == "kid":
            prompt = (
                f"Kids history project request:\n{request}\n\n"
                f"Summary:\n{summary}\n\n"
                f"Background:\n{_list(context_points)}\n\n"
                f"Causes:\n{_list(causes)}\n\n"
                f"Timeline:\n{_list(timeline)}\n\n"
                f"Key People:\n{_list(key_figures)}\n\n"
                f"Key Events:\n{_list(key_events)}\n\n"
                f"Facts:\n{_list(facts)}\n\n"
                f"Source Notes:\n{_list(source_notes)}\n\n"
                "Sources list (use verbatim in the Sources section):\n"
                f"{sources_block}\n\n"
                "Write a kid-friendly HISTORY PROJECT in markdown with these REQUIRED sections:\n"
                "1) Project Title (exciting and simple, like 'Dinosaurs: Amazing Creatures!')\n"
                "2) Project Task (1 simple sentence, like 'Learn about dinosaurs and how they lived!')\n"
                "3) What You Will Learn (3-4 simple bullets)\n"
                "4) The Story (2-3 short paragraphs using VERY simple words that 4th graders understand)\n"
                "5) Timeline (bulleted, chronological, with citations)\n"
                "6) Key People (bulleted, with citations)\n"
                "7) Fun Facts (bulleted, with citations)\n"
                "8) Vocabulary (6-10 words with simple definitions)\n"
                "9) Try This (2-3 simple activities or questions)\n"
                "10) Sources for Parents (use the sources list verbatim)\n"
                "Rules:\n"
                "- CRITICAL: Use ONLY simple words a 4th grader (9-10 years old) can understand.\n"
                "- CRITICAL: Avoid complex terms. Replace: 'Mesozoic Era' with 'a long time ago', 'extinction' with 'died out', 'Cretaceous-Paleogene' with 'when dinosaurs disappeared'.\n"
                "- CRITICAL: Make Project Task exciting and simple, NOT academic (BAD: 'To analyze...', GOOD: 'Learn about...').\n"
                "- CRITICAL: Keep sentences SHORT - maximum 10-15 words each.\n"
                "- Include citations [1], [2] in Timeline and Fun Facts.\n"
                "- If something is uncertain, say so in simple words.\n"
                "- Avoid repeating the same sentence or event.\n"
                "- Do NOT add placeholder sources or notes about missing sources.\n"
                "- Use the provided lists verbatim when possible to keep citations accurate.\n"
                "- CRITICAL: Output clean text ONLY. Do NOT include dictionary structures like {'statement': '...', 'source_id': '1'}.\n"
                "- CRITICAL: All bullets must be plain text with citations, like: '- Dinosaurs lived 165 million years [3]'\n"
            )
            max_tokens = 1600
        elif audience == "teen":
            prompt = (
                f"Teen history project request:\n{request}\n\n"
                f"Summary:\n{summary}\n\n"
                f"Background:\n{_list(context_points)}\n\n"
                f"Causes:\n{_list(causes)}\n\n"
                f"Consequences:\n{_list(consequences)}\n\n"
                f"Timeline:\n{_list(timeline)}\n\n"
                f"Key People:\n{_list(key_figures)}\n\n"
                f"Key Events:\n{_list(key_events)}\n\n"
                f"Facts:\n{_list(facts)}\n\n"
                f"Source Notes:\n{_list(source_notes)}\n\n"
                f"Different Interpretations:\n{_list(interpretations)}\n\n"
                f"Limitations / Further Research:\n{_list(limitations)}\n\n"
                f"Discussion Questions:\n{_list(discussion_questions)}\n\n"
                "Sources list (use verbatim in the Sources section):\n"
                f"{sources_block}\n\n"
                "Write a teen-focused HISTORY PROJECT in markdown with these REQUIRED sections:\n"
                "1) Project Title\n"
                "2) Project Task (1 sentence)\n"
                "3) Introduction (2-3 paragraphs)\n"
                "4) Background & Causes (short paragraphs, cite sources)\n"
                "5) Timeline (10-14 bullets, chronological, with citations)\n"
                "6) Key People (bulleted, with citations)\n"
                "7) Key Events (bulleted, with citations)\n"
                "8) Changes & Consequences (short paragraphs, with citations)\n"
                "9) Different Perspectives (2-3 debates with citations)\n"
                "10) Limitations and Further Research\n"
                "11) Why It Matters Today\n"
                "12) Discussion Questions (8-12)\n"
                "13) Sources (use the sources list verbatim)\n"
                "Rules:\n"
                "- Keep tone clear and student-friendly, but more detailed than kids level.\n"
                "- Cite sources inline using [1], [2] for every factual statement.\n"
                "- If something is uncertain, label it explicitly as uncertain.\n"
                "- Use the provided timeline list only; do not invent new dates.\n"
                "- Avoid repeating the same sentence or event.\n"
                "- Do NOT add placeholder sources or notes about missing sources.\n"
                "- Use at least 6 different source ids across the report; do not overuse [1] or [2].\n"
                "- Use the provided lists verbatim when possible to keep citations accurate.\n"
                "- CRITICAL: Output clean markdown ONLY. Do NOT include dictionary structures like {'statement': '...', 'source_id': '1'}.\n"
                "- CRITICAL: All bullets must be plain text with citations, like: '- The Civil War began in 1861 [3]'\n"
            )
            max_tokens = 2400
        else:
            prompt = (
                f"History project request:\n{request}\n\n"
                f"Summary:\n{summary}\n\n"
                f"Background:\n{_list(context_points)}\n\n"
                f"Causes:\n{_list(causes)}\n\n"
                f"Consequences:\n{_list(consequences)}\n\n"
                f"Timeline:\n{_list(timeline)}\n\n"
                f"Key Figures:\n{_list(key_figures)}\n\n"
                f"Key Events:\n{_list(key_events)}\n\n"
                f"Facts:\n{_list(facts)}\n\n"
                f"Claims:\n{_list(claims)}\n\n"
                f"Source Notes:\n{_list(source_notes)}\n\n"
                f"Different Interpretations:\n{_list(interpretations)}\n\n"
                f"Limitations / Further Research:\n{_list(limitations)}\n\n"
                f"Discussion Questions:\n{_list(discussion_questions)}\n\n"
                "Sources list (use verbatim in the Sources section):\n"
                f"{sources_block}\n\n"
                "Write a HISTORY PROJECT or essay suitable for a teacher or historian in markdown with these REQUIRED sections:\n"
                "1) Project Title\n"
                "2) Project Task (1 sentence)\n"
                "3) Introduction (2-3 paragraphs)\n"
                "4) Historical Background (context + causes, with citations)\n"
                "5) Key Turning Points (short paragraphs, with citations)\n"
                "6) Timeline (10-14 bullets, chronological, with citations)\n"
                "7) Key People (bulleted, with citations)\n"
                "8) Key Events (bulleted, with citations)\n"
                "9) Consequences & Legacy (detailed, with citations)\n"
                "10) Different Historical Interpretations (2-3 debates, with citations)\n"
                "11) Limitations and Further Research\n"
                "12) Discussion Questions (10-14)\n"
                "13) Sources (use the sources list verbatim)\n"
                "Rules:\n"
                "- Cite sources inline using [1], [2] for every factual statement.\n"
                "- If something is uncertain, label it explicitly as uncertain.\n"
                "- Keep language clear, professional, and detailed.\n"
                "- Use the provided timeline list only; do not invent new dates.\n"
                "- Avoid repeating the same sentence or event.\n"
                "- Do NOT add placeholder sources or notes about missing sources.\n"
                "- Use at least 6 different source ids across the report; do not overuse [1] or [2].\n"
                "- Use the provided lists verbatim when possible to keep citations accurate.\n"
                "- Ensure Key People includes multiple perspectives (local voices, not just U.S. officials).\n"
                "- CRITICAL: Output clean markdown ONLY. Do NOT include dictionary structures like {'statement': '...', 'source_id': '1'}.\n"
                "- CRITICAL: All bullets must be plain text with citations, like: '- Napoleon invaded Russia in 1812 [5]'\n"
            )
            max_tokens = 3200

        max_tokens = int(context.initial_parameters.get("workflow_max_tokens") or max_tokens)
        max_tokens = max(800, min(max_tokens, 8192))

        structured_output = bool(self.config.get("structured_output", False))

        if structured_output:
            text = _clean_document(_build_structured_document())
            return AgentResult(
                ok=True,
                data={
                    "document": text,
                    "format": "markdown",
                    "sources": sources,
                    "source_meta": source_meta,
                    "audience": audience,
                },
            )

        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_format="text",
            max_tokens=max_tokens,
            temperature=0.25,
        )
        if not res.ok:
            return res
        text = _clean_document(str(res.data.get("text") or ""))
        maybe_json = _safe_json(text)
        if maybe_json and isinstance(maybe_json, dict) and any(
            key in maybe_json for key in ("summary", "context", "causes", "timeline", "key_figures", "key_events")
        ):
            summary = maybe_json.get("summary") or summary
            timeline = maybe_json.get("timeline") or timeline
            key_figures = maybe_json.get("key_figures") or maybe_json.get("key_people") or key_figures
            key_events = maybe_json.get("key_events") or key_events
            context_points = maybe_json.get("context") or context_points
            causes = maybe_json.get("causes") or causes
            consequences = maybe_json.get("consequences") or consequences
            interpretations = maybe_json.get("interpretations") or interpretations
            limitations = maybe_json.get("limitations") or limitations
            discussion_questions = maybe_json.get("discussion_questions") or discussion_questions
            text = _clean_document(_build_structured_document())
            return AgentResult(
                ok=True,
                data={
                    "document": text,
                    "format": "markdown",
                    "sources": sources,
                    "source_meta": source_meta,
                    "audience": audience,
                },
            )
        # Force key academic sections to use structured inputs to avoid placeholder output.
        timeline_candidates: list[str] = []
        timeline_candidates.extend(_coerce_events(timeline))
        timeline_candidates.extend(_coerce_events(key_events))
        timeline_candidates.extend(_extract_dated(key_events))
        # Only fall back to pulling dated sentences from narrative text if the explicit timeline is too short.
        if len(timeline_candidates) < 8:
            timeline_candidates.extend(_extract_dated(source_notes))
            timeline_candidates.extend(_extract_dated(facts))
            timeline_candidates.extend(_extract_dated_from_text([summary] + _coerce_list(context_points)))
            timeline_candidates.extend(
                _extract_dated_from_text(
                    [summary]
                    + _coerce_list(context_points)
                    + _coerce_list(causes)
                    + _coerce_list(consequences)
                    + _coerce_list(facts)
                    + _coerce_list(source_notes)
                )
            )
        timeline_items = _filter_timeline(timeline_candidates, max_items=14)
        timeline_section = _render_section("Timeline", timeline_items)

        key_people_items = _filter_people(_coerce_people(key_figures), max_items=14)
        if source_text_norm_by_id and key_people_items:
            kept: list[str] = []
            for item in key_people_items:
                cit_ids = [int(x) for x in re.findall(r"\[(\d+)\]", item)]
                name_part = re.split(r"\s*(?:—|–|-|:)\s*", re.sub(r"\[\d+\]", "", item).strip(), 1)[0].strip()
                name_part = re.sub(r"(?:'s|'s)\b.*$", "", name_part).strip()
                if _name_supported_by_sources(name_part, cit_ids):
                    kept.append(item)
            key_people_items = kept
        if context_points or causes or consequences or source_notes or facts or timeline_items:
            pool = " ".join(
                [summary]
                + _coerce_list(context_points)
                + _coerce_list(causes)
                + _coerce_list(consequences)
                + _coerce_list(source_notes)
                + _coerce_list(facts)
                + _coerce_events(key_events)
                + timeline_items
            )
            # Generic "name + citation" rescue: add a few real people that appear in sources but
            # didn't make it into key_figures (no topic-specific hardcoding).
            seen = {_norm_for_filter(p) for p in key_people_items}
            topic_phrases = _topic_phrases_for_filter(request)
            subject_phrases = _subject_phrases_from_request(request)
            title_map = {
                "president": "President",
                "general": "General",
                "governor": "Governor",
                "senator": "Senator",
                "secretary": "Secretary",
                "minister": "Minister",
                "prime": "Prime Minister",
                "dr": "Dr.",
                "doctor": "Dr.",
                "prof": "Professor",
                "professor": "Professor",
                "king": "King",
                "queen": "Queen",
                "sir": "Sir",
            }

            def _split_title(name: str) -> tuple[str, str]:
                parts = [p for p in re.split(r"\s+", name.strip()) if p]
                if len(parts) < 2:
                    return name.strip(), ""
                raw0 = parts[0].rstrip(".").lower()
                if raw0 in title_map:
                    return " ".join(parts[1:]).strip(), title_map[raw0]
                if len(parts) >= 2 and raw0 == "prime" and parts[1].lower().startswith("minister"):
                    return " ".join(parts[2:]).strip(), "Prime Minister"
                return name.strip(), ""

            def _looks_like_person_strict(name: str) -> bool:
                head = re.sub(r"[^\w\s.''\\-]", "", str(name or "")).strip()
                if not head:
                    return False
                if re.search(
                    r"\.\s*(?:After|However|But|And|Or|So|Then|When|While|Because|Since|Therefore|Thus|Meanwhile|Additionally|Moreover)\b",
                    head,
                    flags=re.IGNORECASE,
                ):
                    return False
                head = re.sub(r"(?:'s|’s)\s*$", "", head).strip()
                if len([t for t in head.split() if t]) < 2:
                    return False
                first = head.split()[0]
                first_clean = first.rstrip(".").lower()
                if first_clean in {
                    "on",
                    "in",
                    "at",
                    "from",
                    "by",
                    "for",
                    "to",
                    "as",
                    "with",
                    "without",
                    "after",
                    "before",
                    "during",
                }:
                    return False
                if first_clean in {
                    "jan",
                    "january",
                    "feb",
                    "february",
                    "mar",
                    "march",
                    "apr",
                    "april",
                    "may",
                    "jun",
                    "june",
                    "jul",
                    "july",
                    "aug",
                    "august",
                    "sep",
                    "sept",
                    "september",
                    "oct",
                    "october",
                    "nov",
                    "november",
                    "dec",
                    "december",
                }:
                    return False
                if re.match(r"^[A-Z][a-z]{3,}(?:ed|ing)$", first):
                    return False
                if re.search(r"(?:^|\W)(?:U\.?S\.?|UK|EU)(?:\W|$)", head, flags=re.IGNORECASE):
                    return False
                if re.search(r"\bthe\b", head, flags=re.IGNORECASE):
                    return False
                last = head.split()[-1]
                if len(last) == 1 and not last.endswith("."):
                    return False
                return True
            # Unicode-aware name extractor (supports accents like Muñoz / Piñero).
            token = r"[A-ZÀ-ÖØ-Þ](?:[^\W\d_]|[.'’\-]){0,23}"
            name_pat = re.compile(rf"(?P<name>(?:{token}\s+)?{token}(?:\s+{token}){{1,4}})")
            def _name_key(value: str) -> str:
                return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

            seen_name_keys = {
                _name_key(re.split(r"\s*(?:—|–|-|:)\s*", re.sub(r"\[\d+\]", "", x).strip(), 1)[0].strip())
                for x in key_people_items
            }
            for match in name_pat.finditer(pool):
                if len(key_people_items) >= 14:
                    break
                name = match.group("name").strip()
                name, role = _split_title(name)
                name = re.sub(r"(?:'s|’s)\s*$", "", name).strip()
                if re.search(
                    r"\.\s*(?:After|However|But|And|Or|So|Then|When|While|Because|Since|Therefore|Thus|Meanwhile|Additionally|Moreover)\b",
                    name,
                    flags=re.IGNORECASE,
                ):
                    name = re.split(r"\.", name, maxsplit=1)[0].strip()
                if not _looks_like_person_strict(name):
                    continue
                nk = _name_key(name)
                if nk and nk in seen_name_keys:
                    continue
                tail = pool[match.end() : match.end() + 800]
                sentence_end = re.search(r"[.!?]", tail)
                search_span = tail[: sentence_end.start()] if sentence_end else tail
                cit_match = re.search(r"\[[0-9]+\]", search_span) or re.search(r"\[[0-9]+\]", tail)
                if not cit_match:
                    continue
                cit = cit_match.group(0).strip()
                candidate = f"{name} — {role} {cit}".strip() if role else f"{name} {cit}".strip()
                if _norm_for_filter(candidate) in seen:
                    continue
                if _is_generic_person(candidate) or not _is_name_like(candidate):
                    continue
                if _is_non_person_entity_name(candidate):
                    continue
                cit_ids = [int(x) for x in re.findall(r"\[(\d+)\]", cit)]
                if not _name_supported_by_sources(name, cit_ids):
                    continue
                if topic_phrases:
                    head = re.split(r"\s*[:\-–—]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                    if any(phrase == head for phrase in topic_phrases):
                        continue
                if subject_phrases:
                    head = re.split(r"\s*[:\-–—]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                    if any(phrase == head for phrase in subject_phrases):
                        continue
                key_people_items.append(candidate)
                seen.add(_norm_for_filter(candidate))
                if nk:
                    seen_name_keys.add(nk)
            if len(key_people_items) < 6 and source_records:
                connector = r"(?:de|del|da|di|van|von|la|le|du|st\.?|saint|y)"
                name_token = r"(?:[A-ZÀ-ÖØ-Ý]\.|[A-ZÀ-ÖØ-Ý][^\W\d_]+(?:[.'’\-][^\W\d_]+)*)"
                focus_years = {
                    y
                    for y in re.findall(
                        r"\b(1[5-9]\d{2}|20\d{2})\b",
                        " ".join(timeline_items + key_events_items + _coerce_list(facts) + _coerce_list(source_notes)),
                    )
                }
                trailing_connectors = {"de", "del", "da", "di", "van", "von", "la", "le", "du", "st", "st.", "saint", "y"}
                title_tokens = {
                    "president",
                    "general",
                    "governor",
                    "senator",
                    "secretary",
                    "admiral",
                    "colonel",
                    "captain",
                    "major",
                    "lieutenant",
                    "judge",
                    "justice",
                    "representative",
                    "ambassador",
                    "dr",
                    "doctor",
                }
                titled_pat = re.compile(
                    rf"\b(?P<title>President|General|Governor|Senator|Secretary|Admiral|Colonel|Captain|Major|Lieutenant|Judge|Justice|Representative|Ambassador|Commissioner|Dr\.?|Doctor)\s+(?P<name>{name_token}(?:\s+(?:{connector}|{name_token})){{1,5}})",
                    flags=re.UNICODE,
                )
                plain_pat = re.compile(
                    rf"(?P<name>{name_token}(?:\s+(?:{connector}|{name_token})){{1,4}})",
                    flags=re.UNICODE,
                )
                role_context_re = re.compile(
                    r"\b(governor|general|president|senator|secretary|admiral|colonel|captain|major|lieutenant|judge|justice|representative|ambassador|commissioner|commander|leader|politician|journalist|writer|author|poet|educator|activist|physician|doctor)\b",
                    flags=re.IGNORECASE,
                )

                for rec in source_records:
                    if len(key_people_items) >= 14:
                        break
                    sid = rec.get("id")
                    try:
                        sid_int = int(sid)
                    except Exception:
                        continue
                    excerpt = str(rec.get("text_excerpt") or rec.get("text") or "")
                    if not excerpt:
                        continue
                    added_here = 0
                    for match in titled_pat.finditer(excerpt):
                        if len(key_people_items) >= 14 or added_here >= 3:
                            break
                        title = re.sub(r"\s+", " ", match.group("title").strip()).rstrip(".")
                        name = re.sub(r"\s+", " ", match.group("name").strip()).strip(" ,;:.)(")
                        parts = [p for p in re.split(r"\s+", name) if p]
                        while parts and parts[0].rstrip(".").lower() in title_tokens:
                            parts = parts[1:]
                        while parts and parts[-1].rstrip(".").lower() in trailing_connectors:
                            parts = parts[:-1]
                        name = " ".join(parts).strip()
                        if not name:
                            continue
                        if focus_years:
                            window = excerpt[max(0, match.start() - 250) : match.end() + 250]
                            if not any(y in window for y in focus_years):
                                continue
                        if not _looks_like_person_strict(name):
                            continue
                        if _is_non_person_entity_name(name):
                            continue
                        if not _is_name_like(name):
                            continue
                        nk = _name_key(name)
                        if nk and nk in seen_name_keys:
                            continue
                        if not _name_supported_by_sources(name, [sid_int]):
                            continue
                        candidate = f"{name} - {title} [{sid_int}]".strip()
                        if _norm_for_filter(candidate) in seen:
                            continue
                        if _is_generic_person(candidate):
                            continue
                        if topic_phrases:
                            head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                            if any(phrase == head for phrase in topic_phrases):
                                continue
                        if subject_phrases:
                            head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                            if any(phrase == head for phrase in subject_phrases):
                                continue
                        key_people_items.append(candidate)
                        seen.add(_norm_for_filter(candidate))
                        if nk:
                            seen_name_keys.add(nk)
                        added_here += 1
                    if added_here >= 2:
                        continue
                    for match in plain_pat.finditer(excerpt):
                        if len(key_people_items) >= 14 or added_here >= 3:
                            break
                        name = re.sub(r"\s+", " ", match.group("name").strip()).strip(" ,;:.)(")
                        parts = [p for p in re.split(r"\s+", name) if p]
                        while parts and parts[-1].rstrip(".").lower() in trailing_connectors:
                            parts = parts[:-1]
                        name = " ".join(parts).strip()
                        if not name:
                            continue
                        if focus_years:
                            window = excerpt[max(0, match.start() - 250) : match.end() + 250]
                            if not any(y in window for y in focus_years):
                                continue
                        before = excerpt[max(0, match.start() - 180) : match.start()]
                        after = excerpt[match.end() : match.end() + 180]
                        if not (role_context_re.search(before) or role_context_re.search(after)):
                            continue
                        if not _looks_like_person_strict(name):
                            continue
                        if _is_non_person_entity_name(name):
                            continue
                        if not _is_name_like(name):
                            continue
                        nk = _name_key(name)
                        if nk and nk in seen_name_keys:
                            continue
                        if not _name_supported_by_sources(name, [sid_int]):
                            continue
                        candidate = f"{name} [{sid_int}]".strip()
                        if _norm_for_filter(candidate) in seen:
                            continue
                        if _is_generic_person(candidate):
                            continue
                        if topic_phrases:
                            head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                            if any(phrase == head for phrase in topic_phrases):
                                continue
                        if subject_phrases:
                            head = re.split(r"\s*[-–—:]\s*", re.sub(r"\[\d+\]", "", candidate).strip(), 1)[0].strip().lower()
                            if any(phrase == head for phrase in subject_phrases):
                                continue
                        key_people_items.append(candidate)
                        seen.add(_norm_for_filter(candidate))
                        if nk:
                            seen_name_keys.add(nk)
                        added_here += 1
        key_people_section = _render_section("Key People", key_people_items)

        key_events_items = _filter_events(_coerce_events(key_events), max_items=12)
        if not key_events_items:
            key_events_items = timeline_items
        if not key_events_items:
            key_events_items = _filter_events(_extract_dated(facts), max_items=12)
        if not key_events_items:
            key_events_items = _filter_events(
                _extract_dated_from_text(
                    [summary]
                    + _coerce_list(context_points)
                    + _coerce_list(causes)
                    + _coerce_list(consequences)
                    + _coerce_list(facts)
                    + _coerce_list(source_notes)
                ),
                max_items=12,
            )
        key_events_section = _render_section("Key Events", key_events_items)

        background_lines = _filter_background(_coerce_list(context_points) + _coerce_list(causes), max_items=10)
        if len(background_lines) < 4:
            background_lines = _filter_background(
                _extract_background_sentences(
                    [summary]
                    + _coerce_list(context_points)
                    + _coerce_list(causes)
                    + _coerce_list(facts)
                    + _coerce_list(source_notes)
                ),
                max_items=10,
            )
        background_section = _render_section("Historical Background (Context + Causes)", background_lines)

        turning_points_section = _format_turning_points(key_events_items, timeline_items)
        merged_interpretations: list[Any] = []
        merged_interpretations.extend(_coerce_any_list(interpretations))
        merged_interpretations.extend(_coerce_any_list(dissenting_views))
        if isinstance(critical_analysis, dict):
            for key in ("interpretations", "dissenting_views", "dissenting_perspectives", "debates"):
                merged_interpretations.extend(_coerce_any_list(critical_analysis.get(key)))
        interpretations_section = _format_interpretations(merged_interpretations)
        limitations_section = _format_limitations(limitations)
        consequences_input = _coerce_list(consequences)
        if not consequences_input:
            pool = " ".join(
                _coerce_list(facts)
                + _coerce_list(source_notes)
                + _coerce_list(context_points)
                + _coerce_list(causes)
            )
            derived: list[str] = []
            for sentence in re.split(r"(?<=[.!?])\s+", pool):
                s = sentence.strip()
                if not s:
                    continue
                if len(s) < 40:
                    continue
                if not re.search(r"\[\d+\]", s):
                    continue
                if any(k in s.lower() for k in ("led to", "resulted", "caused", "impact", "changed", "shift", "reform", "legacy", "afterward")):
                    derived.append(s)
                if len(derived) >= 10:
                    break
            consequences_input = derived
        consequences_section = _format_consequences(consequences_input)
        questions_section = _format_discussion_questions(discussion_questions)

        if background_section:
            text = _replace_section(
                text,
                ["Historical Background", "Historical Background (Context + Causes)"],
                background_section,
            )
        text = _replace_section(text, ["Timeline", "Project Timeline"], timeline_section)
        text = _replace_section(text, ["Key People", "Key Figures"], key_people_section)
        text = _replace_section(text, ["Key Events"], key_events_section)
        text = _replace_section(text, ["Key Turning Points"], turning_points_section)
        if audience != "kid":
            if interpretations_section:
                text = _replace_section(
                    text,
                    ["Different Historical Interpretations", "Historiography", "Different Perspectives"],
                    interpretations_section,
                )
            if limitations_section:
                text = _replace_section(
                    text,
                    ["Limitations and Further Research", "Limitations", "Further Research"],
                    limitations_section,
                )
            if consequences_section:
                text = _replace_section(text, ["Consequences & Legacy", "Consequences"], consequences_section)
            if questions_section:
                text = _replace_section(text, ["Discussion Questions"], questions_section)
        text = _dedupe_sections(
            text,
            [
                "Timeline",
                "Key Turning Points",
                "Key People",
                "Key Events",
                "Discussion Questions",
                "Sources",
            ],
        )
        text = _clean_document(text)
        return AgentResult(
            ok=True,
            data={
                "document": text,
                "format": "markdown",
                "sources": sources,
                "source_meta": source_meta,
                "audience": audience,
            },
        )
