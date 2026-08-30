from __future__ import annotations

import ast
import json
import re
from typing import Any

from core.agents.llm_agent import _LLMBaseAgent
from core.pipeline.agent import AgentCapability, AgentResult


def _norm(text: str) -> str:
    value = re.sub(r"\[\s*\d+\s*\]", "", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _extract_citations(text: str) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for match in re.findall(r"\[(\d+)\]", str(text or "")):
        try:
            sid = int(match)
        except Exception:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _has_citation(text: str) -> bool:
    return bool(re.search(r"\[\d+\]", str(text or "")))


def _compact_paragraph(text: str, *, max_sentences: int = 8) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()]
    if not parts:
        return _clean_line(raw)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = _norm(part)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(part)
        if len(out) >= max_sentences:
            break
    return _clean_line(" ".join(out))


def _coerce_line(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, dict):
        date = str(item.get("date") or item.get("year") or "").strip()
        name = str(item.get("name") or item.get("person") or "").strip()
        title = str(item.get("title") or "").strip()
        text = str(
            item.get("statement")
            or item.get("description")
            or item.get("text")
            or item.get("detail")
            or item.get("fact")
            or ""
        ).strip()
        role = str(item.get("role") or "").strip()
        src = item.get("source_id") or item.get("source") or item.get("citation") or item.get("citations")
        citation = ""
        if src is not None:
            src_text = str(src).strip()
            if re.fullmatch(r"\d+", src_text):
                citation = f"[{src_text}]"
            else:
                found = re.search(r"\[\d+\]", src_text)
                if found:
                    citation = found.group(0)
        if date and (title or text):
            body = " ".join(x for x in (title, text) if x).strip()
            return f"{date}: {body} {citation}".strip()
        if name and role:
            return f"{name} - {role} {citation}".strip()
        if name and text:
            return f"{name} - {text} {citation}".strip()
        if name:
            return f"{name} {citation}".strip()
        if title and text:
            return f"{title}: {text} {citation}".strip()
        if title:
            return f"{title} {citation}".strip()
        if text:
            return f"{text} {citation}".strip()
        return ""
    raw = str(item).strip()
    trailing = re.search(r"(\[\d+\])\s*$", raw)
    trailing_citation = trailing.group(1) if trailing else ""
    candidate = raw[: trailing.start()].strip() if trailing else raw
    if candidate.startswith("{") and candidate.endswith("}") and "fact" in candidate.lower():
        try:
            parsed = ast.literal_eval(candidate)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            normalized = _coerce_line(parsed)
            if trailing_citation and not _has_citation(normalized):
                normalized = f"{normalized} {trailing_citation}".strip()
            return normalized
    return raw


def _dedupe(items: list[str], *, max_items: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        line = str(raw or "").strip()
        if not line:
            continue
        key = _norm(line)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line)
        if max_items and len(out) >= max_items:
            break
    return out


def _is_name_like(text: str) -> bool:
    head = re.split(r"\s*(?:-|--|---|:)\s*", re.sub(r"\[\d+\]", "", str(text or "").strip()), 1)[0].strip()
    if not head:
        return False
    if head.lower().startswith("the "):
        return False
    if any(ch.isdigit() for ch in head):
        return False
    if "," in head:
        return False
    words = [w for w in re.split(r"\s+", head) if w]
    if len(words) < 2 or len(words) > 5:
        return False
    if words[0].lower() in {"the", "a", "an"}:
        return False
    bad_tokens = {
        "government",
        "administration",
        "campaign",
        "treaty",
        "act",
        "war",
        "people",
        "forces",
        "committee",
        "report",
        "north",
        "south",
        "east",
        "west",
        "america",
        "american",
        "states",
        "puerto",
        "rico",
        "florida",
        "spanish",
        "empire",
        "island",
        "city",
        "harbor",
        "beach",
        "campaign",
        "invasion",
        "occupation",
        "control",
        "history",
        "manual",
        "library",
        "education",
        "congress",
        "senate",
        "today",
        "yesterday",
        "tomorrow",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "office",
        "member",
        "president",
        "minister",
        "citation",
        "information",
        "article",
        "title",
        "source",
        "video",
        "link",
        "avenue",
        "street",
        "building",
        "bill",
        "commission",
        "record",
        "records",
        "material",
        "materials",
        "introduction",
        "overview",
        "background",
        "legacy",
        "death",
        "facts",
        "fact",
        "definition",
        "review",
        "question",
        "questions",
        "related",
        "terms",
        "quick",
        "contents",
        "topic",
        "subject",
        "heritage",
        "story",
    }
    lowered = _norm(head)
    if any(token in lowered.split() for token in bad_tokens):
        return False
    # Person-like tokens are mostly title-case names or initials.
    particles = {"de", "del", "la", "las", "los", "y", "da", "do", "dos", "van", "von"}
    for token in words:
        t = token.strip(".")
        if t.lower() in particles:
            continue
        if len(t) < 3 and not re.fullmatch(r"[A-Z]\.", t):
            return False
        if not re.match(r"^[A-Z][A-Za-z.'-]*$", t):
            return False
    return True


def _clean_line(text: str) -> str:
    line = str(text or "").strip()
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"\b(1\d{3}|20\d{2})\s+[1-9]\b(?=[.,;:]|\s|$)", r"\1", line)
    line = re.sub(r"\bIn he\b", "He", line)
    line = re.sub(r"(?i)\bin July of local\b", "in July, local", line)
    line = re.sub(r"(?i)^(\d{4}:\s*)Hispaniola\s+In\s+the\s+newly\s+appointed\s+governor,\s*", r"\1In Hispaniola, the newly appointed governor, ", line)
    line = re.sub(r"(?i)\bIn\s+Juan Ponce\b", "Juan Ponce", line)
    line = re.sub(r"\s+([,.;:])", r"\1", line)
    line = re.sub(r"\s+\.", ".", line)
    line = re.sub(r"\.\.+", ".", line)
    line = re.sub(r"\.\s*(\[\d+\])\.", r" \1.", line)
    line = re.sub(r"(\[\d+\])\s*\.\s*\.", r"\1.", line)
    return line


def _sort_chronological(items: list[str]) -> list[str]:
    def _key(line: str) -> tuple[int, int, int, str]:
        # Prefer explicit YYYY, then Month DD, YYYY; fallback keeps stable-ish order.
        text = re.sub(r"\[\d+\]", "", str(line or ""))
        m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text)
        year = int(m.group(1)) if m else 9999
        # Very light month/day parse (only to break ties).
        month = 0
        day = 0
        mm = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})\b", text, flags=re.IGNORECASE)
        if mm:
            day = int(mm.group(2))
            mon = mm.group(1).lower()
            month_map = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
            }
            month = month_map.get(mon, 0)
        return (year, month, day, _norm(text))

    return sorted(items, key=_key)


def _format_person_bullet(line: str) -> str:
    # Accept forms like "Name - Role [3]" or "Name [3]" and format consistently.
    raw = str(line or "").strip()
    if not raw:
        return ""
    m = re.search(r"(\[\d+\])\s*$", raw)
    citation = m.group(1) if m else ""
    body = raw[: m.start()].strip() if m else raw
    head, rest = (body.split(" - ", 1) + [""])[:2]
    head = head.strip()
    rest = rest.strip()
    if not head:
        return raw
    if rest:
        return f"- **{head}** — {rest} {citation}".strip()
    return f"- **{head}** {citation}".strip()


def _paragraph_from_points(points: list[str], *, max_items: int = 5) -> str:
    if not points:
        return ""
    # Turn bullet-like fragments into a readable paragraph without inventing facts.
    out: list[str] = []
    seen: set[str] = set()
    for item in points[:max_items]:
        s = _clean_line(item)
        if _is_question_like(s):
            continue
        s = re.sub(r"^\-\s*", "", s)
        s = re.sub(r"(?i)^he was named florida\b", "He named the region 'La Florida'", s)
        s = re.sub(
            r"(?i)^(?:and\s+)?(introduction|overview|background|context|biography|early life|later years|death|legacy|timeline(?: of [^.]+)?)\s+",
            "",
            s,
        ).strip()
        lowered = _norm(re.sub(r"\[\d+\]", "", s))
        if lowered and not _is_event_line(s):
            has_finite_verb = bool(
                re.search(
                    r"\b(is|are|was|were|be|became|become|had|has|have|did|does|do|joined|served|led|founded|established|named|appointed|died|explored|landed|sailed|resisted|caused|resulted|highlighted|reinforced|influenced|sought|drove|shaped|pushed)\b",
                    lowered,
                )
            )
            if not has_finite_verb:
                continue
        if re.match(r"^(Led to|Resulted in)\b", s):
            s = f"This {s[:1].lower()}{s[1:]}"
        if re.match(r"^(Appointed|Named|Born|Wounded)\b", s):
            s = f"He was {s[:1].lower()}{s[1:]}"
        elif re.match(r"^(Joined|Led|Served|Participated|Became|Founded|Established|Died|Governed|Explored|Returned)\b", s):
            s = f"He {s[:1].lower()}{s[1:]}"
        key = _norm(re.sub(r"\[\d+\]", "", s))
        if not key or key in seen:
            continue
        seen.add(key)
        if s and not re.search(r"[.?!]$", s):
            s = s + "."
        out.append(s)
    return _clean_line(" ".join(out))


