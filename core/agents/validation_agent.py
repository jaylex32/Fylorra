from __future__ import annotations

import json
import re
from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent
from core.integrations.web_search import search_web, fetch_url_text


_PRED_MARKERS = (
    "will ",
    "is projected to",
    "is expected to",
    "may ",
    "could ",
    "might ",
    "would ",
    "by 2026",
    "in 2026",
    "by 2027",
    "are predicted to",
    "is forecasted to",
    "likely to",
    "poised to",
    "set to",
)

_FACT_MARKERS = (
    "has achieved",
    "was ",
    "were ",
    "have been",
    "had ",
    "did ",
    "currently is",
    "exists",
    "exists today",
)

_TREND_MARKERS = (
    "is increasing",
    "is growing",
    "is declining",
    "has been rising",
    "adoption is accelerating",
    "adoption is rising",
)

_CAVEAT_WORDS = (
    "may",
    "might",
    "could",
    "potential",
    "possibly",
    "uncertain",
    "speculative",
    "experimental",
    "not guaranteed",
    "depends on",
    "contingent",
    "if ",
    "assuming",
)

_SCHOOL_ASSIGNMENT_PIPELINES = {
    "school_assignment_universal",
    "school_argumentative_essay",
    "school_compare_contrast_essay",
    "school_science_fair_report",
    "school_book_report",
    "school_current_events_report",
}


def _classify_claim_type(claim: str) -> str:
    text = str(claim or "").lower()
    if any(m in text for m in _PRED_MARKERS):
        return "PREDICTION"
    if any(m in text for m in _FACT_MARKERS):
        return "HISTORICAL_FACT"
    if any(m in text for m in _TREND_MARKERS):
        return "TREND"
    return "GENERAL"


def _extract_citations(text: str) -> list[int]:
    return [int(m) for m in re.findall(r"\[(\d+)\]", text or "")]


def _find_context(doc: str, claim: str, window: int = 140) -> str:
    doc_text = str(doc or "")
    claim_text = str(claim or "").strip()
    if not doc_text or not claim_text:
        return ""
    words = [w for w in re.split(r"\s+", claim_text) if w]
    if not words:
        return ""
    key = " ".join(words[:8])
    try:
        match = re.search(re.escape(key), doc_text, flags=re.IGNORECASE)
    except Exception:
        match = None
    if not match:
        return claim_text
    start = max(0, match.start() - window)
    end = min(len(doc_text), match.end() + window)
    return doc_text[start:end]


def _has_attribution_phrase(context: str) -> bool:
    if not context:
        return False
    ctx = context.lower()
    return "according to" in ctx or "reports that" in ctx or "reported by" in ctx


def _has_caveat(context: str) -> bool:
    if not context:
        return False
    ctx = context.lower()
    return any(word in ctx for word in _CAVEAT_WORDS)


