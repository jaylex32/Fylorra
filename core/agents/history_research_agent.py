from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from urllib.parse import quote_plus, urlparse, unquote
import requests
from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent, _safe_json
from core.agents.research_agent import (
    _classify_source,
    _source_breakdown,
    _diversity_score,
    _source_quality_warning,
    _validate_sources,
    _assign_claim_sources,
    _attach_finding_sources,
    _best_source_for_text,
)
from core.text_extractor import extract_text_from_file
from core.integrations.web_search import search_web, fetch_url_text


class HistoryResearchAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="history_research_agent",
            role="researcher",
            system_prompt=(
                "You are a careful history researcher.\n"
                "Return factual, source-grounded notes with clear citations.\n"
                "Avoid speculation and label uncertainty explicitly."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="history_research",
                    name="History Research",
                    description="Collect credible sources and summarize historical facts.",
                    input_types=["text", "file"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=50,
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
        max_results = int(data.get("web_max_results") or context.initial_parameters.get("web_max_results") or 6)
        require_web = bool(self.config.get("require_web", True))
        # Keep consistent with the shared source validation thresholds used across the app.
        # (ResearchAgent treats 3 sources as the minimum viable set.)
        min_sources = int(self.config.get("min_sources") or 3)
        try:
            settings = context.services.get("settings")
            wf_settings = settings.get_workflow_settings() if settings else {}
            allow_web = bool(allow_web or wf_settings.get("allow_web_research", False))
            max_results = int(wf_settings.get("web_max_results", max_results))
        except Exception:
            pass

        if require_web and not allow_web and not source_files and not source_text:
            return AgentResult(ok=False, message="Web research is required for history templates.")

        collected: list[str] = []
        sources: list[str] = []
        source_blocks: list[str] = []
        source_meta: list[dict[str, Any]] = []
        source_records: list[dict[str, Any]] = []
        source_count = 0
        seen_urls: set[str] = set()
        biography_request = False
        domain_counts: dict[str, int] = {}
        domain_caps: dict[str, int | None] = {
            # Keep Wikipedia as a supplemental source, not the whole bibliography. We allow a few
            # biography/person pages for Key People, but cap it so it doesn't dominate.
            "wikipedia.org": 4,
            # Wikidata is great for ids/metadata, but not useful as a reading source for this template.
            "wikidata.org": 0,
        }

        def _domain_key(url: str) -> str:
            try:
                host = urlparse(str(url or "")).netloc.lower()
            except Exception:
                return ""
            if host.endswith("wikipedia.org"):
                return "wikipedia.org"
            if host.endswith("wikidata.org"):
                return "wikidata.org"
            return host

        def _clean_web_text(text: str, url: str) -> str:
            raw = str(text or "")
            if not raw:
                return ""
            # Remove inline footnote markers that come from scraped sources (Wikipedia, etc.).
            # These are not our citations and they confuse downstream parsing.
            raw = re.sub(r"\[\s*\d+\s*\]", "", raw)
            lowered_url = str(url or "").lower()
            # `fetch_url_text()` often returns a single long line (HTML extracted & whitespace-collapsed).
            # Treat that as a content blob and avoid line-based heuristics that can incorrectly discard it.
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if len(lines) <= 1 and len(raw) >= 800:
                blob = re.sub(r"\s+", " ", raw).strip()
                # Keep some light cleanup, but don't over-filter.
                blob = re.sub(r"\b(skip to main content|skip to content|privacy policy|terms of use|cookie policy)\b", "", blob, flags=re.IGNORECASE)
                blob = re.sub(r"\s{2,}", " ", blob).strip()
                return blob
            cleaned: list[str] = []
            skip_exact = {
                "top of page",
                "skip to main content",
                "skip to content",
                "skip to navigation",
                "back to top",
                "privacy policy",
                "terms of use",
                "cookie policy",
            }
            for ln in lines:
                if not ln:
                    continue
                low = ln.lower()
                if low in skip_exact:
                    continue
                if "subscribe" in low or "newsletter" in low:
                    continue
                if "all rights reserved" in low or "copyright" in low:
                    continue
                if "tracking the retirement announcements" in low:
                    continue
                if re.search(r"\b(?:am|pm)\s+et\b", low):
                    continue
                if re.search(r"\b(?:am|pm)\s+utc\b", low):
                    continue
                if re.search(r"\b(?:am|pm)\s+gmt\b", low):
                    continue
                # Navigation/tag clouds often look like long lists of capitalized terms.
                if len(ln) > 120 and sum(1 for w in ln.split() if w[:1].isupper()) >= 8:
                    continue
                # Drop very short, all-caps fragments (menus, time labels, etc.)
                if len(ln) <= 6 and ln.isupper():
                    continue
                # Britannica / LOC guides sometimes include lots of nav chrome; keep content-heavy lines.
                if "britannica.com" in lowered_url or "guides.loc.gov" in lowered_url:
                    if len(ln) < 40 and not re.search(r"\b(18|19|20)\d{2}\b", ln):
                        # Allow dated short lines, otherwise skip.
                        continue
                cleaned.append(ln)
            out = "\n".join(cleaned).strip()
            out = re.sub(r"\n{3,}", "\n\n", out)
            if not out:
                # Fallback: keep some content rather than returning empty text excerpts.
                out = re.sub(r"\s+", " ", raw).strip()
            return out

        def add_source(*, title: str, url: str, text: str, origin: str) -> None:
            nonlocal source_count
            url = str(url or "").strip()
            domain_key = _domain_key(url) if (origin == "web" and url) else ""
            if domain_key:
                cap = domain_caps.get(domain_key)
                if cap == 0:
                    return
                if cap is not None and domain_counts.get(domain_key, 0) >= cap:
                    return
            if url and url in seen_urls:
                return
            if url:
                seen_urls.add(url)
            clean_title = str(title or "").strip()
            if url and "loc.gov" in url.lower():
                clean_title = re.sub(r"\s*\|\s*library of congress\s*$", "", clean_title, flags=re.IGNORECASE).strip()
                clean_title = re.sub(r"\s*-\s*library of congress\s*$", "", clean_title, flags=re.IGNORECASE).strip()

            raw_text = str(text or "")
            # Do not add "empty" web sources; evidence-gating and name extraction depends on excerpts.
            # If a fetch yields no usable text, skip and let the search continue.
            if origin == "web" and not raw_text.strip():
                return

            source_count += 1
            if domain_key:
                domain_counts[domain_key] = domain_counts.get(domain_key, 0) + 1
            src_type = _classify_source(title, url, origin)
            label = f"[{source_count}] {clean_title or title}"
            if url:
                label = f"{label} - {url}"
            if origin == "local_file":
                label = f"[{source_count}] Local file: {clean_title or title}"
            sources.append(label)
            if raw_text:
                if origin == "web":
                    cleaned = _clean_web_text(raw_text, url)
                    if cleaned:
                        text = cleaned
                    else:
                        # Never allow empty excerpts for web sources; downstream evidence-gating depends on this.
                        text = re.sub(r"\s+", " ", raw_text).strip()
                header = f"[{source_count}] {clean_title or title}"
                if url:
                    header = f"{header} ({url})"
                source_blocks.append(f"{header}\n{text}")
            source_meta.append(
                {
                    "id": source_count,
                    "title": clean_title or title,
                    "url": url,
                    "type": src_type,
                    "origin": origin,
                }
            )
            source_records.append(
                {
                    "id": source_count,
                    "title": clean_title or title,
                    "url": url,
                    "origin": origin,
                    "text": text or "",
                    "text_excerpt": text or "",
                }
            )

        def _extract_topic_hint(text: str) -> str:
            if not text:
                return ""
            cleaned = re.sub(
                r"(?i)^(create|write|build|make)( a)? (history|historical) (project|report|essay|timeline)( on| about| of)?",
                "",
                text.strip(),
            ).strip()
            if cleaned:
                return cleaned
            return text.strip()

        def _loc_search(query: str, limit: int) -> list[dict[str, str]]:
            q = str(query or "").strip()
            if not q:
                return []
            url = f"https://www.loc.gov/search/?q={quote_plus(q)}&fo=json"
            try:
                resp = requests.get(url, timeout=12)
            except Exception:
                return []
            if resp.status_code != 200:
                return []
            try:
                data = resp.json()
            except Exception:
                return []
            results = []
            for item in list(data.get("results") or []):
                if len(results) >= limit:
                    break
                title = str(item.get("title") or "").strip()
                link = str(item.get("url") or "").strip()
                if not title or not link:
                    continue
                results.append({"title": title, "url": link})
            return results

        def _wiki_page(query: str) -> dict[str, str] | None:
            q = str(query or "").strip()
            if not q:
                return None
            slug = quote_plus(q).replace("+", "_")
            url = f"https://en.wikipedia.org/wiki/{slug}"
            try:
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            except Exception:
                return None
            if resp.status_code != 200:
                return None
            title = q
            return {"title": f"Wikipedia - {title}", "url": url}

        def _normalize_text(value: str) -> str:
            # Remove both our citations ([12]) and common scraped footnote markers ([ 12 ]).
            text = re.sub(r"\[\s*\d+\s*\]", "", str(value or ""))
            text = re.sub(r"\s+", " ", text).strip().lower()
            return text

        def _dedupe_list(items: Any, *, key_func=None, max_items: int | None = None) -> list[str]:
            if not isinstance(items, list):
                if items is None:
                    return []
                return [str(items).strip()]
            out: list[str] = []
            seen: set[str] = set()
            for item in items:
                text = str(item or "").strip()
                if not text:
                    continue
                key = key_func(text) if key_func else _normalize_text(text)
                if key in seen:
                    continue
                seen.add(key)
                out.append(text)
                if max_items and len(out) >= max_items:
                    break
            return out

        def _event_key(item: str) -> str:
            cleaned = re.sub(r"\[\d+\]", "", item)
            cleaned = re.sub(r"^\s*[^:]+:\s*", "", cleaned)
            cleaned = re.sub(
                r"^\s*(?:\d{4}|[A-Za-z]+\s+\d{1,2},\s*\d{4}|[A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*[-–:]*\s*",
                "",
                cleaned,
            )
            return _normalize_text(cleaned)

        def _person_key(item: str) -> str:
            # Split only on explicit separators (avoid splitting hyphens inside names).
            base = re.split(r"\s*(?:---|--|—|–|:)\s*|\s+-\s+", str(item or ""), 1)[0]
            return _normalize_text(base)

        def _is_generic_person(item: str) -> bool:
            lowered = _normalize_text(item)
            if not lowered:
                return True
            # Filter common "not-a-person" placeholders that frequently appear in LLM outputs.
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
            return any(phrase == lowered or phrase in lowered for phrase in generic_phrases)

        def _has_year(item: str) -> bool:
            return bool(re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", item))

        def _is_placeholder_timeline(item: str) -> bool:
            lowered = _normalize_text(item)
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
                "published",
                "publication",
                "study",
                "book",
                "work discussed",
                "work was",
                "provides background context",
                "background context",
            ]
            return any(phrase in lowered for phrase in banned)

        def _is_publication_line(item: str) -> bool:
            lowered = _normalize_text(item)
            if not lowered:
                return True
            publication_markers = [
                "published",
                "publication",
                "study",
                "book",
                "work discussed",
                "work was",
                "work",
                "report was",
                "report discussed",
                "report of",
                "first major historical study",
                "in english",
                "author",
                "historian",
                "library of congress",
                "special holiday hours",
                "top of page",
                "preservation microfilming",
                "photoduplication service",
                "available from",
                "catalog",
                "digital id",
            ]
            if any(marker in lowered for marker in publication_markers):
                return True
            if "work" in lowered and ("discussed" in lowered or "study" in lowered or "book" in lowered):
                return True
            if re.search(r"^\(?\s*\d{4}\s*\)?\s+(report|history|the history)\b", lowered):
                return True
            # Bibliographic author patterns like "Davis, George W." are not historical events.
            if re.search(r"\b[A-Z][a-z]+,\s+[A-Z]", str(item or "")) and not re.search(
                r"\b(appointed|landed|signed|ceded|passed|raised|surrendered|occupied|invaded)\b",
                lowered,
            ):
                return True
            return False

        def _has_event_keyword(item: str) -> bool:
            lowered = _normalize_text(item)
            keywords = [
                # General event cues (avoid topic-specific proper nouns).
                "treaty",
                "act",
                "law",
                "constitution",
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

        def _extract_event_sentences(source_records: list[dict[str, Any]]) -> list[str]:
            candidates: list[str] = []
            for record in source_records:
                sid = record.get("id")
                text = str(record.get("text") or "")
                if not text:
                    continue
                sentences = re.split(r"(?<=[.!?])\s+", text)
                for sentence in sentences:
                    clean = sentence.strip()
                    if not clean:
                        continue
                    if not _has_year(clean):
                        continue
                    if _is_publication_line(clean):
                        continue
                    if not _has_event_keyword(clean):
                        continue
                    if len(clean) > 360:
                        clean = clean[:340].rsplit(" ", 1)[0].rstrip(" ,;:-")
                    if sid:
                        candidates.append(f"{clean} [{sid}]")
                    else:
                        candidates.append(clean)
            # Keep a larger pool so later filters can drop malformed "blank hole" lines
            # without starving timeline/key events.
            return _dedupe_list(candidates, key_func=_event_key, max_items=60)

        def _citation_ids(text: str) -> list[int]:
            ids = []
            for m in re.findall(r"\[(\d+)\]", str(text or "")):
                try:
                    ids.append(int(m))
                except Exception:
                    continue
            return ids

        def _strip_citations(text: str) -> str:
            # Remove both our citations ([12]) and common scraped footnote markers ([ 12 ]).
            return re.sub(r"\s*\[\s*\d+\s*\]\s*", " ", str(text or "")).strip()

        def _extract_year(item: str) -> int | None:
            match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", item)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    return None
            return None

        def _timeline_score(item: str) -> int:
            text = str(item or "")
            lowered = _normalize_text(text)
            score = 0
            if _is_publication_line(text):
                score -= 6
            if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", lowered):
                score += 3
            if re.search(r"\b(act|treaty|constitution|plebiscite|referendum)\b", lowered):
                score += 3
            if re.search(r"\b(governor|congress|assembly|citizenship|annex|surrender|landing)\b", lowered):
                score += 2
            if re.search(r"\b(establishes a new|establishes new)\b", lowered):
                score -= 4
            score += min(len(text) // 40, 3)
            return score

        def _rebalance_citations(items: list[str], source_records: list[dict[str, Any]]) -> list[str]:
            if not items or not source_records:
                return items
            out: list[str] = []
            for item in items:
                if not item:
                    continue
                existing = _citation_ids(item)
                best = _best_source_for_text(_strip_citations(item), source_records)
                if best and (not existing or (len(set(existing)) == 1 and existing[0] == 1 and best != 1)):
                    out.append(f"{_strip_citations(item)} [{best}]")
                else:
                    out.append(item)
            return out

        def _is_name_like(item: str) -> bool:
            head = _strip_citations(str(item or "")).strip()
            if not head:
                return False
            if head.lower().startswith(("the ", "a ", "an ")):
                return False
            head = re.split(r"\s*[-–—:]\s*", head, 1)[0].strip()
            if not head:
                return False
            if re.search(r"\bU\.?\s*S\.?\b", head):
                return False
            if re.search(r"\d", head):
                return False
            # Reject short all-caps fragments (e.g., "AM ET", "PM ET", "US") that often come from site chrome.
            parts = [p for p in re.split(r"\s+", head) if p]
            if parts:
                month = parts[0].rstrip(".").lower()
                if len(parts) == 1 and re.fullmatch(
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)",
                    month,
                ):
                    return False
                upper_parts = [p for p in parts if p.isupper() and len(p) <= 4]
                if len(upper_parts) == len(parts):
                    return False
                if any(p in {"AM", "PM", "ET", "UTC", "GMT"} for p in upper_parts):
                    return False
            # Basic token shape.
            token = r"[^\W\d_](?:[^\W\d_]|[.''\-]){0,23}"
            if not re.match(rf"^(?:{token}\s+)?{token}(?:\s+{token}){{1,5}}$", head):
                return False

            # Require proper-name capitalization for non-connector tokens so we don't accept prose fragments like
            # "Spanish forces surrender in" or "officially transferring X".
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
            if not any(ch.isupper() for ch in head):
                return False
            first_word = re.sub(r"[^\w'.-]", "", words[0]).rstrip(".").lower()
            if first_word in {"the", "a", "an", "and", "or"}:
                return False
            for word in words:
                w = re.sub(r"^[\"'“”‘’`\\(\\)\\[\\]\\{\\}\\*]+|[\"'“”‘’`\\(\\)\\[\\]\\{\\}\\*]+$", "", word)
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

        def _ensure_citations(items: list[str], source_ids: list[int], usage: dict[int, int]) -> list[str]:
            if not items:
                return items
            if not source_ids:
                return items
            out: list[str] = []
            for item in items:
                if not item:
                    continue
                if re.search(r"\[\d+\]", item):
                    for sid in _citation_ids(item):
                        usage[sid] = usage.get(sid, 0) + 1
                    out.append(item)
                    continue
                # Pick the least-used source id to spread citations.
                sid = min(source_ids, key=lambda s: usage.get(s, 0))
                usage[sid] = usage.get(sid, 0) + 1
                out.append(f"{item} [{sid}]")
            return out

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
            topic_hint = _extract_topic_hint(request)

            def _to_ascii(value: str) -> str:
                try:
                    value = unicodedata.normalize("NFKD", str(value or ""))
                    return "".join(ch if ord(ch) < 128 else " " for ch in value)
                except Exception:
                    return str(value or "")

            query_base = re.sub(r"\s+", " ", _to_ascii(topic_hint or request)).strip()

            def _topic_keywords(text: str) -> list[str]:
                cleaned = re.sub(r"[^A-Za-z0-9\s-]+", " ", _to_ascii(text or ""))
                cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
                if not cleaned:
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
                    "for",
                    "from",
                    "has",
                    "have",
                    "how",
                    "in",
                    "into",
                    "is",
                    "it",
                    "its",
                    "of",
                    "on",
                    "or",
                    "that",
                    "the",
                    "their",
                    "this",
                    "to",
                    "was",
                    "were",
                    "what",
                    "when",
                    "where",
                    "who",
                    "why",
                    "with",
                    # Very common query terms that cause irrelevant matches.
                    "united",
                    "states",
                    "state",
                    "government",
                    "history",
                    "project",
                    "report",
                    "analysis",
                    "biography",
                    "school",
                    "assignment",
                    "essay",
                    "class",
                }
                parts = [p for p in cleaned.split(" ") if p and p not in stop and len(p) >= 3]
                out: list[str] = []
                seen: set[str] = set()
                for p in parts:
                    if p in seen:
                        continue
                    seen.add(p)
                    out.append(p)
                    if len(out) >= 10:
                        break
                return out

            keywords = _topic_keywords(query_base)
            generic_keywords = {
                "united",
                "states",
                "state",
                "history",
                "project",
                "report",
                "analysis",
                "take",
                "took",
                "over",
                "invasion",
                "occupation",
                "control",
                "war",
                "treaty",
                "act",
                "law",
                "government",
            }
            # Keep "event type" words separate from topic words. For many history prompts (like
            # "take over / invasion / occupation"), the topic words are just the place/entity name,
            # and we want Wikipedia filtering to require BOTH topic + focus so we don't end up with
            # city pages ("Ponce, Puerto Rico") or broad overviews.
            focus_keywords = {
                "invasion",
                "occupation",
                "campaign",
                "annex",
                "annexation",
                "cede",
                "ceded",
                "cession",
                "treaty",
                "act",
                "law",
                "war",
                "armistice",
                "surrender",
                "transfer",
                "takeover",
                "governor",
                "congress",
                "military",
                "civil",
                "civilian",
            }
            focus_terms = [kw for kw in keywords if kw in focus_keywords]
            # If the user asked about takeovers/occupations/invasions, broaden the allowed "focus"
            # terms to include common near-synonyms that often appear in relevant page titles.
            # This is generic (not topic-specific) and prevents rejecting "campaign" pages when
            # the request used "invasion/occupation" phrasing instead.
            if any(w in focus_terms for w in ("invasion", "occupation", "takeover", "annex", "annexation", "control")):
                implied = {
                    "campaign",
                    "treaty",
                    "act",
                    "war",
                    "armistice",
                    "surrender",
                    "cede",
                    "ceded",
                    "cession",
                    "transfer",
                }
                focus_terms = sorted(set(focus_terms).union(implied))
            topic_keywords = [kw for kw in keywords if kw not in generic_keywords and kw not in focus_keywords]
            distinctive_keywords = topic_keywords
            request_lower = _normalize_text(request)

            def _relevance_score(title: str, text: str) -> int:
                blob = f"{title}\n{text}".lower()
                score = 0
                if distinctive_keywords:
                    # Require at least one topic-distinctive keyword match, otherwise generic queries
                    # like "united states" can pull irrelevant pages.
                    if not any(kw and kw in blob for kw in distinctive_keywords[:8]):
                        return 0
                for kw in keywords[:10]:
                    if kw and kw in blob:
                        score += 2 if kw in distinctive_keywords else 1
                if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", blob):
                    score += 1
                if re.search(r"\b(treaty|act|law|war|invasion|occupation|annex|ceded|signed|governor|congress)\b", blob):
                    score += 1
                return score

            def _request_mentions_any(words: list[str]) -> bool:
                for w in words:
                    if w and w.lower() in request_lower:
                        return True
                return False

            def _looks_like_person_query(query: str) -> bool:
                q = re.sub(r"\s+", " ", str(query or "")).strip()
                if not q:
                    return False
                q_lower = q.lower()
                if any(kw in q_lower for kw in keywords[:8]):
                    return False
                # Avoid treating common geo/political terms as "person names".
                non_person_tokens = {
                    "united",
                    "states",
                    "republic",
                    "kingdom",
                    "empire",
                    "war",
                    "act",
                    "treaty",
                    "history",
                    "campaign",
                    "occupation",
                    "invasion",
                }
                tokens = [t for t in re.split(r"\s+", q) if t]
                if any(t.lower() in non_person_tokens for t in tokens):
                    return False
                # 2-5 person-like tokens (accept lowercase user input too).
                if 2 <= len(tokens) <= 5 and all(re.match(r"^[A-Za-z\u00C0-\u017F][A-Za-z\u00C0-\u017F.'-]*$", t) for t in tokens):
                    return True
                return False

            def _person_name_from_query(query: str) -> str | None:
                q = re.sub(r"\s+", " ", str(query or "")).strip()
                if not q:
                    return None
                stop_words = {
                    "puerto",
                    "rico",
                    "united",
                    "states",
                    "usa",
                    "u.s.",
                    "us",
                    "invasion",
                    "occupation",
                    "takeover",
                    "annexation",
                    "annex",
                    "campaign",
                    "treaty",
                    "act",
                    "law",
                    "war",
                    "timeline",
                    "leader",
                    "leaders",
                    "key",
                    "figures",
                    "people",
                    "biography",
                    "history",
                    "project",
                    "assignment",
                    "essay",
                    "school",
                    "report",
                    "research",
                    "create",
                    "write",
                    "build",
                    "make",
                    "about",
                    "on",
                    "of",
                    "for",
                    "the",
                    "a",
                    "an",
                    "and",
                }
                particles = {"de", "del", "la", "las", "los", "y", "da", "do", "dos", "van", "von"}

                # Prefer the subject phrase after "about/on/of" when present.
                subject = q
                m = re.search(r"(?i)\b(?:about|on|of)\b\s+(.+)$", q)
                if m:
                    subject = m.group(1).strip()
                subject = re.sub(r"(?i)\s+for\s+(kids?|children|teens?|adults?)\s*$", "", subject).strip()

                def _collect(segment: str) -> str | None:
                    tokens = [t for t in re.split(r"\s+", segment) if t]
                    if not tokens:
                        return None
                    name_tokens: list[str] = []
                    for raw_token in tokens:
                        t_clean = re.sub(r"[^\w\.\-'\u00C0-\u017F]+", "", raw_token).strip()
                        if not t_clean:
                            if name_tokens:
                                break
                            continue
                        t_lower = t_clean.lower().strip(".")
                        if re.match(r"^\d+$", t_lower):
                            if name_tokens:
                                break
                            continue
                        # Skip leading prompt/directive words; stop once name capture started.
                        if t_lower in stop_words and t_lower not in particles:
                            if name_tokens:
                                break
                            continue
                        if name_tokens and t_lower in particles:
                            name_tokens.append(t_lower)
                            continue
                        if re.match(r"^[A-Za-z\u00C0-\u017F][A-Za-z\u00C0-\u017F.'-]*$", t_clean):
                            if t_lower in particles:
                                name_tokens.append(t_lower)
                            else:
                                name_tokens.append(t_clean[0].upper() + t_clean[1:].lower())
                            continue
                        if name_tokens:
                            break
                    name = re.sub(r"\s+", " ", " ".join(name_tokens)).strip()
                    if len(name.split()) >= 2 and len(name) >= 6:
                        return name
                    return None

                for candidate in (subject, q):
                    parsed = _collect(candidate)
                    if parsed:
                        return parsed
                return None

            topic_hint_for_person = _extract_topic_hint(request)
            person_topic_name = _person_name_from_query(topic_hint_for_person) or _person_name_from_query(request)
            person_particles = {"de", "del", "la", "las", "los", "y", "da", "do", "dos", "van", "von"}
            person_topic_tokens: list[str] = []
            if person_topic_name:
                for token in re.split(r"\s+", _normalize_text(person_topic_name)):
                    if token and len(token) > 2 and token not in person_particles:
                        person_topic_tokens.append(token)
            person_topic_last = person_topic_tokens[-1] if person_topic_tokens else ""

            def _should_keep_search_hit(title: str, url: str, query: str = "") -> bool:
                u = str(url or "").strip()
                if not u.startswith(("http://", "https://")):
                    return False
                t = str(title or "").strip()
                try:
                    host = urlparse(u).netloc.lower()
                    path = urlparse(u).path.lower()
                except Exception:
                    host = ""
                    path = u.lower()

                t_norm = _normalize_text(t)
                page_norm = _normalize_text(f"{t} {unquote(path).replace('_', ' ')}")
                if "wikidata.org" in host:
                    return False
                # For person/biography school work, reject legal/catalog/building records that
                # produce low-quality homework output.
                if biography_request:
                    low_blob = _normalize_text(f"{t} {unquote(path)}")
                    if "congress.gov" in host:
                        return False
                    if "loc.gov" in host and "primary source" not in _normalize_text(query):
                        return False
                    if re.search(
                        r"\b(bill|commission|act\b|commercial building|avenue|land record|catalog|collection|finding aid|search result)\b",
                        low_blob,
                    ):
                        return False
                    if re.search(r"\b(s\.\d{2,6}|hr\s*\d{2,6})\b", low_blob):
                        return False
                # Filter obvious non-content / utility pages unless explicitly requested.
                if any(word in t_norm for word in ("special holiday hours", "top of page", "photoduplication", "preservation microfilming")):
                    return False
                if any(word in t_norm for word in ("bibliography", "dictionary", "glossary", "catalog", "collection")) and not _request_mentions_any(
                    ["bibliography", "dictionary", "glossary", "catalog", "collection"]
                ):
                    return False
                if any(word in t_norm for word in ("flag of", "list of")) and not _request_mentions_any(["flag", "list"]):
                    return False
                # Wikipedia: avoid meta pages that derail the topic.
                if "wikipedia.org" in host and "/wiki/" in path:
                    slug = path.split("/wiki/", 1)[1]
                    slug_decoded = unquote(slug).replace("_", " ").strip().lower()
                    if slug.startswith(("File:", "Category:", "Special:", "Help:", "Template:", "Portal:")):
                        return False
                    if slug.startswith(("List_of_", "Flag_of_")) and not _request_mentions_any(["flag", "list"]):
                        return False
                    # Reject place/city pages like "Ponce, Puerto Rico" unless explicitly requested.
                    if "," in slug_decoded:
                        place = slug_decoded.split(",", 1)[0].strip()
                        if place and place not in request_lower:
                            return False
                    # If the query clearly targets a person, allow biography pages even when the
                    # main request includes "focus" terms (invasion/occupation/etc). This prevents
                    # Key People from being U.S.-only without letting Wikipedia dominate.
                    person_target = _person_name_from_query(query)
                    if person_target:
                        pt = _normalize_text(person_target)
                        pt_tokens = [tok for tok in re.split(r"\s+", pt) if tok]
                        pt_last = pt_tokens[-1] if pt_tokens else ""
                        if pt_last and pt_last not in page_norm:
                            return False
                        if pt_tokens:
                            pt_hits = sum(1 for tok in pt_tokens if tok in page_norm)
                            if pt_hits < min(2, len(pt_tokens)):
                                return False
                        if pt and (slug_decoded.startswith(pt) or _normalize_text(t).startswith(pt)):
                            return True
                    # For person-focused history topics, enforce stronger identity matching so
                    # similarly named but unrelated people do not slip in (e.g. Juan Ponce Enrile).
                    if person_topic_tokens:
                        if person_topic_last and person_topic_last not in page_norm:
                            return False
                        token_hits = sum(1 for tok in person_topic_tokens if tok in page_norm)
                        if token_hits < min(2, len(person_topic_tokens)):
                            return False
                    # Wikipedia: require a topic keyword match to avoid irrelevant pages that match
                    # only generic "event type" words (e.g., "invasion" elsewhere in the world).
                    if topic_keywords and not any(kw in slug_decoded or kw in t_norm for kw in topic_keywords[:8]):
                        return False
                    # When the request includes "focus" terms (invasion/occupation/treaty/etc),
                    # also require a focus-term match to avoid broad overviews.
                    if focus_terms and not any(ft in slug_decoded or ft in t_norm for ft in focus_terms):
                        return False

                # For biography-style requests, enforce identity matching across *all* domains,
                # not just Wikipedia. This prevents similarly named but unrelated pages from
                # slipping in (e.g., "Juan Ponce Enrile" when the request is "Juan Ponce de Leon").
                if biography_request and person_topic_tokens:
                    if person_topic_last and person_topic_last not in page_norm:
                        return False
                    token_hits = sum(1 for tok in person_topic_tokens if tok in page_norm)
                    if token_hits < min(2, len(person_topic_tokens)):
                        return False

                # Prefer keyword overlap, but allow high-quality domains even with low overlap.
                if any(kw in t_norm for kw in keywords[:8]):
                    return True
                if host.endswith(".gov") or host.endswith(".mil") or host.endswith(".edu") or host.endswith(".ac.uk"):
                    return True
                if any(h in host for h in ("loc.gov", "archives.gov", "history.state.gov", "britannica.com", "wikipedia.org", "wikidata.org")):
                    # Wikipedia/Wikidata already handled above; for others we still allow.
                    return "wikipedia.org" not in host and "wikidata.org" not in host
                return False

            def _filter_queries(qs: list[str]) -> list[str]:
                out: list[str] = []
                for q in qs:
                    qq = str(q or "").strip()
                    if not qq:
                        continue
                    # If we get a pure name, contextualize it instead of dropping it entirely.
                    # This keeps Key People grounded (the query still includes the topic context).
                    if _looks_like_person_query(qq) and not re.search(r"\b(biography|life of|born|died)\b", request_lower):
                        ctx: list[str] = []
                        if topic_keywords:
                            ctx.extend(topic_keywords[:2])
                        if focus_terms:
                            ctx.append(focus_terms[0])
                        if ctx:
                            qq = f"{qq} {' '.join(ctx)}"
                    out.append(qq)
                return out

            def _dominant_person_name(titles: list[str]) -> str | None:
                counts: dict[str, int] = {}
                for t in titles:
                    for m in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", t or ""):
                        name = re.sub(r"\s+", " ", m).strip()
                        if len(name) < 6:
                            continue
                        counts[name] = counts.get(name, 0) + 1
                if not counts:
                    return None
                best_name, best_count = max(counts.items(), key=lambda kv: kv[1])
                if best_count >= max(3, int(len(titles) * 0.6)):
                    return best_name
                return None

            def _build_query_plan(topic: str) -> list[str]:
                try:
                    topic_kw = ", ".join(keywords[:8]) if keywords else "(none)"
                    user_message = (
                        "Generate web search queries for a history research task.\n"
                        "Return strict JSON ONLY with keys:\n"
                        "- topic_queries: 5-8 queries focused on the MAIN topic (chronology, key dates, treaties/laws, turning points)\n"
                        "- people_queries: 0-4 queries for important people ONLY if clearly relevant to the topic (avoid biography drift)\n"
                        "Rules:\n"
                        "- Do not invent facts; queries should discover sources.\n"
                        "- Avoid narrowing to one person unless the topic is explicitly biographical.\n\n"
                        f"Topic: {topic}\n"
                        f"Topic keywords: {topic_kw}\n"
                    )
                    plan_res = self._run_llm(
                        context=context,
                        system_prompt=self.system_prompt,
                        user_message=user_message,
                        response_format="json",
                        max_tokens=420,
                        temperature=0.1,
                    )
                    if not plan_res.ok:
                        return []
                    payload = _safe_json(str(plan_res.data.get("text") or ""))
                    if not isinstance(payload, dict):
                        return []
                    tq = payload.get("topic_queries") or []
                    pq = payload.get("people_queries") or []
                    if not isinstance(tq, list):
                        tq = []
                    if not isinstance(pq, list):
                        pq = []
                    out = [str(x).strip() for x in (tq + pq) if str(x).strip()]
                    return out[:16]
                except Exception:
                    return []

            planned = _build_query_plan(query_base)
            planned = _filter_queries(planned)
            biography_request = bool(
                re.search(r"\b(biography|who is|who was|life of)\b", request_lower)
                or (
                    person_topic_name
                    and re.search(r"\b(project|assignment|essay|school)\b", request_lower)
                )
            )
            if biography_request and person_topic_name:
                queries = planned + [
                    f"{person_topic_name} biography",
                    f"{person_topic_name} timeline",
                    f"{person_topic_name} early life and background",
                    f"{person_topic_name} key events",
                    f"{person_topic_name} historical significance",
                    f"{person_topic_name} primary sources",
                    f"{person_topic_name} site:britannica.com",
                    f"{person_topic_name} site:history.com",
                    f"{person_topic_name} site:nationalgeographic.com history",
                    f"{person_topic_name} site:historytoday.com",
                    f"{person_topic_name} site:wikipedia.org",
                ]
            else:
                queries = planned + [
                    f"{query_base} timeline key dates",
                    f"{query_base} chronology",
                    f"{query_base} key dates",
                    f"{query_base} history overview",
                    f"{query_base} key figures leaders",
                    f"{query_base} key people leaders",
                    f"{query_base} major figures",
                    f"{query_base} political leaders",
                    f"{query_base} local leaders",
                    f"{query_base} primary sources",
                    f"{query_base} museum archive",
                    f"{query_base} encyclopedia",
                    f"{query_base} .edu history",
                    f"{query_base} .gov archive",
                    f"{query_base} academic paper history",
                ]

            seen_q: set[str] = set()
            deduped_queries: list[str] = []
            for q in queries:
                qq = str(q or "").strip()
                key = re.sub(r"\s+", " ", qq).strip().lower()
                if not key or key in seen_q:
                    continue
                seen_q.add(key)
                deduped_queries.append(qq)
            queries = deduped_queries

            for query in queries:
                if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                    break
                results = search_web(query, max_results=max_results)
                for result in results:
                    if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                        break
                    url = str(result.get("url") or "")
                    title = str(result.get("title") or url)
                    if not _should_keep_search_hit(title, url, query=query):
                        continue
                    text = fetch_url_text(url, max_chars=8000)
                    if not text:
                        continue
                    if _relevance_score(title, text) < 3:
                        continue
                    add_source(title=title or url, url=url, text=text, origin="web")

            # Drift check: if most sources are weakly related and dominated by a person name, refine once.
            web_records = [r for r in source_records if r.get("origin") == "web"]
            if web_records:
                titles = [str(r.get("title") or "") for r in web_records]
                dominant = _dominant_person_name(titles)
                low_rel = sum(
                    1 for r in web_records if _relevance_score(str(r.get("title") or ""), str(r.get("text") or "")) < 3
                )
                if dominant and low_rel >= max(3, int(len(web_records) * 0.6)):
                    refine_prompt = (
                        "We are getting off-topic sources for a history research task.\n"
                        "Return strict JSON ONLY with key 'queries' (5-8 queries) that refocus on the MAIN TOPIC.\n"
                        "Rules:\n"
                        "- Do not invent facts; queries should discover sources.\n"
                        "- Focus on timelines, key dates, laws/treaties, invasions/occupations, turning points.\n"
                        "- Avoid biography-only results about one person.\n\n"
                        f"Topic: {query_base}\n"
                        f"Dominant name to avoid: {dominant}\n"
                    )
                    refine_res = self._run_llm(
                        context=context,
                        system_prompt=self.system_prompt,
                        user_message=refine_prompt,
                        response_format="json",
                        max_tokens=260,
                        temperature=0.05,
                    )
                    refined: list[str] = []
                    if refine_res.ok:
                        payload = _safe_json(str(refine_res.data.get("text") or ""))
                        if isinstance(payload, dict) and isinstance(payload.get("queries"), list):
                            refined = [str(x).strip() for x in (payload.get("queries") or []) if str(x).strip()]
                    refined = refined[:10]
                    if refined:
                        for query in refined:
                            if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                                break
                            results = search_web(query, max_results=max_results)
                            for result in results:
                                if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                                    break
                                url = str(result.get("url") or "")
                                title = str(result.get("title") or url)
                                if not _should_keep_search_hit(title, url, query=query):
                                    continue
                                text = fetch_url_text(url, max_chars=8000)
                                if not text:
                                    continue
                                if _relevance_score(title, text) < 3:
                                    continue
                                add_source(title=title or url, url=url, text=text, origin="web")

        def _ensure_minimum_history_sources() -> None:
            if not allow_web or not request:
                return
            topic_hint = _extract_topic_hint(request)
            if not topic_hint:
                return
            web_count = len([m for m in source_meta if m.get("origin") == "web"])
            if web_count >= max_results:
                return
            extra_queries = [
                f"{topic_hint} key dates timeline",
                f"{topic_hint} important events chronology",
                f"{topic_hint} major turning points",
                f"{topic_hint} key figures leaders",
                f"{topic_hint} local leaders activists",
                f"{topic_hint} debate perspectives nationalist",
            ]
            for query in extra_queries:
                if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                    break
                results = search_web(query, max_results=max_results)
                for result in results:
                    if len([m for m in source_meta if m.get("origin") == "web"]) >= max_results:
                        break
                    url = str(result.get("url") or "")
                    title = str(result.get("title") or url)
                    if not _should_keep_search_hit(title, url, query=query):
                        continue
                    text = fetch_url_text(url, max_chars=8000)
                    if not text:
                        continue
                    if _relevance_score(title, text) < 3:
                        continue
                    add_source(title=title or url, url=url, text=text, origin="web")

        web_found = len([m for m in source_meta if m.get("origin") == "web"])
        if allow_web and request and web_found == 0 and not biography_request:
            topic_hint = _extract_topic_hint(request)
            fallback_limit = max(min_sources, max_results)
            loc_results = _loc_search(topic_hint, fallback_limit)
            for result in loc_results:
                if len([m for m in source_meta if m.get("origin") == "web"]) >= fallback_limit:
                    break
                url = str(result.get("url") or "")
                title = str(result.get("title") or url)
                if not _should_keep_search_hit(title, url, query=topic_hint):
                    continue
                text = fetch_url_text(url, max_chars=8000)
                if not text:
                    continue
                if _relevance_score(title, text) < 3:
                    continue
                add_source(title=title or url, url=url, text=text, origin="web")

        # Biography-specific fallback: direct high-signal pages. This prevents hard failure when
        # generic search providers return only noise for person-name queries.
        if allow_web and biography_request and person_topic_name:
            web_found = len([m for m in source_meta if m.get("origin") == "web"])
            if web_found == 0:
                base_name = re.sub(r"\s+", " ", str(person_topic_name or "")).strip()
                ascii_name = re.sub(r"\s+", " ", _to_ascii(base_name)).strip()
                wiki = _wiki_page(base_name)
                candidates: list[dict[str, str]] = []
                if wiki:
                    candidates.append(wiki)
                if ascii_name:
                    hyphen = re.sub(r"\s+", "-", ascii_name)
                    underscore = re.sub(r"\s+", "_", ascii_name)
                    candidates.extend(
                        [
                            {"title": f"{base_name} | Britannica", "url": f"https://www.britannica.com/biography/{hyphen}"},
                            {"title": f"{base_name} | History", "url": f"https://www.history.com/articles/{hyphen.lower()}"},
                            {"title": f"{base_name} | World History Encyclopedia", "url": f"https://www.worldhistory.org/{underscore}/"},
                        ]
                    )
                seen_cand: set[str] = set()
                for cand in candidates:
                    if len([m for m in source_meta if m.get("origin") == "web"]) >= max(min_sources, 3):
                        break
                    url = str(cand.get("url") or "").strip()
                    title = str(cand.get("title") or url).strip()
                    if not url or url in seen_cand:
                        continue
                    seen_cand.add(url)
                    if not _should_keep_search_hit(title, url, query=f"{base_name} biography"):
                        continue
                    text = fetch_url_text(url, max_chars=8000)
                    if not text:
                        continue
                    if _relevance_score(title, text) < 2:
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
        validation = _validate_sources(request, len(source_meta), sources)
        source_analysis["validation"] = validation
        proceed = validation.get("proceed")
        # Do not hard-fail biography homework if we have at least one credible source.
        if proceed == "USER_CHOICE" and biography_request and len(source_meta) >= 1:
            proceed = True
            validation = dict(validation or {})
            validation["status"] = "MINIMAL"
            validation["proceed"] = True
            validation["message"] = f"{len(source_meta)} source(s) found for biography topic; proceeding with limited coverage."
            source_analysis["validation"] = validation
        if proceed is False:
            # Hard stop only when we truly cannot proceed (e.g., no sources).
            parsed = {
                "summary": "",
                "context": [],
                "causes": [],
                "consequences": [],
                "timeline": [],
                "key_figures": [],
                "key_events": [],
                "facts": [],
                "source_notes": [],
                "interpretations": [],
                "limitations": [],
                "discussion_questions": [],
                "claims": [],
                "sources": sources,
                "source_meta": source_meta,
                "source_records": source_records,
                "source_analysis": source_analysis,
                "user_request": request,
            }
            return AgentResult(ok=False, message=str(validation.get("message") or "Cannot proceed."), data=parsed)
        if proceed == "USER_CHOICE":
            # We don't currently have a user-choice UI to continue with insufficient sources.
            # Stop here (but include collected sources for debugging/visibility).
            parsed = {
                "summary": "",
                "context": [],
                "causes": [],
                "consequences": [],
                "timeline": [],
                "key_figures": [],
                "key_events": [],
                "facts": [],
                "source_notes": [],
                "interpretations": [],
                "limitations": [],
                "discussion_questions": [],
                "claims": [],
                "sources": sources,
                "source_meta": source_meta,
                "source_records": source_records,
                "source_analysis": source_analysis,
                "user_request": request,
            }
            return AgentResult(ok=False, message=str(validation.get("message") or "Not enough sources."), data=parsed)

        sources_meta_text = "\n".join(
            f"[{m['id']}] {m['title']} | {m.get('url') or 'local'} | type: {m.get('type')}"
            for m in source_meta
        )

        user_msg = (
            f"History topic:\n{request}\n\n"
            "Sources metadata (use these ids for citations):\n"
            f"{sources_meta_text or '(no sources provided)'}\n\n"
            "Source contents:\n"
            f"{source_text or '(no sources provided)'}\n\n"
            "Return strict JSON with keys:\n"
            "- summary (2-3 paragraphs, include citations)\n"
            "- context (list of 4-6 background points with citations)\n"
            "- causes (list of 4-6 causes with citations)\n"
            "- consequences (list of 6-8 outcomes with citations; include specific facts or numbers when possible)\n"
            "- timeline (10-14 specific items with years/dates and citations; no placeholder text)\n"
            "- key_figures (8-12 items; include role + citation; include at least 3 local/colonized voices)\n"
            "- key_events (8-12 items with year + citation)\n"
            "- facts (12-18 items with citations)\n"
            "- source_notes (12-18 short bullets with citations, pulled from the sources)\n"
            "- interpretations (list of 2-3 debates as objects with keys: question, traditional_view, alternative_view; each view must include citations)\n"
            "- limitations (list of 6-10 historical gaps, uncertainties, or areas for further research with citations)\n"
            "- discussion_questions (list of 10-14 critical questions; no citations required)\n"
            "- claims (list of objects: id, text, supporting_sources [ids], contradicting_sources [ids], "
            "flags [DISPUTED, SINGLE_SOURCE], confidence_score 0-100, confidence_label)\n"
            "- sources (list of strings, same ids as above)\n\n"
            "Rules:\n"
            "1) Cite sources with [1], [2] for every factual item.\n"
            "2) Avoid speculation. If uncertain, label as uncertain.\n"
            "3) Prefer primary sources when available (archives, museums, official records).\n"
            "4) Keep items short, specific, and verifiable.\n"
            "5) Only include dates explicitly stated in sources; if uncertain, use the year only.\n"
            "6) Do not repeat the same event with different months or phrasing.\n"
            "7) Use at least 6 different source ids across the output; avoid overusing [1] or [2].\n"
            "8) Include local/regional perspectives in key_figures and notes when relevant.\n"
            "9) Timeline/key_events must list historical events, not publication dates for books or studies.\n"
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="json",
            max_tokens=1800,
            temperature=0.2,
        )
        if not res.ok:
            parsed = {
                "summary": "",
                "context": [],
                "causes": [],
                "consequences": [],
                "timeline": [],
                "key_figures": [],
                "key_events": [],
                "facts": [],
                "source_notes": [],
                "interpretations": [],
                "limitations": [],
                "discussion_questions": [],
                "claims": [],
                "sources": sources,
                "source_meta": source_meta,
                "source_records": source_records,
                "source_analysis": source_analysis,
                "user_request": request,
            }
            return AgentResult(ok=False, message=res.message or "AI call failed.", data=parsed)
        raw = str(res.data.get("text") or "")
        parsed = _safe_json(raw)

        def _needs_repair(payload: Any) -> bool:
            if not isinstance(payload, dict):
                return True
            def _count(key: str) -> int:
                return len(payload.get(key) or [])
            def _looks_like_letters(key: str) -> bool:
                items = payload.get(key) or []
                if not isinstance(items, list) or not items:
                    return False
                short = [str(x).strip() for x in items if str(x).strip()]
                if not short:
                    return False
                one_char = sum(1 for x in short if len(x) == 1)
                return one_char >= max(4, len(short) // 2)
            return (
                _count("timeline") < 6
                or _count("key_events") < 6
                or _count("key_figures") < 6
                or _count("facts") < 8
                or _looks_like_letters("context")
                or _looks_like_letters("causes")
            )

        if _needs_repair(parsed):
            repair_msg = (
                "Your previous response was missing required lists or not valid JSON.\n"
                "Return strict JSON ONLY with the required keys:\n"
                "summary, context, causes, consequences, timeline, key_figures, key_events, facts, "
                "source_notes, interpretations, limitations, discussion_questions, claims, sources.\n"
                "Constraints:\n"
                "- timeline: 10-14 specific items with years/dates and citations.\n"
                "- key_events: 8-12 specific items with years and citations.\n"
                "- key_figures: 8-12 people with role + citation (include local voices).\n"
                "- facts: 12-18 items with citations.\n"
                "- Avoid generic placeholder phrasing like \"establishes a new system\".\n"
                "- Timeline/key_events must list historical events, not publication dates for books or studies.\n"
                "- Use the provided source ids for citations.\n\n"
                f"Sources metadata:\n{sources_meta_text or '(no sources provided)'}\n\n"
                f"Source contents:\n{source_text or '(no sources provided)'}"
            )
            repair_res = self._run_llm(
                context=context,
                system_prompt=self.system_prompt,
                user_message=repair_msg,
                response_format="json",
                max_tokens=1500,
                temperature=0.15,
            )
            if repair_res.ok:
                repaired = _safe_json(str(repair_res.data.get("text") or ""))
                if isinstance(repaired, dict):
                    if not isinstance(parsed, dict):
                        parsed = {}
                    for key in (
                        "summary",
                        "context",
                        "causes",
                        "consequences",
                        "timeline",
                        "key_figures",
                        "key_events",
                        "facts",
                        "source_notes",
                        "interpretations",
                        "limitations",
                        "discussion_questions",
                        "claims",
                        "sources",
                    ):
                        if not parsed.get(key) and repaired.get(key):
                            parsed[key] = repaired.get(key)
        if not parsed:
            parsed = {"summary": raw, "facts": [], "sources": sources}
        # Always prefer the real source list we collected.
        parsed["sources"] = list(sources)
        parsed.setdefault("timeline", [])
        parsed.setdefault("key_figures", [])
        parsed.setdefault("key_events", [])
        parsed.setdefault("facts", [])
        parsed.setdefault("context", [])
        parsed.setdefault("causes", [])
        parsed.setdefault("consequences", [])
        parsed.setdefault("source_notes", [])
        parsed.setdefault("interpretations", [])
        parsed.setdefault("limitations", [])
        parsed.setdefault("discussion_questions", [])
        parsed.setdefault("claims", [])
        parsed["source_meta"] = source_meta
        parsed["source_analysis"] = source_analysis
        parsed["allow_web_research"] = bool(allow_web)
        parsed["web_max_results"] = int(max_results or 5)

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
            if re.search(r"\[\d+\]", text):
                return re.findall(r"\[\d+\]", text)[0]
            return text

        def _is_non_person_entity_name(name: str) -> bool:
            head = _normalize_text(_strip_citations(str(name or ""))).strip()
            if not head:
                return True
            tokens = head.split()
            place_prefixes = {"san", "saint", "st", "new", "fort", "mt", "mount", "lake"}
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
            group_terms = {"people", "citizens", "residents", "population", "community", "communities", "locals", "inhabitants"}
            if any(t in group_terms for t in tokens):
                return True
            if len(tokens) <= 3 and tokens and tokens[-1].endswith(("ans", "ians", "ese", "ites", "ish")):
                return True
            first = tokens[0] if tokens else ""
            return first in {
                "treaty",
                "act",
                "war",
                "battle",
                "campaign",
                "report",
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
                "constitution",
                "law",
                "order",
                "decree",
                "proclamation",
                "empire",
                "kingdom",
                "republic",
                "colony",
                "company",
                "corporation",
                "university",
                "school",
                "church",
                "army",
                "navy",
            }

        def _coerce_person_item(item: Any) -> str:
            if item is None:
                return ""
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("person") or "").strip()
                role = str(item.get("role") or item.get("description") or "").strip()
                citation = _coerce_citation(item.get("citation") or item.get("citations") or item.get("source") or item.get("source_id"))
                # Guard against common JSON failures where "name" is actually a sentence/claim.
                if name:
                    # Strip possessive suffixes that often appear in prose ("McKinley's" -> "McKinley").
                    name = re.sub(r"([A-Za-z])(?:'s|'s)\b", r"\1", name).strip()
                    # Keep only the likely name segment (before punctuation separators).
                    name_head = re.split(r"\s*[-–—:]\s*", name, 1)[0].strip()
                    if (
                        not _is_name_like(name_head)
                        or _is_non_person_entity_name(name_head)
                        or len(_normalize_text(name_head).split()) > 6
                        or re.search(
                            r"\b(began|begins|started|starts|established|establishes|declared|declares|signed|signs|captured|captures|landed|surrender(?:ed|ing|s)?|ceded|cedes|transfer(?:red|ring)|grant(?:ed|ing)|passed|enacted|ratified)\b",
                            _normalize_text(name),
                        )
                    ):
                        return ""
                    name = name_head
                if name and _is_non_person_entity_name(name):
                    return ""
                if name and role:
                    return f"{name} - {role} {citation}".strip()
                if name:
                    return f"{name} {citation}".strip()
                return ""
            text = str(item).strip()
            if not text:
                return ""
            stripped = _strip_citations(text).strip()
            lowered = _normalize_text(stripped)
            # Common failure mode: the model returns bibliographic sentences like
            # "Van Middeldyk's 1903 study..." as a "key figure". For projects, these are not the
            # historical actors; drop them and let the pipeline backfill people from sources.
            if re.match(
                r"^(?P<name>[A-Z][A-Za-z.''\-]+(?:\s+[A-Z][A-Za-z.''\-]+){0,3})['']s\s+(work|book|study|report|account|manual|history)\b",
                stripped,
            ):
                return ""
            # Common failure mode: event/timeline sentences end up in key_figures.
            if lowered.startswith(("the ", "a ", "an ")) or re.search(
                r"\b(began|begins|started|starts|established|establishes|declared|declares|signed|signs|captured|captures|landed|surrender(?:ed|ing|s)?|ceded|cedes|transfer(?:red|ring)|grant(?:ed|ing)|passed|enacted|ratified)\b",
                lowered,
            ):
                return ""
            if re.match(
                r"^\s*(?:\d{4}(?:-\d{4})?|[A-Za-z]+\s+\d{1,2},\s*\d{4}|[A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*[-–—:]",
                stripped,
            ):
                return ""
            head = re.split(r"\s*[-–—:]\s*", stripped, 1)[0].strip()
            if head and _is_non_person_entity_name(head):
                return ""
            if not _is_name_like(stripped):
                return ""
            return text

        def _coerce_event_item(item: Any) -> str:
            if item is None:
                return ""
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
                if head and body:
                    return f"{head} {body} {citation}".strip()
                if head:
                    # Avoid "1898: [5]" type junk (date with no event content).
                    return ""
                if body:
                    return f"{body} {citation}".strip()
                return ""
            return str(item).strip()

        # Normalize any structured JSON items into strings (prevents dict output in downstream sections).
        try:
            if isinstance(parsed.get("key_figures"), list):
                parsed["key_figures"] = [x for x in (_coerce_person_item(i) for i in parsed.get("key_figures") or []) if x]
            if isinstance(parsed.get("key_events"), list):
                parsed["key_events"] = [x for x in (_coerce_event_item(i) for i in parsed.get("key_events") or []) if x]
            if isinstance(parsed.get("timeline"), list):
                parsed["timeline"] = [x for x in (_coerce_event_item(i) for i in parsed.get("timeline") or []) if x]
        except Exception:
            pass
        try:
            parsed["claims"] = _assign_claim_sources(parsed.get("claims") or [], source_records)
        except Exception:
            pass
        try:
            if isinstance(parsed.get("facts"), list):
                parsed["facts"] = _attach_finding_sources(parsed.get("facts") or [], source_records)
        except Exception:
            pass
        try:
            if isinstance(parsed.get("timeline"), list):
                parsed["timeline"] = _attach_finding_sources(parsed.get("timeline") or [], source_records)
        except Exception:
            pass
        parsed["timeline"] = _rebalance_citations(parsed.get("timeline") or [], source_records)
        parsed["key_events"] = _rebalance_citations(parsed.get("key_events") or [], source_records)
        parsed["facts"] = _rebalance_citations(parsed.get("facts") or [], source_records)
        parsed["context"] = _rebalance_citations(parsed.get("context") or [], source_records)
        parsed["causes"] = _rebalance_citations(parsed.get("causes") or [], source_records)
        parsed["consequences"] = _rebalance_citations(parsed.get("consequences") or [], source_records)
        parsed["source_notes"] = _rebalance_citations(parsed.get("source_notes") or [], source_records)
        parsed["key_figures"] = _rebalance_citations(parsed.get("key_figures") or [], source_records)

        def _enrich_key_figures_from_sources() -> None:
            """
            Backfill key_figures from the actual source text when the LLM output is sparse or
            drifts into non-people. This is intentionally conservative:
            - only adds names that appear in source text
            - requires 2+ token proper names
            - avoids obvious bibliographic/author contexts
            """

            if not source_records:
                return
            existing = [str(x).strip() for x in (parsed.get("key_figures") or []) if str(x).strip()]
            if len(existing) >= 8:
                return

            existing_names: set[str] = set()
            for item in existing:
                head = _strip_citations(item).strip()
                head = re.split(r"\s*[-–—:]\s*", head, 1)[0].strip()
                if head:
                    existing_names.add(_normalize_text(head))

            name_re = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b")
            bibliographic_ctx = re.compile(
                r"\b(author|authors|book|study|report|manual|edited|publisher|publication|published)\b",
                re.IGNORECASE,
            )

            additions: list[str] = []
            for record in source_records:
                text = str(record.get("text") or "")
                sid = record.get("id")
                if not text or not isinstance(sid, int) or sid <= 0:
                    continue
                for match in name_re.finditer(text):
                    name = match.group(0).strip()
                    if not name:
                        continue
                    norm = _normalize_text(name)
                    if norm in existing_names:
                        continue
                    if not _is_name_like(name) or _is_non_person_entity_name(name):
                        continue
                    window = text[max(0, match.start() - 80) : match.end() + 80]
                    if bibliographic_ctx.search(window):
                        continue
                    additions.append(f"{name} [{sid}]")
                    existing_names.add(norm)
                    if len(additions) >= 10:
                        break
                if len(additions) >= 10:
                    break

            if additions:
                parsed["key_figures"] = _rebalance_citations(existing + additions, source_records)

        try:
            _enrich_key_figures_from_sources()
        except Exception:
            pass

        def _is_low_information_event_line(item: str) -> bool:
            text = str(item or "").strip()
            if not text:
                return True
            lowered = _normalize_text(text)
            if "source" in lowered and "provides" in lowered:
                return True
            if "background context" in lowered:
                return True
            stripped = _strip_citations(text).strip()
            if stripped.count("(") != stripped.count(")"):
                return True
            if re.fullmatch(
                r"^\s*(?:\(?\s*)?(?:1[5-9]\d{2}|20\d{2})(?:\s*[-–—]{1,2}\s*(?:1[5-9]\d{2}|20\d{2}))?(?:\)?\s*)[-–—:]*\s*$",
                stripped,
            ):
                return True
            if stripped.endswith(("(", "[", "{", "-", "—", "–", ":", ",")):
                return True
            if len(stripped) < 8 and _has_year(stripped):
                return True

            # Drop "blank hole" lines (missing date parts), e.g.:
            # - "began on , when ..."
            # - "served ... from  to May 1900"
            # - "Jones Act of  granted ..."
            # These commonly appear when LLMs try to paraphrase a date but lose the value.
            if re.search(r"\bbegan\s+on\s*,", stripped, flags=re.IGNORECASE):
                return True
            if re.search(r"\bon\s*,\s*(?:when|which)\b", stripped, flags=re.IGNORECASE):
                return True
            if re.search(r"\buntil\s*,\s*(?:when|which)\b", stripped, flags=re.IGNORECASE):
                return True
            if re.search(r"\bfrom\s*(?:,)?\s*to\b", stripped, flags=re.IGNORECASE):
                return True
            if re.search(
                r"\bof\s+(?:granted|passed|signed|enacted|ratified|ceded|transferred)\b",
                stripped,
                flags=re.IGNORECASE,
            ):
                return True
            if re.search(r"\bborn\s+on\s+or\s+after\s*,", stripped, flags=re.IGNORECASE):
                return True
            return False

        def _starts_with_date_prefix(text: str) -> bool:
            month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            return bool(
                re.match(
                    rf"^\s*(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}})\s*[-–—:]\s*",
                    str(text or ""),
                )
            )

        month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        date_pattern = re.compile(
            r"(?P<date>"
            r"(?:\d{4}(?:-\d{4})?)"
            rf"|(?:{month_re}\s+\d{{1,2}},\s*\d{{4}})"
            rf"|(?:{month_re}\s+\d{{4}})"
            rf"|(?:\d{{1,2}}\s+{month_re}\s+\d{{4}})"
            r")"
        )

        def _ensure_date_prefix(value: str) -> str | None:
            text = str(value or "").strip()
            if not text:
                return None
            if _is_publication_line(text) or _is_placeholder_timeline(text):
                return None
            if _is_low_information_event_line(text):
                return None
            if _starts_with_date_prefix(text):
                parts = re.split(r"\s*:\s*", text, 1)
                if len(parts) == 2:
                    rhs = parts[1].strip()
                    rhs = re.sub(r"\b(on|in)\s*,\s*", "", rhs, flags=re.IGNORECASE)
                    rhs = re.sub(r"\b(on|in)\s+(?=and\b)", "", rhs, flags=re.IGNORECASE)
                    rhs = re.sub(r"\buntil\s*,\s*(when|which)\b", r"\1", rhs, flags=re.IGNORECASE)
                    rhs = re.sub(r"\b(on|in)\s*,\s*(when|which)\b", r"\2", rhs, flags=re.IGNORECASE)
                    rhs = re.sub(r"\s{2,}", " ", rhs).strip()
                    if not rhs or _is_low_information_event_line(rhs):
                        return None
                    return f"{parts[0].strip()}: {rhs}"
                return text
            if not _has_year(text):
                return None
            # Common phrasing: "from 1899 to 1900 ..." should become a range prefix.
            from_to = re.search(r"\bfrom\s+(?P<y1>\d{4})\s+to\s+(?P<y2>\d{4})\b", text, flags=re.IGNORECASE)
            if from_to:
                y1 = from_to.group("y1")
                y2 = from_to.group("y2")
                remainder = (text[: from_to.start()] + text[from_to.end() :]).strip()
                remainder = remainder.lstrip(" ,;:-—–").strip()
                remainder = re.sub(r"\b(on|in)\s*,\s*", "", remainder, flags=re.IGNORECASE)
                remainder = re.sub(r"\b(on|in)\s+(?=and\b)", "", remainder, flags=re.IGNORECASE)
                remainder = re.sub(r"\buntil\s*,\s*(when|which)\b", r"\1", remainder, flags=re.IGNORECASE)
                remainder = re.sub(r"\b(on|in)\s*,\s*(when|which)\b", r"\2", remainder, flags=re.IGNORECASE)
                remainder = re.sub(
                    r"\bAct\s+of\s+(?=(?:granted|passed|signed|enacted|ratified|ceded|transferred)\b)",
                    "Act ",
                    remainder,
                    flags=re.IGNORECASE,
                )
                remainder = re.sub(
                    r"\bof\s+(?=(?:granted|passed|signed|enacted|ratified|ceded|transferred)\b)",
                    "",
                    remainder,
                    flags=re.IGNORECASE,
                )
                remainder = re.sub(r"\s{2,}", " ", remainder).strip()
                if not remainder or _is_low_information_event_line(remainder):
                    return None
                return f"{y1}–{y2}: {remainder}"
            # Handle leading date ranges like "Oct 1898 – Dec 9, 1898: ...".
            range_match = re.match(
                rf"^\s*(?P<d1>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[-–—]{{1,2}}\s*(?P<d2>(?:\d{{4}}(?:-\d{{4}})?|{month_re}\s+\d{{1,2}},\s*\d{{4}}|{month_re}\s+\d{{4}}|\d{{1,2}}\s+{month_re}\s+\d{{4}}))\s*[-–—:]\s*(?P<rest>.+)$",
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
            remainder = re.sub(r"\b(on|in)\s*,\s*", "", remainder, flags=re.IGNORECASE)
            remainder = re.sub(r"\b(on|in)\s+(?=and\b)", "", remainder, flags=re.IGNORECASE)
            remainder = re.sub(r"\buntil\s*,\s*(when|which)\b", r"\1", remainder, flags=re.IGNORECASE)
            remainder = re.sub(r"\b(on|in)\s*,\s*(when|which)\b", r"\2", remainder, flags=re.IGNORECASE)
            remainder = re.sub(
                r"\bAct\s+of\s+(?=(?:granted|passed|signed|enacted|ratified|ceded|transferred)\b)",
                "Act ",
                remainder,
                flags=re.IGNORECASE,
            )
            remainder = re.sub(
                r"\bof\s+(?=(?:granted|passed|signed|enacted|ratified|ceded|transferred)\b)",
                "",
                remainder,
                flags=re.IGNORECASE,
            )
            remainder = re.sub(r"\s{2,}", " ", remainder).strip()
            if not remainder or _is_low_information_event_line(remainder):
                return None
            return f"{date}: {remainder}"

        def _has_action_verb(text: str) -> bool:
            lowered = _normalize_text(text)
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
                "started",
                "starts",
                "landed",
                "invaded",
                "occupied",
                "attacked",
                "bombarded",
                "captured",
                "seized",
                "took",
                "took over",
                "took control",
                "lowered",
                "raised",
                "surrender",
                "surrendered",
                "suspended",
                "ceded",
                "transferred",
                "appointed",
                "served",
                "serves",
                "established",
                "created",
                "granted",
                "formed",
            ]
            return any(v in lowered for v in verbs)
        parsed["key_events"] = [
            item
            for item in (parsed.get("key_events") or [])
            if not _is_placeholder_timeline(item) and not _is_publication_line(item) and not _is_low_information_event_line(item)
        ]

        def _drop_too_short(items: list[str], *, min_len: int) -> list[str]:
            out: list[str] = []
            for item in items or []:
                text = str(item or "").strip()
                if not text:
                    continue
                if len(text) < min_len and not _has_year(text):
                    continue
                out.append(text)
            return out

        parsed["context"] = _drop_too_short(_dedupe_list(parsed.get("context"), max_items=10), min_len=10)
        parsed["causes"] = _drop_too_short(_dedupe_list(parsed.get("causes"), max_items=10), min_len=10)
        parsed["consequences"] = _drop_too_short(_dedupe_list(parsed.get("consequences"), max_items=10), min_len=10)
        parsed["facts"] = _drop_too_short(_dedupe_list(parsed.get("facts"), max_items=22), min_len=12)
        parsed["source_notes"] = _drop_too_short(_dedupe_list(parsed.get("source_notes"), max_items=22), min_len=12)

        source_ids = [int(m.get("id")) for m in source_meta if m.get("id")]
        usage: dict[int, int] = {}
        event_candidates = _extract_event_sentences(source_records)
        normalized_timeline: list[str] = []
        for t in _dedupe_list(parsed.get("timeline"), key_func=_event_key, max_items=22):
            normalized = _ensure_date_prefix(t) or t
            normalized_timeline.append(normalized)
        timeline_items = [
            t
            for t in _dedupe_list(normalized_timeline, key_func=_event_key, max_items=18)
            if _has_year(t)
            and _starts_with_date_prefix(t)
            and _has_event_keyword(t)
            and _has_action_verb(t)
            and not _is_placeholder_timeline(t)
            and not _is_publication_line(t)
            and not _is_low_information_event_line(t)
        ]
        # Sort and limit per year (avoid repeated 1899/1900 spam).
        timeline_items = sorted(timeline_items, key=lambda x: (_extract_year(x) or 9999, -_timeline_score(x)))
        filtered_timeline: list[str] = []
        year_counts: dict[int, int] = {}
        def _token_set(text: str) -> set[str]:
            base = _normalize_text(_strip_citations(text))
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

        def _is_near_duplicate_timeline(candidate: str) -> bool:
            cand_set = _token_set(candidate)
            if not cand_set:
                return False
            for existing in filtered_timeline:
                ex_set = _token_set(existing)
                if not ex_set:
                    continue
                inter = len(cand_set & ex_set)
                union = len(cand_set | ex_set)
                if union and (inter / union) >= 0.85:
                    return True
            return False

        for item in timeline_items:
            year = _extract_year(item)
            if year is None:
                continue
            # Allow multiple events in the same year (many history topics cluster key events),
            # but cap to avoid "same-year spam" regressions.
            if year_counts.get(year, 0) >= 3:
                continue
            if _is_near_duplicate_timeline(item):
                continue
            year_counts[year] = year_counts.get(year, 0) + 1
            filtered_timeline.append(item)
        parsed["timeline"] = filtered_timeline[:14]

        # Backfill timeline from extracted event candidates if too short.
        if len(parsed["timeline"]) < 8:
            pool = [
                p
                for p in event_candidates
                if _has_year(p)
                and (_ensure_date_prefix(p) is not None or _starts_with_date_prefix(p))
                and _has_event_keyword(p)
                and _has_action_verb(p)
                and not _is_placeholder_timeline(p)
                and not _is_publication_line(p)
                and not _is_low_information_event_line(p)
            ]
            pool = sorted(pool, key=lambda x: (_extract_year(x) or 9999, -_timeline_score(x)))
            for item in pool:
                if len(parsed["timeline"]) >= 10:
                    break
                item = _ensure_date_prefix(item) or item
                year = _extract_year(item)
                if year is None:
                    continue
                if year_counts.get(year, 0) >= 3:
                    continue
                parsed["timeline"].append(item)
                year_counts[year] = year_counts.get(year, 0) + 1

        # Backfill timeline from other dated lists if still too short.
        if len(parsed["timeline"]) < 8:
            pool = []
            for key in ("key_events", "facts", "source_notes", "context", "causes", "consequences"):
                pool.extend(parsed.get(key) or [])
            pool = [
                p
                for p in pool
                if _has_year(p)
                and (_ensure_date_prefix(p) is not None or _starts_with_date_prefix(p))
                and _has_event_keyword(p)
                and _has_action_verb(p)
                and not _is_placeholder_timeline(p)
                and not _is_publication_line(p)
                and not _is_low_information_event_line(p)
            ]
            pool = _dedupe_list(pool, key_func=_event_key, max_items=20)
            pool = sorted(pool, key=lambda x: (_extract_year(x) or 9999, -_timeline_score(x)))
            for item in pool:
                if len(parsed["timeline"]) >= 10:
                    break
                item = _ensure_date_prefix(item) or item
                year = _extract_year(item)
                if year is None:
                    continue
                if year_counts.get(year, 0) >= 3:
                    continue
                parsed["timeline"].append(item)
                year_counts[year] = year_counts.get(year, 0) + 1

        # If the timeline is still too short, fetch additional high-signal "key dates" sources and retry once.
        if allow_web and request and len(parsed.get("timeline") or []) < 8:
            before_sources = len(source_records)
            _ensure_minimum_history_sources()
            if len(source_records) > before_sources:
                event_candidates = _extract_event_sentences(source_records)
                normalized_timeline = []
                for t in _dedupe_list(parsed.get("timeline"), key_func=_event_key, max_items=22):
                    normalized_timeline.append(_ensure_date_prefix(t) or t)
                timeline_items = [
                    t
                    for t in _dedupe_list(normalized_timeline, key_func=_event_key, max_items=18)
                    if _has_year(t)
                    and _starts_with_date_prefix(t)
                    and _has_event_keyword(t)
                    and _has_action_verb(t)
                    and not _is_placeholder_timeline(t)
                    and not _is_publication_line(t)
                    and not _is_low_information_event_line(t)
                ]
                timeline_items.extend(
                    [
                        (_ensure_date_prefix(p) or p)
                        for p in _dedupe_list(event_candidates, key_func=_event_key, max_items=22)
                        if _has_year(p)
                        and (_ensure_date_prefix(p) is not None or _starts_with_date_prefix(p))
                        and _has_event_keyword(p)
                        and _has_action_verb(p)
                        and not _is_placeholder_timeline(p)
                        and not _is_publication_line(p)
                        and not _is_low_information_event_line(p)
                    ]
                )
                timeline_items = _dedupe_list(timeline_items, key_func=_event_key, max_items=24)
                timeline_items = sorted(timeline_items, key=lambda x: (_extract_year(x) or 9999, -_timeline_score(x)))
                filtered_timeline = []
                year_counts = {}
                for item in timeline_items:
                    item = _ensure_date_prefix(item) or item
                    year = _extract_year(item)
                    if year is None:
                        continue
                    if year_counts.get(year, 0) >= 3:
                        continue
                    year_counts[year] = year_counts.get(year, 0) + 1
                    filtered_timeline.append(item)
                    if len(filtered_timeline) >= 14:
                        break
                parsed["timeline"] = filtered_timeline

        # Ensure Key Events is populated with real historical events (not book/publication dates).
        # Writer can fall back to timeline, but having a dedicated list improves structure and scoring.
        def _build_key_events() -> list[str]:
            candidates: list[str] = []
            candidates.extend([str(x) for x in (parsed.get("key_events") or []) if x])
            candidates.extend([str(x) for x in (parsed.get("timeline") or []) if x])
            candidates.extend(event_candidates or [])
            # As a last resort, mine other lists that often contain dated facts.
            for key in ("facts", "source_notes", "context", "causes", "consequences"):
                candidates.extend([str(x) for x in (parsed.get(key) or []) if x])

            normalized: list[str] = []
            for c in candidates:
                pref = _ensure_date_prefix(c) or c
                normalized.append(pref)

            filtered = [
                c
                for c in _dedupe_list(normalized, key_func=_event_key, max_items=40)
                if _has_year(c)
                and (_starts_with_date_prefix(c) or _ensure_date_prefix(c) is not None)
                and _has_event_keyword(c)
                and _has_action_verb(c)
                and not _is_placeholder_timeline(c)
                and not _is_publication_line(c)
                and not _is_low_information_event_line(c)
            ]
            filtered = sorted(filtered, key=lambda x: (_extract_year(x) or 9999, -_timeline_score(x)))
            out: list[str] = []
            year_counts: dict[int, int] = {}

            def _token_set(text: str) -> set[str]:
                base = _normalize_text(_strip_citations(text))
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
                cand_set = _token_set(candidate)
                if not cand_set:
                    return False
                for existing in out:
                    ex_set = _token_set(existing)
                    if not ex_set:
                        continue
                    inter = len(cand_set & ex_set)
                    union = len(cand_set | ex_set)
                    if union and (inter / union) >= 0.85:
                        return True
                return False

            for item in filtered:
                item = _ensure_date_prefix(item) or item
                year = _extract_year(item)
                if year is None:
                    continue
                if year_counts.get(year, 0) >= 3:
                    continue
                if _is_near_duplicate(item):
                    continue
                year_counts[year] = year_counts.get(year, 0) + 1
                out.append(item)
                if len(out) >= 12:
                    break
            return out

        parsed["key_events"] = _build_key_events()

        def _looks_like_person_entry(line: str) -> bool:
            text = _strip_citations(str(line or "")).strip()
            if not text:
                return False
            if "[uncertain]" in text.lower():
                return False
            # Require a source citation on all Key People entries to prevent hallucination.
            if not re.search(r"\[\d+\]", str(line or "")):
                return False
            # Reject obvious non-name filler tokens (prepositions/determiners) that can sneak in
            # when a model outputs "Topic From" / "X Of" style fragments.
            stop_name_tokens = {
                "a",
                "an",
                "and",
                "as",
                "at",
                "by",
                "during",
                "for",
                "from",
                "in",
                "into",
                "near",
                "of",
                "on",
                "over",
                "the",
                "to",
                "under",
                "with",
                "without",
            }
            # Prefer structured "Name - role" entries (produced by our extractors).
            if re.search(r"\s+(?:—|–|---|--|-)\s+", text):
                name_part = re.split(r"\s+(?:—|–|---|--|-)\s+", text, 1)[0].strip()
                return _is_name_like(name_part)
            # Possessives like "Puerto Rico's" are not people.
            if re.search(r"['']s\b", text):
                return False
            # Allow bare names (2-4 tokens) to avoid empty lists, but reject sentence-like lines.
            if re.search(r"[.?!]$", text):
                return False
            lowered = _normalize_text(text)
            if re.search(r"\b(treaty|act|law|war|campaign|report|manual|hearing)\b", lowered):
                return False
            if re.search(
                r"\b(committee|commission|department|ministry|bureau|division|office|board|council|congress|parliament|senate|army|navy|government|administration|university|school|company|corporation|contents|table|editor|editors|updated|last|chatbot|britannica|ask|anything)\b",
                lowered,
            ):
                return False
            tokens = [t for t in re.split(r"\s+", text) if t]
            if not (2 <= len(tokens) <= 4):
                return False
            if any(t.strip(".").lower() in stop_name_tokens for t in tokens):
                return False
            # Reject common ship/vehicle prefixes (not individuals).
            first = tokens[0].rstrip(".").upper()
            if first in {"USS", "U.S.S", "HMS", "SS", "MS"}:
                return False
            # Filter demonyms/group labels like "Puerto Rican" / "American" (not individuals).
            if tokens and tokens[-1].lower().endswith(("ans", "ians", "ese", "ites", "ish", "ican")):
                return False
            # Organizations are a frequent failure mode in "Key People".
            if re.search(r"\b(national\s+guard|guard)\b", _normalize_text(text)):
                return False
            # Reject all-caps abbreviations (e.g., "AM ET", "PM ET", "US Rule" headers).
            upper_short = [t for t in tokens if t.isupper() and len(t) <= 4]
            if len(upper_short) >= max(2, len(tokens) - 1):
                return False
            return all(re.match(r"^[A-Z][A-Za-z.''\\-]*$", t) for t in tokens)

        parsed["key_figures"] = [
            item
            for item in (parsed.get("key_figures") or [])
            if item and not _is_generic_person(item) and _looks_like_person_entry(str(item))
        ]
        parsed["key_figures"] = _dedupe_list(parsed.get("key_figures"), key_func=_person_key, max_items=14)

        def _norm_match(text: str) -> str:
            t = str(text or "")
            try:
                t = unicodedata.normalize("NFKD", t)
                t = "".join(ch for ch in t if not unicodedata.combining(ch))
            except Exception:
                pass
            t = t.lower()
            t = re.sub(r"[^a-z0-9]+", " ", t)
            return re.sub(r"\s+", " ", t).strip()

        def _extract_years(text: str) -> list[int]:
            years: list[int] = []
            for m in re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(text or "")):
                try:
                    years.append(int(m))
                except Exception:
                    continue
            return years

        def _has_event_focus(req: str) -> bool:
            r = _normalize_text(req)
            return bool(
                re.search(
                    r"\b(invasion|invade|invaded|occupation|occupied|takeover|take over|took over|took control|annex|annexation|cession|cede|ceded|transfer|transferred|treaty|war|campaign|battle|armistice|surrender)\b",
                    r,
                )
            )

        def _actor_terms(req: str) -> list[str]:
            req_norm = _normalize_text(req)
            terms: list[str] = []
            if "united states" in req_norm:
                terms.append("united states")
            if "american" in req_norm:
                terms.append("american")
            if re.search(r"\bu s\b", req_norm):
                terms.append("u s")
            return terms

        def _topic_terms(req: str) -> list[str]:
            req_norm = _normalize_text(req)
            stop = {
                "a",
                "an",
                "and",
                "as",
                "at",
                "be",
                "by",
                "can",
                "did",
                "do",
                "does",
                "for",
                "from",
                "has",
                "have",
                "how",
                "in",
                "into",
                "is",
                "it",
                "of",
                "on",
                "or",
                "over",
                "the",
                "to",
                "was",
                "were",
                "what",
                "when",
                "which",
                "who",
                "why",
                "with",
            }
            focus_words = {
                "invasion",
                "invade",
                "invaded",
                "occupation",
                "occupied",
                "takeover",
                "take",
                "took",
                "control",
                "war",
                "campaign",
                "battle",
                "treaty",
                "armistice",
                "surrender",
                "annex",
                "annexation",
                "cession",
                "cede",
                "ceded",
                "transfer",
                "transferred",
            }
            terms: list[str] = []
            for w in req_norm.split():
                if len(w) < 4:
                    continue
                if w in stop or w in focus_words:
                    continue
                if w not in terms:
                    terms.append(w)
                if len(terms) >= 8:
                    break
            return terms

        def _derive_focus_triggers(req: str) -> tuple[list[str], list[str]]:
            req_norm = _normalize_text(req)
            strong: set[str] = set()
            weak: set[str] = set()

            strong |= {
                "treaty",
                "agreement",
                "protocol",
                "signed",
                "ratified",
                "act",
                "bill",
                "law",
                "constitution",
                "congress",
                "senate",
                "parliament",
                "military government",
                "military rule",
                "civil government",
                "civilian government",
                "civilian",
                "administration",
                "governor",
                "occupation",
                "occupied",
                "annex",
                "annexation",
                "cession",
                "cede",
                "ceded",
                "transfer",
                "transferred",
                "armistice",
                "surrender",
                "landing",
                "landed",
                "troops",
                "invasion",
                "invade",
                "invaded",
                "seized",
                "seize",
                "captured",
                "capture",
            }
            weak |= {"war", "campaign", "battle", "takeover", "take over", "took over", "took control"}

            if any(w in req_norm for w in ("occupation", "occupied")):
                strong |= {"rule", "military", "civil", "governance"}
            if any(w in req_norm for w in ("invasion", "invade", "invaded", "takeover", "took over", "take over")):
                strong |= {"attack", "assault", "land", "landing", "landed", "armistice", "surrender", "treaty"}
            if "treaty" in req_norm:
                strong |= {"agreement", "signed", "ratified", "protocol"}
            if any(w in req_norm for w in ("annex", "annexation", "cession", "cede", "ceded", "transfer", "transferred")):
                strong |= {"sovereignty", "territory", "colonial", "protectorate"}

            strong_list = sorted(strong, key=lambda x: (-len(x), x))
            weak_list = sorted([w for w in weak if w not in strong], key=lambda x: (-len(x), x))
            return strong_list, weak_list

        def _build_focus_window(records: list[dict[str, Any]], req: str) -> tuple[int, int] | None:
            if not records or not _has_event_focus(req):
                return None

            strong_triggers, weak_triggers = _derive_focus_triggers(req)
            topic_terms = _topic_terms(req)
            actor_terms = _actor_terms(req)
            triggers = list(dict.fromkeys([*strong_triggers, *weak_triggers]))

            def _trigger_positions(text: str) -> list[int]:
                positions: list[int] = []
                for trig in triggers:
                    if not trig:
                        continue
                    start = 0
                    while True:
                        idx = text.find(trig, start)
                        if idx < 0:
                            break
                        positions.append(idx)
                        start = idx + max(1, len(trig))
                return positions

            def _year_positions(text: str) -> list[tuple[int, int]]:
                # Return (year, position) pairs.
                out: list[tuple[int, int]] = []
                for m in re.finditer(r"(?<!\d)(?:1[0-9]{3}|20[0-9]{2})(?!\d)", text):
                    try:
                        out.append((int(m.group(0)), m.start()))
                    except Exception:
                        continue
                return out

            def _select_years_near_triggers(text: str, years: list[int]) -> list[int]:
                if not years:
                    return []
                if len(years) <= 1:
                    return years
                lower = text.lower()
                trig_pos = _trigger_positions(lower)
                year_pos = _year_positions(lower)
                if not trig_pos or not year_pos:
                    return years[:2]

                scored: list[tuple[int, int]] = []
                year_set = set(years)
                for y, pos in year_pos:
                    if y not in year_set:
                        continue
                    dist = min(abs(pos - tp) for tp in trig_pos) if trig_pos else 10_000
                    scored.append((dist, y))
                if not scored:
                    return years[:2]
                scored.sort(key=lambda x: (x[0], x[1]))
                picked: list[int] = []
                for _, y in scored:
                    if y not in picked:
                        picked.append(y)
                    if len(picked) >= 2:
                        break
                return picked or years[:2]

            year_sources_total: dict[int, set[int]] = {}
            year_weights: dict[int, int] = {}

            for rec in records:
                try:
                    sid = int(rec.get("id"))
                except Exception:
                    continue
                blob = str(rec.get("text") or "")
                if not blob:
                    continue
                sentences = re.split(r"(?<=[.!?])\s+|\n+", blob)
                for sent in sentences:
                    s = " ".join(str(sent or "").split()).strip()
                    if not s or len(s) < 25:
                        continue
                    s_norm = _normalize_text(s)

                    # If the request includes an explicit actor like "United States", constrain
                    # the focus window to sentences that mention that actor. This avoids drifting
                    # to centuries of unrelated background history in long "military history" sources.
                    if actor_terms and not any(a in s_norm for a in actor_terms):
                        continue

                    if topic_terms and not any(tt in s_norm for tt in topic_terms):
                        continue

                    yrs = _extract_years(s)
                    if not yrs:
                        continue

                    weight = 0
                    if any(t in s_norm for t in strong_triggers):
                        weight += 2
                    if any(t in s_norm for t in weak_triggers):
                        weight += 1
                    if weight <= 0:
                        continue
                    yrs_for_weight = _select_years_near_triggers(s, yrs)
                    for y in yrs_for_weight:
                        year_sources_total.setdefault(y, set()).add(sid)
                        year_weights[y] = year_weights.get(y, 0) + weight

            if not year_sources_total:
                return None

            scored_years: dict[int, int] = {}
            for y, srcs in year_sources_total.items():
                support = len(srcs)
                scored_years[y] = (year_weights.get(y, 0) * 10) + support

            years_sorted = sorted(scored_years.keys())
            window_size = 35
            best_sum = -1
            best_start = years_sorted[0]
            for start in years_sorted:
                end = start + window_size
                total = 0
                for y in years_sorted:
                    if y < start:
                        continue
                    if y > end:
                        break
                    total += scored_years.get(y, 0)
                if total > best_sum:
                    best_sum = total
                    best_start = start
            return best_start - 3, best_start + window_size + 3

        def _build_focus_text_by_id(records: list[dict[str, Any]], req: str) -> dict[int, str]:
            window = _build_focus_window(records, req)
            if not window:
                return {}
            w_min, w_max = window
            strong_triggers, weak_triggers = _derive_focus_triggers(req)
            topic_terms = _topic_terms(req)
            actor_terms = _actor_terms(req)

            triggers = list(dict.fromkeys([*strong_triggers, *weak_triggers]))

            out: dict[int, str] = {}
            for rec in records:
                try:
                    sid = int(rec.get("id"))
                except Exception:
                    continue
                blob = str(rec.get("text") or "")
                if not blob:
                    continue
                sentences = re.split(r"(?<=[.!?])\s+|\n+", blob)
                keep: list[str] = []
                for idx, sent in enumerate(sentences):
                    s = " ".join(str(sent or "").split()).strip()
                    if not s or len(s) < 25:
                        continue
                    s_norm = _normalize_text(s)
                    if topic_terms and not any(tt in s_norm for tt in topic_terms):
                        continue
                    yrs = _extract_years(s)
                    in_window = any((w_min <= y <= w_max) for y in yrs) if yrs else False
                    has_trigger = any(t in s_norm for t in triggers)
                    actor_ok = (not actor_terms) or any(a in s_norm for a in actor_terms)
                    if in_window:
                        pass
                    elif has_trigger and actor_ok:
                        pass
                    else:
                        continue

                    for j in (idx - 1, idx, idx + 1):
                        if 0 <= j < len(sentences):
                            neighbor = " ".join(str(sentences[j] or "").split()).strip()
                            if neighbor and len(neighbor) >= 25:
                                keep.append(neighbor)
                    if len(keep) >= 90:
                        break
                focus_text = "\n".join(keep).strip()
                if focus_text:
                    out[sid] = focus_text
            return out

        def _gate_key_figures_to_focus(
            key_figures: list[str], records: list[dict[str, Any]], req: str
        ) -> list[str]:
            if not key_figures or not records or not _has_event_focus(req):
                return key_figures

            focus_text_by_id = _build_focus_text_by_id(records, req)
            if not focus_text_by_id:
                return key_figures

            def _citation_ids(item: str) -> list[int]:
                return [int(m) for m in re.findall(r"\[(\d+)\]", str(item or ""))]

            def _name_in_focus(name: str, ids: list[int]) -> bool:
                nm = _norm_match(name)
                if not nm:
                    return False
                needle = f" {nm} "
                for sid in ids:
                    blob = focus_text_by_id.get(int(sid), "")
                    if not blob:
                        continue
                    blob_norm = _norm_match(blob)
                    if needle in f" {blob_norm} ":
                        return True
                return False

            gated: list[str] = []
            for item in list(key_figures or []):
                item_text = str(item or "").strip()
                ids = _citation_ids(item_text)
                if not ids:
                    continue
                head = _strip_citations(item_text).strip()
                head = re.split(r"\s*(?:—|–|--+|-|:)\s*", head, 1)[0].strip()
                if not head:
                    continue
                if _name_in_focus(head, ids):
                    gated.append(item_text)

            # Prefer returning a small focused set; later steps can backfill from other sources.
            if gated:
                return _dedupe_list(gated, key_func=_person_key, max_items=14)
            # If we have a focus window but none of the LLM-provided names appear in it,
            # discard them so backfill can repopulate from focused excerpts.
            if focus_text_by_id:
                return []
            return key_figures

        if source_records and parsed.get("key_figures"):
            parsed["key_figures"] = _gate_key_figures_to_focus(
                list(parsed.get("key_figures") or []),
                source_records,
                request,
            )

        # If the request is event-focused (takeover/occupation/etc.), restrict timeline/key events to the
        # derived focus window and then backfill only from in-window candidates. This prevents drifting
        # to centuries of unrelated background history.
        focus_window = _build_focus_window(source_records, request) if source_records else None
        if focus_window and source_records:
            w_min, w_max = focus_window

            def _in_window_years(text: str) -> bool:
                yrs = _extract_years(str(text or ""))
                return any((w_min <= y <= w_max) for y in yrs) if yrs else False

            parsed["timeline"] = [t for t in (parsed.get("timeline") or []) if _in_window_years(t)]
            parsed["key_events"] = [e for e in (parsed.get("key_events") or []) if _in_window_years(e)]

            # Backfill timeline from extracted candidates, but only within the window.
            if len(parsed.get("timeline") or []) < 8:
                pool = [
                    p
                    for p in (event_candidates or [])
                    if _in_window_years(p)
                    and _has_year(p)
                    and (_ensure_date_prefix(p) is not None or _starts_with_date_prefix(p))
                    and _has_event_keyword(p)
                    and _has_action_verb(p)
                    and not _is_placeholder_timeline(p)
                    and not _is_publication_line(p)
                    and not _is_low_information_event_line(p)
                ]
                pool = _dedupe_list(pool, key_func=_event_key, max_items=22)
                pool = sorted(pool, key=lambda x: (_extract_year(x) or 9999, -_timeline_score(x)))
                for item in pool:
                    if len(parsed.get("timeline") or []) >= 10:
                        break
                    item = _ensure_date_prefix(item) or item
                    if item and item not in (parsed.get("timeline") or []):
                        parsed["timeline"] = (parsed.get("timeline") or []) + [item]

            # Backfill key events from in-window candidates if empty/short.
            if len(parsed.get("key_events") or []) < 4:
                event_pool = [
                    p
                    for p in (event_candidates or [])
                    if _in_window_years(p)
                    and not _is_placeholder_timeline(p)
                    and not _is_publication_line(p)
                    and not _is_low_information_event_line(p)
                ]
                event_pool = _dedupe_list(event_pool, key_func=_event_key, max_items=22)
                parsed["key_events"] = _dedupe_list(
                    (parsed.get("key_events") or []) + event_pool, key_func=_event_key, max_items=10
                )

        # If extraction under-delivered, pull key people from ALL sources (not just the first one).
        if len(parsed.get("key_figures") or []) < 6 and source_records:
            extracted_people: list[str] = []
            import unicodedata

            def _fold_text(text: str) -> str:
                # Lowercase, strip punctuation-ish spacing, and remove diacritics for robust substring checks.
                s = str(text or "").lower()
                s = unicodedata.normalize("NFKD", s)
                s = "".join(ch for ch in s if not unicodedata.combining(ch))
                return re.sub(r"\s+", " ", s).strip()

            def _name_in_text(full_text: str, name: str) -> bool:
                n = _fold_text(name)
                if not n or len(n) < 4:
                    return False
                return n in _fold_text(full_text)

            focus_text_by_id = _build_focus_text_by_id(source_records, request) if source_records else {}
            for src in source_records:
                sid = src.get("id")
                sample = str(focus_text_by_id.get(int(sid), "") or src.get("text") or "")
                if not sample.strip():
                    continue
                # Keep prompts small; we only need named people + role hints.
                sample = sample.strip()
                if len(sample) > 3500:
                    sample = sample[:3500]
                people_prompt = (
                    "Extract people mentioned in this source (prioritize local/regional figures when available).\n"
                    "Return strict JSON ONLY with the shape:\n"
                    "{ \"people\": [ {\"name\": \"...\", \"role\": \"...\"} ] }\n"
                    "Rules:\n"
                    "- 0 to 5 people.\n"
                    "- Use real names found in the text.\n"
                    "- Only include individuals (NOT countries, places, organizations, laws, wars).\n"
                    "- role should be a short phrase (e.g. 'U.S. general', 'journalist', 'local political leader').\n"
                    "- Do not invent names.\n\n"
                    "Example:\n"
                    "{ \"people\": [ {\"name\": \"Ada Lovelace\", \"role\": \"mathematician\"} ] }\n\n"
                    f"Source ID for citation: {sid}\n"
                    f"Source text:\n{sample}"
                )
                llm_res = self._run_llm(
                    context=context,
                    system_prompt=self.system_prompt,
                    user_message=people_prompt,
                    response_format="json",
                    max_tokens=450,
                    temperature=0.0,
                )
                if not llm_res.ok:
                    continue
                payload = _safe_json(str(llm_res.data.get("text") or ""))
                people_list = []
                if isinstance(payload, dict):
                    people_list = payload.get("people") or []
                if not isinstance(people_list, list):
                    continue
                full_text = str(src.get("text") or "")
                for p in people_list:
                    line = _coerce_person_item(p)
                    if not line:
                        continue
                    # Enforce "no hallucinated people": require the extracted name appears in the source text.
                    try:
                        extracted_name = re.split(r"\s*[-–—]\s*", _strip_citations(line), 1)[0].strip()
                    except Exception:
                        extracted_name = ""
                    if extracted_name and full_text and not _name_in_text(full_text, extracted_name):
                        continue
                    if sid and not re.search(r"\[\d+\]", line):
                        line = f"{line} [{sid}]"
                    extracted_people.append(line.strip())
            if extracted_people:
                merged = (parsed.get("key_figures") or []) + extracted_people
                merged = [m for m in merged if m and not _is_generic_person(m)]
                parsed["key_figures"] = _dedupe_list(merged, key_func=_person_key, max_items=14)

        # Final fallback: heuristic extraction of titled names (prevents empty Key People sections).
        if len(parsed.get("key_figures") or []) < 6 and source_records:
            titled_people: list[str] = []
            title_patterns = [
                r"president",
                r"prime minister",
                r"governor",
                r"general",
                r"admiral",
                r"senator",
                r"minister",
                r"secretary",
                r"king",
                r"queen",
                r"emperor",
                r"pope",
                r"bishop",
                r"dr\.?|doctor",
                r"prof\.?|professor",
                r"judge",
            ]
            token = r"[^\W\d_](?:[^\W\d_]|[.'’\-]){0,23}"
            title_re = re.compile(
                rf"\b(?P<title>{'|'.join(title_patterns)})\s+(?P<name>{token}(?:\s+{token}){{1,3}})\b",
                flags=re.IGNORECASE,
            )
            for src in source_records:
                sid = src.get("id")
                text = str(src.get("text") or "")
                if not text:
                    continue
                for match in title_re.finditer(text):
                    name = match.group("name").strip()
                    title = match.group("title").strip()
                    if not name or not _is_name_like(name):
                        continue
                    role = title.title()
                    line = f"{name} - {role}"
                    if sid:
                        line = f"{line} [{sid}]"
                    titled_people.append(line)
            if titled_people:
                merged = (parsed.get("key_figures") or []) + titled_people
                merged = [m for m in merged if m and not _is_generic_person(m)]
                parsed["key_figures"] = _dedupe_list(merged, key_func=_person_key, max_items=14)

        # Extra fallback: extract likely person names from timeline/key events text.
        # This avoids empty Key People sections when JSON extraction under-delivers.
        if len(parsed.get("key_figures") or []) < 6:
            def _line_citation_id(text: str) -> int | None:
                ids = _citation_ids(text)
                return ids[0] if ids else None

            def _looks_like_place(name: str) -> bool:
                head = _normalize_text(_strip_citations(name)).strip()
                tokens = head.split()
                if len(tokens) != 2:
                    return False
                place_prefixes = {"san", "saint", "st", "new", "fort", "mt", "mount", "lake"}
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
                return tokens[0] in place_prefixes or tokens[1] in place_suffixes

            candidate_lines: list[str] = []
            for field in ("timeline", "key_events", "facts", "context", "causes", "consequences", "source_notes"):
                candidate_lines.extend([str(x) for x in (parsed.get(field) or []) if x])

            token = r"[^\W\d_](?:[^\W\d_]|[.'’\-]){0,23}"
            titled_re = re.compile(
                rf"\b(?P<title>president|prime minister|governor|general|admiral|senator|minister|secretary|king|queen|emperor|pope|bishop|dr\.?|doctor|prof\.?|professor|judge)\s+(?P<name>{token}(?:\s+{token}){{1,3}})\b",
                flags=re.IGNORECASE,
            )
            plain_re = re.compile(rf"\b(?P<name>{token}(?:\s+{token}){{1,3}})\b")

            extracted: list[str] = []
            seen_names: set[str] = set()
            for line in candidate_lines:
                sid = _line_citation_id(line)
                for m in titled_re.finditer(line):
                    nm = m.group("name").strip()
                    if not nm or not _is_name_like(nm) or _looks_like_place(nm) or _is_non_person_entity_name(nm):
                        continue
                    key = _person_key(nm)
                    if not key or key in seen_names:
                        continue
                    seen_names.add(key)
                    role = m.group("title").strip().title()
                    entry = f"{nm} - {role}"
                    if sid is not None:
                        entry = f"{entry} [{sid}]"
                    extracted.append(entry)
                if len(extracted) >= 10:
                    break
                # Then allow plain multi-token names, but keep conservative to avoid places.
                for m in plain_re.finditer(_strip_citations(line)):
                    nm = m.group("name").strip()
                    if not nm or nm.lower().startswith("the "):
                        continue
                    if _looks_like_place(nm) or _is_non_person_entity_name(nm):
                        continue
                    parts = nm.split()
                    if len(parts) < 3 and not re.search(r"\b[A-Z]\.\b", nm):
                        continue
                    if not _is_name_like(nm):
                        continue
                    key = _person_key(nm)
                    if not key or key in seen_names:
                        continue
                    seen_names.add(key)
                    entry = nm
                    if sid is not None:
                        entry = f"{entry} [{sid}]"
                    extracted.append(entry)
                    if len(extracted) >= 12:
                        break
                if len(extracted) >= 12:
                    break

            if extracted:
                merged = (parsed.get("key_figures") or []) + extracted
                merged = [m for m in merged if m and not _is_generic_person(m)]
                parsed["key_figures"] = _dedupe_list(merged, key_func=_person_key, max_items=14)
        # Keep key figures as actual individuals (avoid "the government", "the people", etc.).
        parsed["key_figures"] = [
            p
            for p in (parsed.get("key_figures") or [])
            if p and not _is_generic_person(p) and _is_name_like(p)
        ]
        parsed["key_figures"] = _dedupe_list(parsed.get("key_figures"), key_func=_person_key, max_items=14)
        if allow_web and len(parsed.get("key_figures") or []) < 6:
            _ensure_minimum_history_sources()
            # Re-extract people from the newly added sources (do not hardcode topic-specific names).
            existing_keys = {_person_key(p) for p in (parsed.get("key_figures") or []) if p}
            token = r"[^\W\d_](?:[^\W\d_]|[.'’\-]){0,23}"
            titled_re = re.compile(
                rf"\b(?P<title>president|prime minister|governor|general|admiral|senator|minister|secretary|king|queen|emperor|pope|bishop|dr\.?|doctor|prof\.?|professor|judge)\s+(?P<name>{token}(?:\s+{token}){{1,3}})\b",
                flags=re.IGNORECASE,
            )
            name_re = re.compile(rf"\b(?P<name>{token}(?:\s+{token}){{1,3}})\b")
            # Skip common non-person entity names (generic). Also skip the request/topic itself to avoid
            # treating the subject as a person (e.g., "Harlem Renaissance").
            topic_hint = _extract_topic_hint(request)
            topic_tokens = [t for t in re.split(r"\s+", _normalize_text(topic_hint)) if len(t) > 2]
            topic_phrases = set()
            if topic_tokens:
                topic_phrases.add(" ".join(topic_tokens[:6]).strip())
            skip_entities = {
                "the united states",
                "united states",
                "u.s.",
                "us",
                "u.s",
                "united states of america",
                "congress",
                "library of congress",
                "wikipedia",
                "wikidata",
            } | {p for p in topic_phrases if p}
            for record in source_records:
                if len(parsed.get("key_figures") or []) >= 12:
                    break
                sid = record.get("id")
                try:
                    sid_int = int(sid) if sid is not None else None
                except Exception:
                    sid_int = None
                text = str(record.get("text") or "")
                if not text:
                    continue
                # Scan sentence-sized chunks to reduce false positives.
                for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
                    if len(parsed.get("key_figures") or []) >= 12:
                        break
                    chunk = " ".join(str(sentence or "").split()).strip()
                    if not chunk or len(chunk) < 40:
                        continue
                    # Prefer titled mentions for higher precision.
                    for m in titled_re.finditer(chunk):
                        nm = m.group("name").strip()
                        if not nm or _looks_like_place(nm) or _is_non_person_entity_name(nm) or not _is_name_like(nm):
                            continue
                        key = _person_key(nm)
                        if not key or key in existing_keys:
                            continue
                        existing_keys.add(key)
                        role = m.group("title").strip().title()
                        entry = f"{nm} - {role}"
                        if sid_int is not None:
                            entry = f"{entry} [{sid_int}]"
                        if not _is_generic_person(entry):
                            parsed["key_figures"].append(entry)
                    if len(parsed.get("key_figures") or []) >= 12:
                        break
                    # Then capture plain multi-token names conservatively.
                    for m in name_re.finditer(chunk):
                        nm = m.group("name").strip()
                        if not nm:
                            continue
                        head = _normalize_text(nm)
                        if head in skip_entities:
                            continue
                        if _looks_like_place(nm) or _is_non_person_entity_name(nm) or not _is_name_like(nm):
                            continue
                        parts = [p for p in nm.split() if p]
                        if len(parts) < 2:
                            continue
                        key = _person_key(nm)
                        if not key or key in existing_keys:
                            continue
                        existing_keys.add(key)
                        entry = nm
                        if sid_int is not None:
                            entry = f"{entry} [{sid_int}]"
                        if not _is_generic_person(entry):
                            parsed["key_figures"].append(entry)
        parsed["key_events"] = _dedupe_list(parsed.get("key_events"), key_func=_event_key, max_items=12)
        if len(parsed["key_events"]) < 6 and event_candidates:
            existing_events = {_event_key(item) for item in parsed.get("key_events") or []}
            for item in event_candidates:
                if len(parsed["key_events"]) >= 10:
                    break
                if _event_key(item) in existing_events:
                    continue
                if not _has_year(item):
                    continue
                if not _has_event_keyword(item):
                    continue
                if _is_placeholder_timeline(item) or _is_publication_line(item) or _is_low_information_event_line(item):
                    continue
                parsed["key_events"].append(item)
                existing_events.add(_event_key(item))

        def _extract_dated_events_from_sources(records: list[dict[str, Any]], *, max_items: int) -> list[str]:
            events: list[str] = []
            seen: set[str] = set()

            month_re = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            date_pattern = re.compile(
                rf"(?P<date>(?:\b\d{{4}}\b|\b{month_re}\s+\d{{1,2}},\s*\d{{4}}\b|\b{month_re}\s+\d{{4}}\b|\b\d{{1,2}}\s+{month_re}\s+\d{{4}}\b))"
            )

            for record in records:
                if len(events) >= max_items:
                    break
                sid = record.get("id")
                try:
                    sid_int = int(sid) if sid is not None else None
                except Exception:
                    sid_int = None
                text = str(record.get("text") or "")
                if not text:
                    continue
                sentences = re.split(r"(?<=[.!?])\s+", text)
                for sentence in sentences:
                    if len(events) >= max_items:
                        break
                    clean = " ".join(str(sentence or "").split()).strip()
                    if not clean or len(clean) < 40 or len(clean) > 260:
                        continue
                    if not _has_year(clean) or not _has_event_keyword(clean):
                        continue
                    if _is_placeholder_timeline(clean) or _is_publication_line(clean) or _is_low_information_event_line(clean):
                        continue
                    match = date_pattern.search(clean)
                    if not match:
                        continue
                    date = match.group("date").strip()
                    remainder = clean.replace(date, "", 1).lstrip(" :-—–").strip()
                    if not remainder:
                        continue
                    line = f"{date}: {remainder}".strip()
                    if sid_int is not None:
                        line = f"{line} [{sid_int}]"
                    key = _event_key(line)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    events.append(line)
            return events

        # If the LLM-provided timeline is too short (often due to over-filtering of publication dates),
        # backfill with dated event sentences extracted from the sources themselves.
        parsed["timeline"] = _dedupe_list(parsed.get("timeline"), key_func=_event_key, max_items=18)
        if len(parsed.get("timeline") or []) < 8 and source_records:
            existing = {_event_key(item) for item in parsed.get("timeline") or []}
            for item in _extract_dated_events_from_sources(source_records, max_items=18):
                if len(parsed["timeline"]) >= 14:
                    break
                if _event_key(item) in existing:
                    continue
                parsed["timeline"].append(item)
                existing.add(_event_key(item))
        if len(parsed["key_events"]) < 6:
            existing_events = {_event_key(item) for item in parsed.get("key_events") or []}
            for item in parsed.get("timeline") or []:
                if len(parsed["key_events"]) >= 10:
                    break
                if _event_key(item) in existing_events:
                    continue
                if not _has_year(item):
                    continue
                if _is_publication_line(item):
                    continue
                if _is_placeholder_timeline(item) or _is_low_information_event_line(item):
                    continue
                parsed["key_events"].append(item)
                existing_events.add(_event_key(item))
        parsed["facts"] = _dedupe_list(parsed.get("facts"), max_items=18)
        parsed["context"] = _dedupe_list(parsed.get("context"), max_items=8)
        parsed["causes"] = _dedupe_list(parsed.get("causes"), max_items=8)
        parsed["consequences"] = _dedupe_list(parsed.get("consequences"), max_items=8)
        parsed["source_notes"] = _dedupe_list(parsed.get("source_notes"), max_items=20)
        interpretations = parsed.get("interpretations")
        allowed_ids = {int(x) for x in source_ids}
        if isinstance(interpretations, list) and any(isinstance(x, dict) for x in interpretations):
            seen: set[str] = set()
            kept: list[dict[str, Any]] = []

            def _keep_only_allowed_citations(text: str) -> str:
                raw = str(text or "")
                cites = [f"[{i}]" for i in _citation_ids(raw) if i in allowed_ids]
                base = re.sub(r"\[\d+\]", "", raw).strip()
                base = re.sub(r"\s+", " ", base).strip()
                cites = _dedupe_list(cites)
                return f"{base} {' '.join(cites)}".strip() if cites else base

            def _has_allowed_citation(text: str) -> bool:
                return any(i in allowed_ids for i in _citation_ids(text))

            for item in interpretations:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question") or "").strip()
                traditional = str(item.get("traditional_view") or item.get("view_a") or item.get("position_a") or "").strip()
                alternative = str(item.get("alternative_view") or item.get("view_b") or item.get("position_b") or "").strip()
                traditional = _keep_only_allowed_citations(traditional)
                alternative = _keep_only_allowed_citations(alternative)
                if not (_has_allowed_citation(traditional) or _has_allowed_citation(alternative)):
                    # Some models return structured debates but forget citations; attach a best-matching
                    # source so the writing stage can include the debate without hallucination.
                    if traditional:
                        best = _best_source_for_text(_strip_citations(traditional), source_records)
                        if best and best in allowed_ids:
                            traditional = f"{_strip_citations(traditional)} [{best}]"
                    if alternative:
                        best = _best_source_for_text(_strip_citations(alternative), source_records)
                        if best and best in allowed_ids:
                            alternative = f"{_strip_citations(alternative)} [{best}]"
                    if not (_has_allowed_citation(traditional) or _has_allowed_citation(alternative)):
                        continue
                key = _normalize_text(question or traditional or alternative)
                if not key or key in seen:
                    continue
                seen.add(key)
                kept.append(
                    {
                        "question": question,
                        "traditional_view": traditional,
                        "alternative_view": alternative,
                    }
                )
                if len(kept) >= 8:
                    break
            parsed["interpretations"] = kept
        else:
            # If the model returned legacy single-line interpretations, coerce them into structured debates
            # so the writing agent can render non-repetitive "Debate" blocks.
            debates: list[dict[str, str]] = []
            seen: set[str] = set()
            if isinstance(interpretations, list):
                for item in interpretations:
                    text = str(item or "").strip()
                    if not text:
                        continue
                    # Drop uncited interpretations to avoid hallucinated debate claims.
                    if not _citation_ids(text):
                        best = _best_source_for_text(_strip_citations(text), source_records)
                        if best and best in allowed_ids:
                            text = f"{_strip_citations(text)} [{best}]"
                        else:
                            continue
                    lowered = text.lower()
                    for splitter in ("while others", "whereas", "but others", "however", " vs ", " versus "):
                        if splitter in lowered:
                            parts = re.split(splitter, text, maxsplit=1, flags=re.IGNORECASE)
                            if len(parts) == 2:
                                traditional = parts[0].strip().rstrip(" ,;")
                                alternative = parts[1].strip().lstrip(" ,;")
                                if not traditional or not alternative:
                                    break
                                key = _normalize_text(traditional + " " + alternative)
                                if key and key not in seen:
                                    debates.append(
                                        {
                                            "question": "",
                                            "traditional_view": traditional,
                                            "alternative_view": alternative,
                                        }
                                    )
                                    seen.add(key)
                            break
                    if len(debates) >= 6:
                        break
            if debates:
                parsed["interpretations"] = debates
            else:
                parsed["interpretations"] = _dedupe_list(parsed.get("interpretations"), max_items=8)
        parsed["limitations"] = _dedupe_list(parsed.get("limitations"), max_items=12)
        parsed["discussion_questions"] = _dedupe_list(parsed.get("discussion_questions"), max_items=16)

        if not parsed.get("key_events"):
            parsed["key_events"] = list(parsed.get("timeline") or [])[:10]

        # Include lightweight source excerpts for downstream grounding (e.g., Key People verification).
        # This is intentionally truncated to keep execution artifacts small.
        try:
            excerpt_len = int(self.config.get("source_excerpt_chars") or 12000)
        except Exception:
            excerpt_len = 12000
        try:
            parsed["source_records"] = [
                {
                    "id": int(r.get("id")) if r.get("id") is not None else None,
                    "title": str(r.get("title") or ""),
                    "url": str(r.get("url") or ""),
                    "origin": str(r.get("origin") or ""),
                    "text_excerpt": str(r.get("text") or "")[:excerpt_len],
                }
                for r in (source_records or [])
                if r
            ]
        except Exception:
            parsed["source_records"] = []

        for key in ("context", "causes", "consequences", "timeline", "key_figures", "key_events", "facts", "source_notes"):
            parsed[key] = _ensure_citations(parsed.get(key) or [], source_ids, usage)

        missing = [sid for sid in source_ids if usage.get(sid, 0) == 0]
        if missing:
            records_by_id = {int(r.get("id")): r for r in source_records if r.get("id")}

            def _best_highlight(record: dict[str, Any]) -> str | None:
                text = str(record.get("text") or "")
                if not text:
                    return None
                sentences = re.split(r"(?<=[.!?])\s+", text)
                for sent in sentences:
                    clean = sent.strip()
                    if not clean:
                        continue
                    if len(clean) > 240:
                        continue
                    if _is_publication_line(clean):
                        continue
                    lowered_sent = clean.lower()
                    if "top of page" in lowered_sent or "special holiday hours" in lowered_sent:
                        continue
                    if _has_year(clean) and _has_event_keyword(clean):
                        return clean
                for sent in sentences:
                    clean = sent.strip()
                    if not clean:
                        continue
                    if len(clean) > 240:
                        continue
                    if _is_publication_line(clean):
                        continue
                    if _has_event_keyword(clean):
                        return clean
                return None

            for sid in missing:
                record = records_by_id.get(int(sid))
                if not record:
                    continue
                highlight = _best_highlight(record)
                if not highlight:
                    continue
                parsed["facts"].append(f"{highlight} [{sid}]")
                usage[sid] = usage.get(sid, 0) + 1
            parsed["facts"] = _dedupe_list(parsed.get("facts"), max_items=22)
        return AgentResult(ok=True, data=parsed, raw_output=raw)