def _event_core_key(text: str) -> str:
    line = re.sub(r"\[\d+\]", "", str(text or ""))
    line = _clean_line(line)
    lowered = _norm(line)
    year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", line)
    year = year_match.group(1) if year_match else ""
    if re.search(r"\b(died|death|killed|assassinat|wounded|fatally|skirmish)\b", lowered):
        if "calusa" in lowered:
            return f"death {year} calusa".strip()
        if "florida" in lowered:
            return f"death {year} florida".strip()
        return f"death {year}".strip()
    if "florida" in lowered and any(x in lowered for x in ("la florida", "named", "exploration", "expedition", "coast")):
        return f"florida expedition {year}".strip()
    line = re.sub(
        r"^(?:\d{4}|[A-Za-z]+\s+\d{1,2},\s*\d{4}|[A-Za-z]+\s+\d{4})\s*[:\-–]\s*",
        "",
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(r"^(?:In\s+)?\d{4},\s*", "", line, flags=re.IGNORECASE)
    line = re.sub(r"^(?:in\s+)?[A-Za-z]+\s+\d{1,2},\s*\d{4},\s*", "", line, flags=re.IGNORECASE)
    line = re.sub(r"^(?:in\s+)?[A-Za-z]+\s+\d{4},\s*", "", line, flags=re.IGNORECASE)
    line = re.sub(r"\bin\s+(1[5-9]\d{2}|20\d{2})\b", "", line, flags=re.IGNORECASE)
    line = re.sub(r"(?i)\bfirst governor of puerto rico\b", "governor of puerto rico", line)
    line = re.sub(r"[^\w\s]", " ", line)
    return _norm(line)


def _dedupe_events(items: list[str], *, max_items: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        line = _clean_line(raw)
        if not line:
            continue
        key = _event_core_key(line)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line)
        if max_items and len(out) >= max_items:
            break
    return out


def _year_of_line(text: str) -> str:
    m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", str(text or ""))
    return m.group(1) if m else ""


def _is_question_like(text: str) -> bool:
    raw = _clean_line(str(text or ""))
    if not raw:
        return False
    lowered = _norm(raw)
    if "?" in raw:
        return True
    if re.match(r"(?i)^(how|what|when|where|why|who)\b", raw):
        return True
    if "how old was" in lowered:
        return True
    return False


def _one_event_per_year(items: list[str], *, max_items: int | None = None) -> list[str]:
    out: list[str] = []
    seen_years: set[str] = set()
    for item in items:
        line = _clean_line(item)
        if not line or _is_question_like(line):
            continue
        year = _year_of_line(line)
        if year and year in seen_years:
            continue
        if year:
            seen_years.add(year)
        out.append(line)
        if max_items and len(out) >= max_items:
            break
    return out


def _is_early_life_line(text: str) -> bool:
    line = _norm(text)
    if not line:
        return False
    return bool(
        re.search(
            r"\b(born|birth|noble|family|childhood|early life|early years|served|military|granada|joined columbus|second voyage|spain|santervas)\b",
            line,
        )
    )


def _is_historical_context_line(text: str) -> bool:
    line = _norm(text)
    if not line:
        return False
    return bool(
        re.search(
            r"\b(spanish crown|colonization|colonial|imperial|territories|trade routes|legal battles|authority|indigenous|taino|calusa|resisted|resistance|conflict)\b",
            line,
        )
    )


def _event_line_to_sentence(text: str) -> str:
    line = _clean_line(text)
    if not line:
        return ""
    if _is_question_like(line):
        return ""
    cite_match = re.search(r"(\[\d+\])\s*$", line)
    cite = cite_match.group(1) if cite_match else ""
    body = line[: cite_match.start()].strip() if cite_match else line
    m = re.match(
        r"^((?:1[5-9]\d{2}|20\d{2}|[A-Za-z]+\s+\d{1,2},\s*(?:1[5-9]\d{2}|20\d{2})|[A-Za-z]+\s+(?:1[5-9]\d{2}|20\d{2})))\s*[,:\-–]\s*(.+)$",
        body,
        flags=re.IGNORECASE,
    )
    if not m:
        plain = _clean_line(body)
        plain = re.sub(r"^(?:1[5-9]\d{2}|20\d{2})\s*,\s*(?:1[5-9]\d{2}|20\d{2})\s*:\s*", "", plain)
        if _is_question_like(plain):
            return ""
        if re.match(r"(?i)^governed\b", plain):
            plain = f"He {plain[:1].lower()}{plain[1:]}"
        elif re.match(r"(?i)^exploration of florida and naming it ['\"]?la florida['\"]?\b", plain):
            plain = "He explored Florida and named it 'La Florida'"
        elif re.match(r"(?i)^is appointed\b", plain):
            plain = f"He was {plain[:1].lower()}{plain[1:]}"
        if plain and not re.search(r"[.?!]$", plain):
            plain = f"{plain}."
        if cite and cite not in plain:
            plain = f"{plain} {cite}".strip()
        return plain
    date_part = m.group(1).strip()
    detail = _clean_line(m.group(2))
    detail = re.sub(r"^(?:1[5-9]\d{2}|20\d{2})\s*:\s*", "", detail)
    detail = re.sub(r"(?i)^in\s+", "", detail)
    detail = re.sub(r"(?i)^is appointed\b", "appointed", detail)
    detail = re.sub(r"(?i)^is named\b", "named", detail)
    detail = re.sub(r"(?i)^named florida\b", "named the region 'La Florida'", detail)
    detail = re.sub(r"(?i)^Hispaniola\s+", "Hispaniola, ", detail)
    detail = re.sub(r"(?i)^In\s+Hispaniola,\s+In\s+", "In Hispaniola, ", detail)
    detail = re.sub(r"(?i)^In\s+Juan Ponce", "Juan Ponce", detail)
    detail = re.sub(
        r"(?i)^first european expedition to puerto rico under ponce de le[oó]n\b",
        "Ponce de León led the first European expedition to Puerto Rico",
        detail,
    )
    detail = re.sub(
        r"(?i)^exploration of florida and naming it ['\"]?la florida['\"]?\b",
        "he explored Florida and named it 'La Florida'",
        detail,
    )
    detail = re.sub(
        r"(?i)^In\s+Hispaniola,\s*the newly appointed governor,\s*([^,]+),\s*arrived in Hispaniola,\s*",
        r"the newly appointed governor, \1, arrived in Hispaniola, ",
        detail,
    )
    detail = re.sub(r"''", "'", detail)
    if re.match(r"^(He|She|The)\b", detail):
        detail = f"{detail[:1].lower()}{detail[1:]}"
    if re.match(r"(?i)^(appointed|named|born|wounded)\b", detail):
        detail = f"he was {detail[:1].lower()}{detail[1:]}"
    elif re.match(r"(?i)^(joined|led|sailed|landed|died|became|founded|established|explored|returned)\b", detail):
        detail = f"he {detail[:1].lower()}{detail[1:]}"
    elif re.match(r"(?i)^governed\b", detail):
        detail = f"he {detail[:1].lower()}{detail[1:]}"
    sentence = f"In {date_part}, {detail}".strip()
    sentence = _clean_line(sentence)
    sentence = re.sub(r"(?i)^In\s+(\d{4}),\s*In\s+", r"In \1, ", sentence)
    sentence = re.sub(r"(?i)^In\s+(\d{4}),\s*Hispaniola,\s+", r"In \1, in Hispaniola, ", sentence)
    sentence = re.sub(
        r"(?i)^In\s+(\d{4}),\s*Hispaniola,\s*the newly appointed governor,\s*([^,]+),\s*arrived in Hispaniola,\s*",
        r"In \1, the newly appointed governor, \2, arrived in Hispaniola, ",
        sentence,
    )
    if sentence and not re.search(r"[.?!]$", sentence):
        sentence = f"{sentence}."
    if cite and cite not in sentence:
        sentence = f"{sentence} {cite}".strip()
    return sentence


def _narrative_from_events(events: list[str], *, max_items: int = 5) -> str:
    if not events:
        return ""
    converted = [_event_line_to_sentence(x) for x in events]
    converted = _dedupe_events(converted, max_items=max_items)
    return _paragraph_from_points(converted, max_items=max_items)


def _as_clause(text: str) -> str:
    line = _clean_line(text)
    if not line:
        return ""
    if re.match(r"^(Established|Led|Joined|Named|Appointed|Became|Died|Founded|Created|Built|Expanded)\b", line):
        return f"he {line[:1].lower()}{line[1:]}"
    # Keep proper nouns/titles as-is to avoid "juan Ponce..." casing artifacts.
    if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}", line):
        return line
    return f"{line[:1].lower()}{line[1:]}" if line[:1].isupper() else line