def _safe_json_list(text: str) -> list[dict[str, Any]]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except Exception:
        match = re.search(r"\[.*\]", raw, flags=re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                return []
        else:
            return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _normalize_sources_list(sources: Any) -> list[str]:
    if not isinstance(sources, list):
        return []
    items = [str(x).strip() for x in sources if str(x).strip()]
    if not items:
        return []
    if any(item.startswith("[") for item in items):
        return items
    return [f"[{i + 1}] {item}" for i, item in enumerate(items)]


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


def _inject_sources_section(document: str, sources_list: list[str]) -> str:
    if not document or not sources_list:
        return document
    body = "\n".join(f"- {line}" for line in sources_list)
    replacement = f"## Sources\n{body}"
    pattern = re.compile(r"(?ms)^\s*#+\s+Sources[^\n]*\n.*?(?=^\s*#+\s+\w|\Z)", re.IGNORECASE)
    cleaned = pattern.sub("", document).strip()
    if cleaned:
        return cleaned.rstrip() + "\n\n" + replacement
    return replacement


def _extract_sources_from_document(document: str) -> list[str]:
    if not document:
        return []
    pattern = re.compile(r"(?ms)^\s*#+\s+Sources[^\n]*\n(.*?)(?=^\s*#+\s+\w|\Z)", re.IGNORECASE)
    match = pattern.search(document)
    if not match:
        return []
    block = match.group(1)
    items: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        if line:
            items.append(line)
    return items


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
    body = "\n".join(f"- {line}" for line in sources_list)
    replacement = f"## Sources\n{body}"
    if cleaned:
        return cleaned.rstrip() + "\n\n" + replacement
    return replacement


class ValidationAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="validation_agent",
            role="validator",
            system_prompt=(
                "You are a quality assurance agent.\n"
                "Validate clarity, grammar, and completeness. Provide a brief QA report."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="validation",
                    name="Quality Validation",
                    description="Check grammar, clarity, and structure.",
                    input_types=["text"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=30,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        doc = payload.get("document") or payload.get("text") or ""
        pipeline_id = str(
            context.pipeline_id
            or context.initial_parameters.get("pipeline_id")
            or ""
        )
        sources = payload.get("sources") or []
        sources_list = _normalize_sources_list(sources)
        if not sources_list:
            sources_list = _extract_sources_from_document(doc)

        # For universal school assignments, do not run verification extraction at all.
        # This prevents "Verification Report" leakage and keeps output submission-ready.
        if pipeline_id in _SCHOOL_ASSIGNMENT_PIPELINES:
            improved = _strip_verification_report(_strip_placeholder_notes(doc))
            improved = _collapse_sources_sections(improved, sources_list)
            return AgentResult(
                ok=True,
                data={
                    "overall_score": 0.8,
                    "issues": [],
                    "improved_text": improved,
                    "sources": sources_list or sources,
                },
            )

        allow_web = bool(payload.get("allow_web_research") or context.initial_parameters.get("allow_web_research"))
        max_results = int(payload.get("web_max_results") or context.initial_parameters.get("web_max_results") or 5)
        try:
            settings = context.services.get("settings")
            wf_settings = settings.get_workflow_settings() if settings else {}
            allow_web = bool(allow_web or wf_settings.get("allow_web_research", False))
            max_results = int(wf_settings.get("web_max_results", max_results))
        except Exception:
            pass

        verification_results: list[dict[str, Any]] = []
        verification_notes = ""
        verification_report = ""
        if doc:
            extract_msg = (
                "Extract up to 10 major claims from the report (predictions, facts, trends).\n"
                "Return JSON list of objects with keys: text, section.\n"
                "Keep each claim to one sentence."
            )
            extract_res = self._run_llm(
                context=context,
                system_prompt="You extract verifiable claims from reports.",
                user_message=f"{extract_msg}\n\nDocument:\n{doc}",
                response_format="json",
                max_tokens=650,
                temperature=0.1,
            )
            claims = _safe_json_list(str(extract_res.data.get("text") if extract_res.ok else ""))
            if claims:
                seen_claims: set[str] = set()
                unique: list[dict[str, Any]] = []
                for claim in claims:
                    text = str(claim.get("text") or "").strip()
                    if not text:
                        continue
                    key = text.lower()
                    if key in seen_claims:
                        continue
                    seen_claims.add(key)
                    unique.append(claim)
                claims = unique
            verification_results = []
            for claim in claims[:10]:
                text = str(claim.get("text") or "").strip()
                if not text:
                    continue
                ctype = _classify_claim_type(text)
                context_snip = _find_context(doc, text)
                citations = _extract_citations(context_snip)
                has_attr = _has_attribution_phrase(context_snip)
                has_caveat = _has_caveat(context_snip)
                result: dict[str, Any] = {"claim": text, "type": ctype}

                if ctype == "PREDICTION":
                    if not citations and not has_attr:
                        result.update(
                            {
                                "status": "UNVERIFIABLE",
                                "reason": "Prediction not attributed to any source.",
                                "action": "Add explicit attribution or remove.",
                                "severity": "HIGH",
                            }
                        )
                    elif citations and not has_attr:
                        result.update(
                            {
                                "status": "NEEDS_ATTRIBUTION",
                                "source": citations[0] if citations else "source",
                                "fix": "Add explicit attribution (e.g., According to [source]).",
                                "severity": "MEDIUM",
                            }
                        )
                    elif not has_caveat and any(m in text.lower() for m in ("will ", "is projected to", "is expected to")):
                        result.update(
                            {
                                "status": "MISSING_CAVEATS",
                                "source": citations[0] if citations else "source",
                                "fix": "Include source caveats (e.g., may, could, speculative).",
                                "severity": "MEDIUM",
                            }
                        )
                    else:
                        result.update(
                            {
                                "status": "VERIFIED",
                                "note": "Prediction properly attributed.",
                            }
                        )
                        if len(citations) <= 1:
                            result["flag"] = "Single-source prediction - not corroborated."
                elif ctype == "HISTORICAL_FACT":
                    if allow_web:
                        query = f"\"{text}\""
                        results = search_web(query, max_results=min(3, max_results))
                        hits = 0
                        urls = []
                        for hit in results:
                            url = str(hit.get("url") or "")
                            title = str(hit.get("title") or url)
                            fetched = fetch_url_text(url, max_chars=2000)
                            if text.lower() in (fetched or "").lower() or text.lower() in (title or "").lower():
                                hits += 1
                            if url:
                                urls.append(f"{title} - {url}")
                        if hits > 0:
                            result.update({"status": "VERIFIED", "sources": urls})
                        else:
                            result.update(
                                {
                                    "status": "UNVERIFIED",
                                    "reason": "Could not confirm historical fact.",
                                    "action": "Review and correct or remove.",
                                    "severity": "HIGH",
                                }
                            )
                    else:
                        if citations or has_attr:
                            result.update(
                                {
                                    "status": "WEAKLY_VERIFIED",
                                    "flag": "Web verification disabled; relying on citation.",
                                    "severity": "MEDIUM",
                                }
                            )
                        else:
                            result.update(
                                {
                                    "status": "NEEDS_ATTRIBUTION",
                                    "reason": "Web verification disabled.",
                                    "action": "Add citation or enable web research.",
                                    "severity": "MEDIUM",
                                }
                            )
                elif ctype == "TREND":
                    if len(citations) >= 2:
                        result.update({"status": "VERIFIED", "note": "Trend supported by multiple sources."})
                    elif len(citations) == 1:
                        result.update(
                            {
                                "status": "WEAKLY_VERIFIED",
                                "flag": "Single source trend - not corroborated.",
                                "severity": "MEDIUM",
                            }
                        )
                    else:
                        result.update(
                            {
                                "status": "UNVERIFIED",
                                "reason": "No evidence cited for trend.",
                                "action": "Add supporting sources or remove.",
                                "severity": "HIGH",
                            }
                        )
                else:
                    if has_attr or citations:
                        result.update({"status": "VERIFIED"})
                    else:
                        result.update(
                            {
                                "status": "NEEDS_ATTRIBUTION",
                                "reason": "Claim lacks attribution.",
                                "action": "Add source citation.",
                                "severity": "MEDIUM",
                            }
                        )

                verification_results.append(result)

            buckets = {
                "VERIFIED": [],
                "NEEDS_ATTRIBUTION": [],
                "MISSING_CAVEATS": [],
                "WEAKLY_VERIFIED": [],
                "UNVERIFIABLE": [],
                "UNVERIFIED": [],
            }
            for item in verification_results:
                buckets.setdefault(item.get("status", "UNVERIFIABLE"), []).append(item)

            total = sum(len(v) for v in buckets.values())
            lines: list[str] = []
            lines.append("# Verification Report")
            lines.append("")
            lines.append(f"**Total Claims Checked**: {total}")
            lines.append("")
            lines.append(f"## Verified ({len(buckets['VERIFIED'])})")
            for item in buckets["VERIFIED"]:
                lines.append(f"- {item.get('claim')}")
            if buckets["NEEDS_ATTRIBUTION"]:
                lines.append("")
                lines.append(f"## Needs Attribution ({len(buckets['NEEDS_ATTRIBUTION'])})")
                for item in buckets["NEEDS_ATTRIBUTION"]:
                    lines.append(f"- {item.get('claim')}")
            if buckets["MISSING_CAVEATS"]:
                lines.append("")
                lines.append(f"## Missing Caveats ({len(buckets['MISSING_CAVEATS'])})")
                for item in buckets["MISSING_CAVEATS"]:
                    lines.append(f"- {item.get('claim')}")
            if buckets["WEAKLY_VERIFIED"]:
                lines.append("")
                lines.append(f"## Weakly Verified ({len(buckets['WEAKLY_VERIFIED'])})")
                for item in buckets["WEAKLY_VERIFIED"]:
                    lines.append(f"- {item.get('claim')}")
            if buckets["UNVERIFIABLE"] or buckets["UNVERIFIED"]:
                lines.append("")
                lines.append(
                    f"## Unverifiable ({len(buckets['UNVERIFIABLE']) + len(buckets['UNVERIFIED'])})"
                )
                for item in buckets["UNVERIFIABLE"] + buckets["UNVERIFIED"]:
                    lines.append(f"- {item.get('claim')}")
            verification_report = "\n".join(lines).strip()
        elif not allow_web:
            verification_notes = "Fact-checking skipped (web research disabled)."
        skip_rewrite = pipeline_id in {"family_history_project", "history_project"}
        if skip_rewrite:
            improved = _strip_verification_report(_strip_placeholder_notes(doc))
            improved = _collapse_sources_sections(improved, sources_list)
            issues = [verification_notes] if verification_notes else []
            return AgentResult(
                ok=True,
                data={
                    "overall_score": 0.8,
                    "issues": issues,
                    "improved_text": improved,
                    "verification": verification_results,
                    "verification_report": verification_report,
                    "sources": sources_list or sources,
                },
            )
        user_msg = (
            "Review the document for clarity, grammar, and missing sections.\n"
            "Preserve headings and citations like [1].\n"
            "Ensure forward-looking claims include confidence labels and caveats.\n"
            "Use the verification notes to add qualifiers or remove unverified specifics.\n"
            "Return JSON with keys: overall_score (0-1), issues (list), improved_text (string).\n\n"
            f"{verification_notes}\n\n"
            f"Document:\n{doc}"
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
        parsed = None
        raw_clean = raw.strip()
        if raw_clean.startswith("```"):
            raw_clean = re.sub(r"^```(?:json)?", "", raw_clean).strip()
            raw_clean = re.sub(r"```$", "", raw_clean).strip()
        try:
            parsed = json.loads(raw_clean)
        except Exception:
            match = re.search(r"\{.*\}", raw_clean, flags=re.S)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except Exception:
                    parsed = None
        if not isinstance(parsed, dict):
            parsed = {"overall_score": 0.7, "issues": [], "improved_text": doc}
        if not parsed.get("improved_text"):
            parsed["improved_text"] = doc
        if not sources_list:
            sources_list = _extract_sources_from_document(parsed.get("improved_text") or "")
        cleaned = _strip_verification_report(parsed.get("improved_text") or "")
        parsed["improved_text"] = _collapse_sources_sections(cleaned, sources_list)
        issues = parsed.get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]
        if verification_notes:
            issues.append(verification_notes)
        parsed["issues"] = issues
        if verification_results:
            parsed["verification"] = verification_results
        if verification_report:
            parsed["verification_report"] = verification_report
        return AgentResult(ok=True, data=parsed)