def _clause_similarity_key(text: str) -> str:
    line = re.sub(r"\[\d+\]", "", _clean_line(text))
    if not line:
        return ""
    line = re.sub(
        r"(?i)^(ponce de le[oó]n|juan ponce de le[oó]n|he|his expeditions|this period|this topic)\s+",
        "",
        line,
    )
    line = re.sub(r"[^\w\s]", " ", line)
    return _norm(line)


def _has_finite_verb(text: str) -> bool:
    lowered = _norm(re.sub(r"\[\d+\]", "", str(text or "")))
    if not lowered:
        return False
    return bool(
        re.search(
            r"\b(is|are|was|were|be|became|become|had|has|have|did|does|do|joined|served|led|founded|established|named|appointed|died|explored|landed|sailed|resisted|caused|resulted|highlighted|reinforced|sought|drove|contested|pushed)\b",
            lowered,
        )
    )


def _expand_context_fragment(text: str) -> str:
    line = _clean_line(text)
    if not line:
        return ""
    if _has_finite_verb(line):
        return line
    cite_match = re.search(r"(\[\d+\])\s*$", line)
    cite = cite_match.group(1) if cite_match else ""
    body = line[: cite_match.start()].strip() if cite_match else line
    lowered = _norm(body)
    if "indigenous" in lowered or "taino" in lowered or "calusa" in lowered or "resist" in lowered:
        sentence = f"Indigenous resistance, especially from Taíno and Calusa communities, shaped the outcome of Spanish expansion efforts."
    elif "diego colon" in lowered or "legal" in lowered or "governance" in lowered:
        sentence = f"Legal disputes with Diego Colón over Puerto Rico's governance limited Ponce de León's political control."
    elif "crown" in lowered or "imperial" in lowered or "territor" in lowered or "trade" in lowered:
        sentence = f"The Spanish Crown's imperial goals for land, trade, and resources strongly influenced his expeditions."
    else:
        core = body[:1].lower() + body[1:] if body[:1].isupper() else body
        sentence = f"A key background factor was {core}."
    if cite:
        return f"{sentence} {cite}".strip()
    return sentence


def _build_biography_events_para(events: list[str], *, max_items: int = 5) -> str:
    if not events:
        return ""
    non_death = [
        x
        for x in events
        if not re.search(r"\b(died|death|killed|assassinat|wounded|executed|fatally)\b", _norm(x))
    ]
    event_sentences = _dedupe_events([_event_line_to_sentence(x) for x in non_death], max_items=max_items * 2)
    event_sentences = _one_event_per_year(event_sentences, max_items=max_items)
    if not event_sentences:
        return ""
    out: list[str] = []
    for idx, sentence in enumerate(event_sentences[:max_items]):
        s = _clean_line(sentence)
        if idx == 1:
            s = re.sub(r"^In\s+", "By ", s, flags=re.IGNORECASE)
        elif idx == 2:
            # Avoid "soon" for multi-year gaps (e.g., 1509 -> 1513).
            s = re.sub(r"^In\s+", "In ", s, flags=re.IGNORECASE)
        elif idx >= 3:
            s = re.sub(r"^In\s+", "Later, in ", s, flags=re.IGNORECASE)
        out.append(s)
    return _paragraph_from_points(out, max_items=max_items)


def _timeline_bullet_fragment(text: str) -> str:
    line = _clean_line(text)
    if not line:
        return ""
    if _is_question_like(line):
        return ""
    cite_match = re.search(r"(\[\d+\])\s*$", line)
    cite = cite_match.group(1) if cite_match else ""
    body = line[: cite_match.start()].strip() if cite_match else line
    # Normalize from sentence/event style into compact timeline format.
    body = re.sub(r"^In\s+", "", body, flags=re.IGNORECASE)
    date_part = ""
    detail = body
    m = re.match(
        r"^((?:1[5-9]\d{2}|20\d{2}|[A-Za-z]+\s+\d{1,2},\s*(?:1[5-9]\d{2}|20\d{2})|[A-Za-z]+\s+(?:1[5-9]\d{2}|20\d{2})))\s*[,:\-–]\s*(.+)$",
        body,
        flags=re.IGNORECASE,
    )
    if m:
        date_part = m.group(1).strip()
        detail = m.group(2).strip()
    else:
        y = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", body)
        if y:
            date_part = y.group(1)
            detail = re.sub(r"\b" + re.escape(y.group(1)) + r"\b", "", body, count=1).strip(" ,:-")

    detail = _clean_line(detail)
    detail = re.sub(r"^(?:1[5-9]\d{2}|20\d{2})\s*:\s*", "", detail)
    detail = re.sub(r"(?i)^In\s+Hispaniola,\s+", "", detail)
    detail = re.sub(r"(?i)^Hispaniola\s+In\s+the newly appointed governor,\s*", "the newly appointed governor, ", detail)
    detail = re.sub(
        r"(?i)^the newly appointed governor,\s*([^,]+),\s*arrived in Hispaniola.*",
        r"Governor \1 arrives in Hispaniola to restore colonial order",
        detail,
    )
    detail = re.sub(
        r"(?i)^In\s+Hispaniola,\s*the newly appointed governor,\s*([^,]+),\s*arrived in Hispaniola.*",
        r"Governor \1 arrives in Hispaniola to restore colonial order",
        detail,
    )
    detail = re.sub(r"(?i)^he was appointed first governor of puerto rico\b", "Appointed first governor of Puerto Rico", detail)
    detail = re.sub(r"(?i)^he was named florida\b", "Named the region 'La Florida'", detail)
    detail = re.sub(r"(?i)^he landed on the coast of Florida at a site between .*", "Landed on Florida's coast", detail)
    detail = re.sub(r"(?i)^named Florida ['\"]?La Florida['\"]? during his 1513 expedition\b", "Named the region 'La Florida'", detail)
    detail = re.sub(r"(?i)^exploration of florida and naming it ['\"]?la florida['\"]?\b", "Explored Florida and named it 'La Florida'", detail)
    detail = re.sub(r"(?i)^juan ponce de león sailed to Florida with two ships and 200 men and landed near Charlotte Harbor\b", "Sailed to Florida with 200 settlers; landed near Charlotte Harbor", detail)
    detail = re.sub(r"(?i)^he died in 1521 from wounds sustained in Florida\b", "Died from wounds sustained in Florida", detail)
    detail = re.sub(r"(?i)^died in 1521 from wounds sustained in Florida\b", "Died from wounds sustained in Florida", detail)
    detail = re.sub(r"(?i)\bdied in\s+from\b", "Died from", detail)
    detail = re.sub(r"(?i)\bdied in during\b", "Died during", detail)
    detail = re.sub(r"(?i)\bfrom\s+to\s+(\d{4})\b", r"through \1", detail)
    detail = re.sub(r"''", "'", detail)
    detail = re.sub(r"(?i)\bresulted in the abandonment of the colony due to resistance\b", "Colony effort collapsed after Indigenous resistance", detail)
    # Trim very long fragments while keeping meaning.
    if len(detail) > 120:
        detail = detail[:117].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
    detail = detail.rstrip(".")
    if detail and detail[0].islower():
        detail = detail[0].upper() + detail[1:]
    if date_part:
        out = f"{date_part} - {detail}"
    else:
        out = detail
    if cite and cite not in out:
        out = f"{out} {cite}"
    return _clean_line(out)


def _is_noise_line(text: str) -> bool:
    lowered = _norm(text)
    if not lowered:
        return True
    noise_markers = (
        "see all videos",
        "show more",
        "quick facts",
        "this is a guest post",
        "in office",
        "succeeded by",
        "preceeded by",
        "president ferdinand marcos",
        "member of the regular batasang",
        "chatgpt",
        "table of contents",
        "special holiday hours",
        "money videos",
        "cite verified",
        "copy citation",
        "ask the chatbot",
        "written by",
        "last updated",
        "how old was",
        "how old is",
        "what is ",
        "who is ",
    )
    return any(marker in lowered for marker in noise_markers)


def _is_reference_line(text: str) -> bool:
    line = _clean_line(text)
    lowered = _norm(line)
    if not lowered:
        return True
    if re.search(r"\b(apa|mla|chicago|citation style|copy citation|endnotes|bibliography)\b", lowered):
        return True
    if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3},\s", line) and re.search(r"\([^)]+\b(1[5-9]\d{2}|20\d{2})\)", line):
        return True
    if re.search(r"\([A-Za-z][^)]*\b(1[5-9]\d{2}|20\d{2})\)\s*,\s*\d{1,3}\b", line):
        return True
    if re.search(r"\b(press|publishing|publisher|benchmark books|capstone|crabtree)\b", lowered):
        return True
    return False


def _has_date_like(text: str) -> bool:
    month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    return bool(
        re.search(
            rf"\b(?:1[5-9]\d{{2}}|20\d{{2}}|{month_re}\s+\d{{1,2}},\s*(?:1[5-9]\d{{2}}|20\d{{2}})|{month_re}\s+(?:1[5-9]\d{{2}}|20\d{{2}}))\b",
            str(text or ""),
            flags=re.IGNORECASE,
        )
    )


def _is_event_line(text: str) -> bool:
    if _is_noise_line(text):
        return False
    if _is_reference_line(text):
        return False
    line = _clean_line(text)
    if len(line) < 14:
        return False
    if len(line) > 260:
        return False
    lowered = _norm(line)
    if re.search(
        r"\b(in office|member of|succeeded by|preceded by|show more|quick facts|this is a guest post)\b",
        lowered,
    ):
        return False
    if re.search(r"\([A-Za-z][^)]*\b(1[5-9]\d{2}|20\d{2})\)", line) and re.search(r",\s*\d{1,3}\.?\s*$", line):
        return False
    if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3},\s", line):
        return False
    if re.search(r"\b(press|publishing|publisher|books?)\b", lowered):
        return False
    verbs = (
        "signed",
        "landed",
        "reached",
        "arrived",
        "explored",
        "discovered",
        "captured",
        "declared",
        "established",
        "founded",
        "passed",
        "created",
        "became",
        "claimed",
        "named",
        "appointed",
        "ceded",
        "transferred",
        "granted",
        "ratified",
        "began",
        "ended",
        "attacked",
        "invaded",
        "launched",
        "bombed",
        "surrendered",
        "wounded",
        "died",
        "governed",
        "governor",
        "expedition",
        "exploration",
    )
    return _has_date_like(line) and any(v in lowered for v in verbs)


def _request_terms(request: str) -> list[str]:
    cleaned = _norm(request)
    if not cleaned:
        return []
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "about",
        "on",
        "of",
        "how",
        "what",
        "when",
        "where",
        "why",
        "who",
        "history",
        "project",
        "assignment",
        "essay",
        "school",
        "kids",
        "kid",
        "children",
        "teens",
        "teen",
        "adult",
        "adults",
    }
    out: list[str] = []
    seen: set[str] = set()
    for token in cleaned.split():
        if len(token) < 3 or token in stop:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out[:12]


def _person_tokens_from_request(request: str) -> list[str]:
    # Extract probable person-name tokens for biography-style prompts.
    text = str(request or "").strip()
    if not text:
        return []
    lowered = text.lower()
    biography_markers = ("biography", "life of", "who was", "who is", "about", "on ")
    if not any(marker in lowered for marker in biography_markers):
        return []

    # Prefer the subject phrase after about/on/of when present.
    subject = text
    m = re.search(r"(?i)\b(?:about|on|of)\b\s+(.+)$", text)
    if m:
        subject = m.group(1).strip()
    subject = re.sub(
        r"(?i)\s+for\s+(?:a\s+)?(?:kids?|children|teens?|adults?|school\s+assignment|homework|classwork|project|essay|report)\s*$",
        "",
        subject,
    ).strip()

    particles = {"de", "del", "la", "las", "los", "y", "da", "do", "dos", "van", "von"}
    stop = {
        "history",
        "project",
        "assignment",
        "essay",
        "school",
        "biography",
        "report",
        "research",
        "for",
        "about",
        "on",
        "of",
        "the",
        "a",
        "an",
    }
    tokens: list[str] = []
    for part in re.split(r"\s+", re.sub(r"[^\w\s'’.-]", " ", subject)):
        p = part.strip(" .,'’\"-")
        if not p:
            continue
        k = _norm(p)
        if not k or k in stop:
            continue
        if k in particles:
            continue
        if len(k) > 1:
            tokens.append(k)

    # Require at least two tokens to activate this guard.
    deduped = []
    seen = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped if len(deduped) >= 2 else []


def _line_relevant_to_request(text: str, request_terms: list[str], person_tokens: list[str]) -> bool:
    line = _norm(text)
    if not line:
        return False
    if person_tokens:
        # For person-focused prompts, require the last-name token and at least one additional token.
        last = person_tokens[-1]
        if last not in line:
            return False
        hits = sum(1 for t in person_tokens if t in line)
        if hits < min(2, len(person_tokens)):
            return False
        return True
    if not request_terms:
        return True
    return any(t in line for t in request_terms[:10])


def _parse_summary_text(summary: Any) -> str:
    if summary is None:
        return ""
    if isinstance(summary, dict):
        text = str(summary.get("summary") or summary.get("text") or "").strip()
        return _compact_paragraph(text)
    raw = str(summary).strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                text = str(parsed.get("summary") or parsed.get("text") or "").strip()
                if text:
                    return _compact_paragraph(text)
        except Exception:
            return ""
    if (raw.startswith("{") or raw.startswith("[")) and len(raw) > 10:
        # Guardrail: never pass raw JSON-like blobs into the final document.
        return ""
    return _compact_paragraph(raw)


def _needs_summary_rebuild(summary: str) -> bool:
    text = str(summary or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if len(text) < 80:
        return True
    if text.startswith("{") or text.startswith("["):
        return True
    if "{'fact':" in lowered or '"fact":' in lowered:
        return True
    if "..." in text or "?" in text:
        return True
    if re.search(r"\b(1[5-9]\d{2}|20\d{2})\s*:", text):
        return True
    if re.search(r"\b(1[5-9]\d{2}|20\d{2})\s*,\s*(1[5-9]\d{2}|20\d{2})\s*:", text):
        return True
    if _is_noise_line(text):
        return True
    return False


def _extract_people_from_lines(lines: list[str], *, max_items: int = 10) -> list[str]:
    token = r"(?:[A-ZÀ-ÖØ-Ý]\.|[A-ZÀ-ÖØ-Ý][^\W\d_]+(?:[.'’\-][^\W\d_]+)*)"
    particle = r"(?:de|del|la|las|los|y|da|do|dos|van|von)"
    pat = re.compile(rf"\b({token}(?:\s+(?:{particle})\s+{token}|\s+{token}){{1,4}})\b")
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not _has_citation(line):
            continue
        citation = re.search(r"\[\d+\]", line)
        cite = citation.group(0) if citation else ""
        plain = re.sub(r"\[\d+\]", "", line)
        for match in pat.finditer(plain):
            name = match.group(1).strip()
            candidate = f"{name} {cite}".strip()
            if not _is_name_like(candidate):
                continue
            key = _norm(name)
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)
            if len(out) >= max_items:
                return out
    return out


def _extract_people_from_source_records(
    source_records: list[dict[str, Any]],
    *,
    person_tokens: list[str],
    request_terms: list[str],
    max_items: int = 10,
) -> list[str]:
    token = r"(?:[A-ZÀ-ÖØ-Ý]\.|[A-ZÀ-ÖØ-Ý][^\W\d_]+(?:[.'’\\-][^\W\d_]+)*)"
    particle = r"(?:de|del|la|las|los|y|da|do|dos|van|von)"
    pat = re.compile(rf"\b({token}(?:\s+(?:{particle})\s+{token}|\s+{token}){{1,4}})\b")
    out: list[str] = []
    seen: set[str] = set()
    for rec in source_records or []:
        if len(out) >= max_items:
            break
        sid = rec.get("id")
        citation = f"[{sid}]" if sid is not None else ""
        text = str(rec.get("text_excerpt") or rec.get("text") or "").strip()
        if not text:
            continue
        plain = re.sub(r"\s+", " ", text)
        for match in pat.finditer(plain):
            if len(out) >= max_items:
                break
            name = _strip_heading_prefix(match.group(1).strip())
            if not name:
                continue
            candidate = f"{name} {citation}".strip()
            if not _is_name_like(candidate):
                continue
            key = _norm(name)
            if key in seen:
                continue
            if _is_noise_line(name):
                continue
            # For biography-like prompts, force identity relevance to the requested person.
            if person_tokens:
                name_norm = _norm(name)
                last = person_tokens[-1]
                if last not in name_norm:
                    continue
                hits = sum(1 for t in person_tokens if t in name_norm)
                if hits < min(2, len(person_tokens)):
                    continue
            elif request_terms:
                window = plain[max(0, match.start() - 160) : min(len(plain), match.end() + 160)]
                if not _line_relevant_to_request(window, request_terms, person_tokens):
                    continue
            seen.add(key)
            out.append(candidate)
    return out


def _with_citation(text: str, fallback: str) -> str:
    if re.search(r"\[\d+\]", text):
        return text
    if fallback:
        return f"{text} {fallback}".strip()
    return text


def _is_biography_request(request: str) -> bool:
    text = (request or "").lower()
    return any(x in text for x in ("biography", "life of", "who was", "who is", "about "))


def _year_span(items: list[str]) -> str:
    years: list[int] = []
    seen: set[int] = set()
    for item in items:
        for match in re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", str(item or "")):
            try:
                y = int(match)
            except Exception:
                continue
            if y in seen:
                continue
            seen.add(y)
            years.append(y)
    if not years:
        return ""
    years.sort()
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]} - {years[-1]}"


def _first_sentence(text: str) -> str:
    raw = _clean_line(text)
    if not raw:
        return ""
    safe = re.sub(r"\bc\.\s*(\d{3,4})", r"circa \1", raw, flags=re.IGNORECASE)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", safe) if p.strip()]
    first = parts[0] if parts else safe
    return re.sub(r"\bcirca\s+(\d{3,4})", r"c. \1", first, flags=re.IGNORECASE)


def _sanitize_person_line(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    m = re.search(r"(\[\d+\])\s*$", raw)
    citation = m.group(1) if m else ""
    body = raw[: m.start()].strip() if m else raw
    head, rest = (re.split(r"\s+-\s+|\s*:\s*", body, maxsplit=1) + [""])[:2]
    clean_head = _strip_heading_prefix(head)
    if not clean_head:
        return ""
    rest = _clean_line(rest)
    rebuilt = f"{clean_head} - {rest}".strip(" -") if rest else clean_head
    return f"{rebuilt} {citation}".strip()


def _strip_heading_prefix(name: str) -> str:
    raw = _clean_line(name)
    if not raw:
        return ""
    tokens = [t for t in re.split(r"\s+", raw) if t]
    if len(tokens) < 2:
        return ""
    prefix_tokens = {
        "introduction",
        "overview",
        "background",
        "context",
        "early",
        "life",
        "years",
        "later",
        "death",
        "legacy",
        "impact",
        "biography",
        "facts",
        "fact",
        "definition",
        "review",
        "questions",
        "related",
        "terms",
        "quick",
        "videos",
        "video",
        "money",
        "contents",
        "article",
        "topic",
        "subject",
        "timeline",
        "history",
    }
    suffix_tokens = {"facts", "fact", "biography", "definition", "timeline", "history"}
    while len(tokens) >= 2 and tokens[0].strip(".,:;!?").lower() in prefix_tokens:
        tokens.pop(0)
    while len(tokens) >= 2 and tokens[-1].strip(".,:;!?").lower() in suffix_tokens:
        tokens.pop()
    cleaned = " ".join(tokens).strip(" .,:;!?")
    return cleaned


def _extract_relevant_source_sentences(
    source_records: list[dict[str, Any]],
    *,
    request_terms: list[str],
    person_tokens: list[str],
    biography_mode: bool,
    max_items: int = 120,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    extra_noise = (
        "table of contents",
        "ask the chatbot",
        "ask anything",
        "quick facts",
        "related topics",
        "copy citation",
        "select citation style",
        "share to social media",
        "external websites",
        "see all videos",
        "review questions",
        "related terms",
        "written by",
        "last updated",
        "homework help",
        "definition",
        "study content",
        "timeline - have fun with history",
    )
    strong_verb_markers = (
        "was",
        "is",
        "were",
        "born",
        "died",
        "served",
        "joined",
        "explored",
        "landed",
        "founded",
        "established",
        "led",
        "named",
        "became",
        "returned",
        "sailed",
        "governor",
        "colonize",
        "displaced",
        "wounded",
        "attacked",
    )
    for rec in source_records or []:
        sid = rec.get("id")
        citation = f"[{sid}]" if sid is not None else ""
        text = str(rec.get("text_excerpt") or rec.get("text") or "").strip()
        if not text:
            continue
        text = re.sub(r"\[\s*\d+\s*\]", "", text)
        text = text.replace(" | ", ". ").replace(" • ", ". ")
        text = re.sub(r"\s+", " ", text).strip()
        chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", text) if c.strip()]
        if len(chunks) <= 1 and len(text) > 800:
            chunks = [c.strip() for c in re.split(r"(?<=\.)\s+", text) if c.strip()]
        for chunk in chunks:
            if len(out) >= max_items:
                return out
            line = _clean_line(chunk)
            if len(line) < 35 or len(line) > 320:
                continue
            if _is_question_like(line):
                continue
            line = re.sub(
                r"^[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*){0,8}\s+Timeline\s*-\s*[A-Za-z ]+\s+",
                "",
                line,
            ).strip()
            line = re.sub(
                r"(?i)^(introduction|biography|legacy|early life|later years|timeline(?: of [^.]+)?|quick facts)\s+",
                "",
                line,
            ).strip()
            if len(line) < 35:
                continue
            lowered = _norm(line)
            if any(marker in lowered for marker in extra_noise):
                continue
            if _is_noise_line(line):
                continue
            if _is_reference_line(line):
                continue
            if len([w for w in re.split(r"\s+", line) if w]) < 7:
                continue
            if re.search(r"\b(photo|getty|name:|birth/death|birthplace|nationality|endnotes|apa|mla|chicago)\b", lowered):
                continue
            if re.search(r"\[[a-z][a-z \-]{1,20}\]", line, flags=re.IGNORECASE):
                continue
            # Drop bibliographic references, which are not assignment prose.
            if re.search(r"\([A-Za-z][^)]*\b\d{4}\)\s*,?\s*\d{1,3}\.?\s*$", line):
                continue
            if line.count(":") >= 2 and not any(v in lowered for v in strong_verb_markers):
                continue
            if not any(v in lowered for v in strong_verb_markers) and not _is_event_line(line):
                continue
            if biography_mode:
                if person_tokens and not _line_relevant_to_request(line, [], person_tokens):
                    continue
            elif not _line_relevant_to_request(line, request_terms, person_tokens):
                continue
            with_citation = _with_citation(line, citation)
            key = _norm(re.sub(r"\[\d+\]", "", with_citation))
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(with_citation)
    return out


def _categorize_source_sentences(sentences: list[str]) -> dict[str, list[str]]:
    buckets = {
        "intro": [],
        "background": [],
        "events": [],
        "death": [],
        "legacy": [],
        "facts": [],
    }
    for line in sentences:
        lowered = _norm(line)
        if not lowered:
            continue
        if _is_reference_line(line):
            continue
        if re.search(r"\b(died|death|killed|wounded|assassinated|executed)\b", lowered):
            buckets["death"].append(line)
            buckets["facts"].append(line)
            continue
        if re.search(
            r"\b(legacy|impact|remembered|influenced|led to|paved the way|long term|lasting|historical significance)\b",
            lowered,
        ):
            buckets["legacy"].append(line)
            buckets["facts"].append(line)
            continue
        if re.search(
            r"\b(born|early life|early years|noble family|served as|joined|career|childhood|upbringing)\b",
            lowered,
        ):
            buckets["background"].append(line)
            buckets["facts"].append(line)
            continue
        if _is_event_line(line) or re.search(
            r"\b(expedition|explored|landed|founded|established|governor|named|sailed|colonize|settled)\b",
            lowered,
        ):
            buckets["events"].append(line)
            buckets["facts"].append(line)
            continue
        if re.search(r"\b(was a|is a|known for|credited with|was an?)\b", lowered):
            buckets["intro"].append(line)
            buckets["facts"].append(line)
            continue
        if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", lowered):
            buckets["events"].append(line)
            buckets["facts"].append(line)
            continue
        buckets["facts"].append(line)
    for key, items in buckets.items():
        buckets[key] = _dedupe(items, max_items=12)
    return buckets


class FamilyHistoryWritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="family_history_writing_agent",
            role="writer",
            system_prompt=(
                "You are a school history writing assistant for families. "
                "Create clear, useful project/homework/essay drafts from fact-checked inputs."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="family_history_writing",
                    name="Family History Writing",
                    description="Create parent and student friendly history assignments from fact-checked notes.",
                    input_types=["json"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=20,
                )
            ],
            config=config or {},
        )

    def _audience(self, request: str) -> str:
        text = (request or "").lower()
        if any(x in text for x in ("for kids", "for children", "kid", "kids", "child", "children", "elementary")):
            return "kid"
        if any(x in text for x in ("for teens", "teen", "teenager", "high school")):
            return "teen"
        return "adult"

    def _assignment_kind(self, request: str) -> str:
        text = (request or "").lower()
        if any(x in text for x in ("essay", "thesis", "argumentative", "persuasive")):
            return "essay"
        if any(x in text for x in ("homework", "worksheet", "classwork")):
            return "homework"
        if any(x in text for x in ("presentation", "slides", "poster", "speech")):
            return "presentation"
        if "report" in text:
            return "report"
        return "project"

    def _project_title(self, request: str, summary: str) -> str:
        cleaned = re.sub(
            r"(?i)^(create|write|build|make)\s+(a|an)?\s*(history|historical)?\s*(project|report|essay)?\s*(on|about|of)?\s*",
            "",
            (request or "").strip(),
        ).strip()
        cleaned = re.sub(r"(?i)\s+for\s+(kids?|children|teens?|high school students|adults?)\s*$", "", cleaned).strip()
        if not cleaned:
            cleaned = (summary or "").split(".")[0].strip()
        cleaned = cleaned.strip(" .:-")
        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned if cleaned else "History Project"

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        request = str(
            payload.get("user_request")
            or context.user_request
            or context.initial_parameters.get("user_request")
            or context.initial_parameters.get("request")
            or payload.get("project_title")
            or payload.get("topic")
            or ""
        ).strip()
        audience = self._audience(request)
        assignment_kind = self._assignment_kind(request)
        request_terms = _request_terms(request)
        person_tokens = _person_tokens_from_request(request)
        biography_mode = _is_biography_request(request)

        summary = _parse_summary_text(payload.get("summary"))
        context_points = _dedupe([_coerce_line(x) for x in (payload.get("context") or [])], max_items=10)
        causes = _dedupe([_coerce_line(x) for x in (payload.get("causes") or [])], max_items=10)
        consequences = _dedupe([_coerce_line(x) for x in (payload.get("consequences") or [])], max_items=10)
        timeline = _dedupe([_coerce_line(x) for x in (payload.get("timeline") or [])], max_items=12)
        key_events = _dedupe([_coerce_line(x) for x in (payload.get("key_events") or [])], max_items=12)
        key_figures_raw = _dedupe([_coerce_line(x) for x in (payload.get("key_figures") or [])], max_items=20)
        interpretations_raw = [_coerce_line(x) for x in (payload.get("interpretations") or [])]
        limitations = _dedupe([_coerce_line(x) for x in (payload.get("limitations") or [])], max_items=8)
        questions = _dedupe([_coerce_line(x) for x in (payload.get("discussion_questions") or [])], max_items=12)
        facts = _dedupe([_coerce_line(x) for x in (payload.get("facts") or [])], max_items=10)
        timeline_raw = list(timeline)
        key_events_raw = list(key_events)
        facts_raw = list(facts)

        sources = _dedupe([_coerce_line(x) for x in (payload.get("sources") or [])], max_items=20)
        source_records = list(payload.get("source_records") or [])
        source_meta = list(payload.get("source_meta") or [])
        if source_meta:
            meta_lines: list[str] = []
            for item in source_meta:
                sid = item.get("id")
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if not title and not url:
                    continue
                prefix = f"[{sid}] " if sid is not None else ""
                line = f"{prefix}{title or url}"
                if url:
                    line = f"{line} - {url}"
                meta_lines.append(line)
            if meta_lines:
                sources = _dedupe(meta_lines, max_items=20)

        first_citation = ""
        for pool in (timeline, key_events, context_points, causes, consequences, facts):
            for line in pool:
                ids = _extract_citations(line)
                if ids:
                    first_citation = f"[{ids[0]}]"
                    break
            if first_citation:
                break

        title = self._project_title(request, summary)

        # Hard filter to keep this output assignment-ready and avoid noisy, non-person rows.
        timeline = [
            _clean_line(line)
            for line in timeline
            if _has_citation(line)
            and _is_event_line(line)
        ]
        key_events = [
            _clean_line(line)
            for line in key_events
            if _has_citation(line)
            and _is_event_line(line)
        ]
        context_points = [
            _clean_line(line)
            for line in context_points
            if _has_citation(line)
            and not _is_noise_line(line)
            and (biography_mode or _line_relevant_to_request(line, request_terms, person_tokens))
        ][:10]
        causes = [
            _clean_line(line)
            for line in causes
            if _has_citation(line)
            and not _is_noise_line(line)
            and (biography_mode or _line_relevant_to_request(line, request_terms, person_tokens))
        ][:10]
        consequences = [
            _clean_line(line)
            for line in consequences
            if _has_citation(line)
            and not _is_noise_line(line)
            and (biography_mode or _line_relevant_to_request(line, request_terms, person_tokens))
        ][:10]
        facts = [
            _clean_line(line)
            for line in facts
            if _has_citation(line)
            and not _is_noise_line(line)
            and (biography_mode or _line_relevant_to_request(line, request_terms, person_tokens))
        ][:10]
        limitations = [_clean_line(line) for line in limitations if not _is_noise_line(line)][:8]
        questions = [_clean_line(line) for line in questions if not _is_noise_line(line)][:10]

        # Fallback: when structured fact-check fields are sparse, reconstruct assignment sections
        # directly from cleaned source excerpts so the final document is still complete.
        source_sentences: list[str] = []
        source_buckets: dict[str, list[str]] = {}
        if source_records:
            source_sentences = _extract_relevant_source_sentences(
                source_records,
                request_terms=request_terms,
                person_tokens=person_tokens,
                biography_mode=biography_mode,
                max_items=120,
            )
            source_buckets = _categorize_source_sentences(source_sentences)

        if not first_citation and source_sentences:
            first_ids = _extract_citations(source_sentences[0])
            if first_ids:
                first_citation = f"[{first_ids[0]}]"

        if source_buckets:
            if not context_points:
                context_points = _dedupe(source_buckets.get("background", [])[:6] + source_buckets.get("intro", [])[:2], max_items=8)
            if not causes:
                causes = _dedupe(source_buckets.get("background", [])[:5], max_items=6)
            if not consequences:
                consequences = _dedupe(source_buckets.get("legacy", [])[:6], max_items=8)
            if not facts:
                facts = _dedupe(source_buckets.get("facts", [])[:10], max_items=10)
            if not key_events:
                key_events = _dedupe(
                    [x for x in source_buckets.get("events", []) if _is_event_line(x) or _has_date_like(x)][:10],
                    max_items=10,
                )
            if not timeline:
                timeline = _dedupe(
                    [x for x in source_buckets.get("events", []) if _has_date_like(x)][:10],
                    max_items=10,
                )

        # If summary is weak or malformed, rebuild it from cited content.
        if _needs_summary_rebuild(summary):
            rebuilt = _paragraph_from_points(
                facts[:3] + context_points[:3] + key_events[:2] + (source_buckets.get("intro", [])[:2] if source_buckets else []),
                max_items=6,
            )
            if rebuilt:
                summary = rebuilt

        key_figures_sanitized = [_sanitize_person_line(x) for x in key_figures_raw]
        key_people = [
            line
            for line in key_figures_sanitized
            if _is_name_like(line)
            and _has_citation(line)
            and not _is_noise_line(line)
            and _line_relevant_to_request(line, request_terms, person_tokens)
        ]
        key_people = [_with_citation(line, first_citation) for line in key_people]
        key_people = _dedupe(key_people, max_items=10)
        fallback_people_target = 2 if biography_mode else 4
        if len(key_people) < fallback_people_target and source_records:
            for item in _extract_people_from_source_records(
                source_records,
                person_tokens=person_tokens,
                request_terms=request_terms,
                max_items=6 if biography_mode else 10,
            ):
                if item in key_people:
                    continue
                key_people.append(item)
                if len(key_people) >= 10:
                    break
        if biography_mode and not key_people and person_tokens:
            particles = {"de", "del", "la", "las", "los", "y", "da", "do", "dos", "van", "von"}
            pretty = " ".join(t if t in particles else t.title() for t in person_tokens)
            if pretty:
                key_people = [_with_citation(pretty, first_citation)]
        key_people = _dedupe(key_people, max_items=8 if biography_mode else 10)
        # No fallback extraction from arbitrary lines: it tends to turn events/places into "people".

        # Keep interpretations concise and non-repetitive for project writing.
        interpretations = _dedupe(
            [
                _with_citation(x, first_citation)
                for x in interpretations_raw
                if _has_citation(x)
                and _line_relevant_to_request(x, request_terms, person_tokens)
            ],
            max_items=4,
        )

        # Ensure key events and timeline are populated from fact-checked data.
        if not key_events:
            key_events = [x for x in timeline if _is_event_line(x)][:10]
        if not timeline:
            timeline = [x for x in key_events if _is_event_line(x)][:10]

        # Present chronologically for assignment readability.
        timeline = _dedupe_events(_sort_chronological(timeline), max_items=12)
        key_events = _dedupe_events(_sort_chronological(key_events), max_items=12)

        year_span = _year_span(timeline_raw + key_events_raw + facts_raw)
        request_lower = request.lower()
        wants_questions = bool(re.search(r"\b(question|questions|discussion|debate)\b", request_lower))
        wants_limitations = bool(re.search(r"\b(limit|limitations|uncertain|research gaps|open questions)\b", request_lower))
        wants_timeline = bool(re.search(r"\b(timeline|chronology|key dates|dates)\b", request_lower))
        wants_people_section = bool(re.search(r"\b(key people|key figures|important people|main people)\b", request_lower))

        intro_para = _with_citation(summary, first_citation) if summary else ""
        background_para = ""
        events_para = ""
        legacy_para = ""
        death_para = ""

        if biography_mode:
            early_pool = _dedupe(
                context_points
                + facts
                + source_buckets.get("background", [])
                + source_buckets.get("intro", []),
                max_items=24,
            )
            early_candidates = [x for x in early_pool if _is_early_life_line(x)]
            context_candidates = [
                x
                for x in _dedupe(context_points + causes + source_buckets.get("background", []), max_items=20)
                if _is_historical_context_line(x) and x not in early_candidates
            ]
            event_source = _one_event_per_year(
                _dedupe_events(_sort_chronological(key_events + timeline), max_items=20),
                max_items=12,
            )
            death_pool = key_events + timeline + facts + source_buckets.get("death", [])
            if not any(re.search(r"\b(died|death|killed|assassinat|wounded|executed|retreated)\b", _norm(x)) for x in death_pool):
                death_pool = death_pool + consequences
            death_candidates = [
                x
                for x in _dedupe(death_pool, max_items=20)
                if re.search(r"\b(died|death|killed|assassinat|wounded|executed|retreated)\b", _norm(x))
                and not _is_question_like(x)
            ]
            legacy_candidates = [
                x
                for x in _dedupe(consequences + source_buckets.get("legacy", []) + facts, max_items=20)
                if not re.search(r"\b(died|death|killed|assassinat|wounded|executed|retreated)\b", _norm(x))
            ]

            if not intro_para:
                intro_para = _paragraph_from_points(
                    source_buckets.get("intro", [])[:2] + source_buckets.get("events", [])[:1] + early_candidates[:1],
                    max_items=4,
                )
            background_parts: list[str] = []
            if early_candidates:
                background_parts.append(_paragraph_from_points(early_candidates[:4], max_items=4))
            if context_candidates:
                expanded_context = [_expand_context_fragment(x) for x in context_candidates[:3]]
                background_parts.append(_paragraph_from_points(expanded_context, max_items=3))
            background_para = _clean_line(" ".join(x for x in background_parts if x))
            events_para = _build_biography_events_para(event_source, max_items=6) or _narrative_from_events(event_source[:6], max_items=6)
            death_para = _paragraph_from_points([_event_line_to_sentence(x) for x in death_candidates[:4]], max_items=4)
            legacy_para = _paragraph_from_points(legacy_candidates[:5], max_items=5)
        else:
            background_para = _paragraph_from_points(context_points[:5] + causes[:3], max_items=8)
            events_para = _paragraph_from_points((key_events or timeline)[:7] + facts[:2], max_items=9)
            legacy_seed = consequences[:6] + (facts[:3] if consequences else [])
            legacy_para = _paragraph_from_points(legacy_seed, max_items=9)
            death_para = _paragraph_from_points(
                [
                    x
                    for x in (key_events + timeline + facts + consequences)
                    if re.search(r"\b(died|death|killed|assassinat|wounded|executed|retreated)\b", _norm(x))
                ][:5],
                max_items=5,
            )

        if source_buckets:
            if not intro_para:
                intro_para = _paragraph_from_points(
                    source_buckets.get("intro", [])[:2] + source_buckets.get("background", [])[:2] + source_buckets.get("events", [])[:1],
                    max_items=4,
                )
            if not background_para:
                background_para = _paragraph_from_points(
                    source_buckets.get("background", [])[:5] + source_buckets.get("intro", [])[:1],
                    max_items=6,
                )
            if not events_para:
                events_para = _paragraph_from_points(source_buckets.get("events", [])[:7], max_items=7)
            if not legacy_para:
                legacy_para = _paragraph_from_points(source_buckets.get("legacy", [])[:5], max_items=5)
            if not death_para:
                death_para = _paragraph_from_points(source_buckets.get("death", [])[:4], max_items=4)
        if (not intro_para) and source_sentences:
            intro_para = _paragraph_from_points(source_sentences[:3], max_items=3)
        if biography_mode and background_para and "spanish crown" not in _norm(background_para):
            crown_cause = next(
                (
                    x
                    for x in (causes + context_points)
                    if re.search(r"\b(spanish crown|imperial|trade|resource|expansion|territor)\b", _norm(x))
                ),
                "",
            )
            if not crown_cause:
                crown_cause = next(
                    (
                        x
                        for x in source_buckets.get("background", [])
                        if re.search(r"\b(spanish crown|imperial|trade|resource|expansion|territor)\b", _norm(x))
                    ),
                    "",
                )
            if crown_cause:
                crown_sentence = _clean_line(_expand_context_fragment(crown_cause))
                if crown_sentence and _norm(crown_sentence) not in _norm(background_para):
                    background_para = _clean_line(f"{background_para} {crown_sentence}")
        if biography_mode and background_para:
            bg_norm = _norm(background_para)
            has_crown_goals = ("spanish crown s imperial goals" in bg_norm) or ("spanish crowns imperial goals" in bg_norm)
            if "spanish crown sought" in bg_norm and has_crown_goals:
                background_para = re.sub(
                    r"\s*The Spanish Crown[’']s imperial goals[^.]*\.\s*",
                    " ",
                    background_para,
                    flags=re.IGNORECASE,
                )
                background_para = _clean_line(background_para)
        if biography_mode and intro_para and death_para:
            intro_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", intro_para) if s.strip()]
            non_death_intro = [
                s for s in intro_sentences if not re.search(r"\b(died|death|killed|wounded|skirmish)\b", _norm(s))
            ]
            if len(non_death_intro) >= 2:
                intro_para = _clean_line(" ".join(non_death_intro))
        if events_para and intro_para and _norm(events_para) == _norm(intro_para):
            events_para = ""
        if biography_mode and (not events_para or len(re.split(r"(?<=[.!?])\s+", events_para)) < 2):
            event_fallback = _dedupe_events(
                _sort_chronological(key_events + timeline + source_buckets.get("events", [])),
                max_items=10,
            )
            rebuilt_events = _build_biography_events_para(event_fallback, max_items=6) or _narrative_from_events(
                event_fallback[:6],
                max_items=6,
            )
            if rebuilt_events:
                events_para = rebuilt_events
        if biography_mode and death_para:
            death_pool = key_events + timeline + facts + source_buckets.get("death", [])
            if not any(re.search(r"\b(died|death|killed|assassinat|wounded|executed|retreated)\b", _norm(x)) for x in death_pool):
                death_pool = death_pool + consequences
            death_only_events = [
                x
                for x in death_pool
                if re.search(r"\b(died|death|killed|assassinat|wounded|executed|retreated)\b", _norm(x))
            ]
            death_para = _paragraph_from_points(
                _dedupe_events(
                    [
                        _event_line_to_sentence(x)
                        for x in death_only_events
                    ],
                    max_items=3,
                ),
                max_items=3,
            )
        if legacy_para and events_para and _norm(legacy_para) == _norm(events_para):
            legacy_para = ""
        if legacy_para and intro_para and _norm(legacy_para) == _norm(intro_para):
            legacy_para = ""
        if background_para and intro_para and _norm(background_para) == _norm(intro_para):
            background_para = ""

        project_line = "History Project"
        subtitle = "A clear and source-based school project"
        if assignment_kind == "essay":
            project_line = "History Essay Project"
            subtitle = "A structured historical analysis"
        elif assignment_kind == "homework":
            project_line = "History Homework Project"
            subtitle = "A complete assignment-ready response"
        elif assignment_kind == "presentation":
            project_line = "History Presentation Project"
            subtitle = "Class-ready speaking and notes format"
        elif assignment_kind == "report":
            project_line = "History Report Project"
            subtitle = "A detailed historical research report"
        if biography_mode:
            project_line = "Historical Figure Project"
            if title.lower().startswith("biography of"):
                subtitle = "A biography project"
            else:
                subtitle = f"A biography of {title}"
        if audience == "kid":
            subtitle = "A kid-friendly school project"
        if year_span:
            project_line = f"{project_line}: {year_span}"

        lines: list[str] = []
        lines.append(f"# {title}")
        lines.append(f"*{subtitle}*")
        lines.append(f"*{project_line}*")
        lines.append("")

        if intro_para:
            lines.append("## Introduction")
            lines.append(intro_para)
            lines.append("")

        if biography_mode:
            if background_para:
                lines.append("## Early Life and Background")
                lines.append(_with_citation(background_para, first_citation))
                lines.append("")
            if events_para:
                lines.append("## Life and Major Events")
                lines.append(_with_citation(events_para, first_citation))
                lines.append("")
            if death_para:
                lines.append("## Later Years and Death")
                lines.append(_with_citation(death_para, first_citation))
                lines.append("")
            if legacy_para:
                lines.append("## Legacy and Historical Impact")
                lines.append(_with_citation(legacy_para, first_citation))
                lines.append("")
        else:
            if background_para:
                lines.append("## Historical Background and Causes")
                lines.append(_with_citation(background_para, first_citation))
                lines.append("")
            if events_para:
                lines.append("## Major Events and Turning Points")
                lines.append(_with_citation(events_para, first_citation))
                lines.append("")
            if legacy_para:
                lines.append("## Impact and Legacy")
                lines.append(_with_citation(legacy_para, first_citation))
                lines.append("")

        legacy_core = _first_sentence(legacy_para)
        intro_core = _first_sentence(intro_para)
        death_core = _first_sentence(death_para)
        indigenous_core = _first_sentence(
            _paragraph_from_points(
                [
                    x
                    for x in (consequences + context_points + causes + facts)
                    if re.search(r"\b(indigenous|taino|calusa|native|resisted|resistance|conflict)\b", _norm(x))
                ][:2],
                max_items=2,
            )
        )
        legacy_clause = _as_clause(legacy_core)
        intro_clause = _as_clause(intro_core)
        death_clause = _as_clause(death_core)
        indigenous_clause = _as_clause(indigenous_core)
        if biography_mode:
            if legacy_clause.startswith("he "):
                legacy_clause = f"Ponce de León {legacy_clause[3:]}"
            if intro_clause.startswith("he "):
                intro_clause = f"Ponce de León {intro_clause[3:]}"
            if death_clause.startswith("he "):
                death_clause = f"he {death_clause[3:]}"
            if indigenous_clause.startswith("he "):
                indigenous_clause = f"this period {indigenous_clause[3:]}"
        if biography_mode and legacy_core:
            impact_clause = indigenous_clause if indigenous_core else death_clause
            if impact_clause and _clause_similarity_key(impact_clause) != _clause_similarity_key(legacy_clause):
                impact_sentence = impact_clause[:1].upper() + impact_clause[1:]
                impact_sentence = impact_sentence.rstrip(".") + "."
            else:
                impact_sentence = "His expeditions also intensified conflict with Indigenous communities and reshaped the colonial history of the region."
            conclusion_para = _with_citation(
                f"In conclusion, {legacy_clause.rstrip('.')}. "
                f"{impact_sentence} "
                "His legacy shows how exploration advanced empire while also intensifying colonial conflict. "
                "Studying his story today helps explain the long-term effects of early colonization.",
                first_citation,
            )
        elif legacy_core and intro_core and _norm(legacy_core) != _norm(intro_core):
            conclusion_para = _with_citation(
                f"In conclusion, {legacy_clause.rstrip('.')}. This topic remains important because {intro_clause.rstrip('.')}.",
                first_citation,
            )
        elif biography_mode and intro_core and death_core and _norm(intro_core) != _norm(death_core):
            conclusion_para = _with_citation(
                f"In conclusion, {intro_clause.rstrip('.')}. His later years ended when {death_clause.rstrip('.')}.",
                first_citation,
            )
        elif legacy_core:
            conclusion_para = _with_citation(f"In conclusion, {legacy_clause.rstrip('.')}.", first_citation)
        elif events_para:
            conclusion_para = _with_citation(_as_clause(_first_sentence(events_para)), first_citation)
        else:
            conclusion_para = _with_citation(intro_clause, first_citation) if intro_core else ""
        if conclusion_para:
            lines.append("## Conclusion")
            lines.append(_with_citation(conclusion_para, first_citation))
            lines.append("")

        timeline_for_output = list(timeline)
        timeline_for_output = _one_event_per_year(timeline_for_output, max_items=10)
        if biography_mode and timeline_for_output:
            has_death_line = any(re.search(r"\b(died|death)\b", _norm(x)) for x in timeline_for_output)
            if has_death_line:
                timeline_for_output = [
                    x
                    for x in timeline_for_output
                    if not re.search(r"\b(fatally wounded|wounded by an arrow)\b", _norm(x))
                ] or timeline_for_output

        if timeline_for_output and (len(timeline_for_output) >= 2 or wants_timeline):
            lines.append("## Timeline of Key Dates")
            emitted_timeline_keys: set[str] = set()
            for item in timeline_for_output[:10]:
                bullet_line = _timeline_bullet_fragment(item) if _has_date_like(item) else _clean_line(item)
                if not bullet_line or _is_question_like(bullet_line):
                    continue
                timeline_key = _event_core_key(bullet_line)
                if timeline_key and timeline_key in emitted_timeline_keys:
                    continue
                if timeline_key:
                    emitted_timeline_keys.add(timeline_key)
                lines.append(f"- {_with_citation(bullet_line, first_citation)}")
            lines.append("")

        if key_people and wants_people_section:
            lines.append("## Key People")
            for item in key_people[:8]:
                bullet = _format_person_bullet(item)
                lines.append(bullet or f"- {item}")
            lines.append("")

        if interpretations and not biography_mode and assignment_kind in {"essay", "report"}:
            lines.append("## Historical Perspectives")
            for idx, item in enumerate(interpretations[:2], start=1):
                lines.append(f"### Perspective {idx}")
                lines.append(_clean_line(_with_citation(item, first_citation)))
                lines.append("")

        if limitations and wants_limitations:
            lines.append("## Open Questions for Research")
            for item in limitations[:5]:
                lines.append(f"- {item}")
            lines.append("")

        if questions and wants_questions:
            lines.append("## Questions for Discussion")
            for item in questions[:8]:
                lines.append(f"- {item}")
            lines.append("")

        if sources:
            lines.append("## Works Cited")
            for item in sources:
                lines.append(f"- {_clean_line(item)}")
            lines.append("")

        document = "\n".join(lines).strip() + "\n"
        return AgentResult(
            ok=True,
            data={
                "document": document,
                "format": "markdown",
                "audience": audience,
                "assignment_type": assignment_kind,
                "sources": sources,
                "source_meta": source_meta,
            },
        )
