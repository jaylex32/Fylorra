from __future__ import annotations

import re
from typing import Any

from core.agents.llm_agent import _LLMBaseAgent
from core.pipeline.agent import AgentCapability, AgentResult


def _strip_internal_reasoning(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"(?is)<\s*(think|analysis|reasoning)[^>]*>.*?<\s*/\s*\1\s*>", "", out)
    out = re.sub(r"(?is)```(?:thinking|analysis|reasoning).*?```", "", out)
    return out.strip()


def _clean_text(text: str) -> str:
    out = str(text or "")
    replacements = {
        "â€”": "-",
        "â€“": "-",
        "â€˜": "'",
        "â€™": "'",
        'â€œ': '"',
        'â€�': '"',
        "â€¦": "...",
    }
    for bad, good in replacements.items():
        out = out.replace(bad, good)
    return out


def _render_sources(sources: Any, source_meta: Any) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    if isinstance(source_meta, list):
        for raw in source_meta:
            if not isinstance(raw, dict):
                continue
            sid = raw.get("id")
            title = str(raw.get("title") or "").strip()
            url = str(raw.get("url") or "").strip()
            if not title and not url:
                continue
            prefix = f"[{sid}] " if sid is not None else ""
            line = f"{prefix}{title or url}"
            if url and url != title:
                line = f"{line} - {url}"
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
    if lines:
        return lines
    if isinstance(sources, list):
        for raw in sources:
            line = str(raw or "").strip()
            if not line:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
    return lines


def _request_terms(request: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(request or "").lower())
    stop = {
        "write",
        "create",
        "make",
        "generate",
        "website",
        "blog",
        "article",
        "news",
        "report",
        "about",
        "for",
        "the",
        "and",
        "with",
        "topic",
    }
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 3 or t in stop:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:10]


def _source_line_matches_request(line: str, terms: list[str]) -> bool:
    if not terms:
        return True
    hay = str(line or "").lower()
    hits = 0
    for t in terms:
        if t in hay:
            hits += 1
            continue
        stem = t[:5]
        if stem and stem in hay:
            hits += 1
    return hits >= 2


def _replace_references_section(doc: str, source_lines: list[str]) -> str:
    text = str(doc or "").strip()
    if not text:
        return text
    pattern = re.compile(
        r"(?ms)^\s*##\s+(References|Works Cited|Sources)\s*\n.*?(?=^\s*##\s+|\Z)",
        re.IGNORECASE,
    )
    text = pattern.sub("", text).rstrip()
    if not source_lines:
        return text + ("\n" if text else "")
    cited_ids = {int(x) for x in re.findall(r"\[(\d+)\]", text)}
    filtered_lines: list[str] = []
    if cited_ids:
        for line in source_lines:
            m = re.match(r"^\s*\[(\d+)\]\s+", str(line))
            if m and int(m.group(1)) in cited_ids:
                filtered_lines.append(line)
    if not filtered_lines:
        filtered_lines = list(source_lines)
    out = [text, "", "## References"]
    for line in filtered_lines:
        out.append(f"- {line}")
    return "\n".join(out).strip() + "\n"


def _strip_inline_numeric_citations(doc: str) -> str:
    text = str(doc or "")
    text = re.sub(r"\s*\[(?:\d+\s*(?:,\s*\d+\s*)*)\]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _normalize_pricing_language(doc: str) -> str:
    text = str(doc or "")
    # Avoid overclaiming that tools are fully free when many are freemium/paid.
    text = re.sub(
        r"(?i)\bfree tools\b",
        "free-tier or low-cost tools",
        text,
    )
    text = re.sub(
        r"(?i)\bfree AI tools\b",
        "free-tier or low-cost AI tools",
        text,
    )
    text = re.sub(
        r"(?i)\bthese tools are free\b",
        "many of these tools offer free tiers, with paid plans for advanced features",
        text,
    )
    return text


class WebArticleWritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="web_article_writing_agent",
            role="writer",
            system_prompt=(
                "You are an editorial writer for professional websites.\n"
                "Write clear, engaging, factual articles suitable for publication."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="web_article_writing",
                    name="Web Article Writing",
                    description="Create publication-ready website or news-style articles.",
                    input_types=["json", "text"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=45,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        request = str(payload.get("user_request") or context.user_request or "").strip()
        if "_" in request and " " not in request:
            request = request.replace("_", " ").strip()
        notes = str(payload.get("summary") or payload.get("notes") or "").strip()
        findings = payload.get("findings") or payload.get("highlights") or []
        claims = payload.get("claims") or []
        sources = payload.get("sources") or []
        source_meta = payload.get("source_meta") or []
        source_validation = payload.get("source_validation") or {}
        source_lines = _render_sources(sources, source_meta)
        terms = _request_terms(request)
        matched_sources = [s for s in source_lines if _source_line_matches_request(s, terms)]
        validation_status = str(source_validation.get("status") or "").upper()
        weak_sources = bool(source_lines) and len(matched_sources) < 2
        weak_sources = weak_sources or validation_status in {"INSUFFICIENT", "CRITICAL_ERROR"}

        findings_text = (
            "\n".join(f"- {str(x)}" for x in findings if str(x or "").strip())
            if isinstance(findings, list)
            else str(findings or "")
        )
        claims_text = (
            "\n".join(f"- {str(x.get('text') or '').strip()}" for x in claims if isinstance(x, dict))
            if isinstance(claims, list)
            else ""
        )
        sources_text = "\n".join(f"- {s}" for s in source_lines)

        user_msg = (
            f"Article request:\n{request}\n\n"
            f"Notes:\n{notes}\n\n"
            f"Findings:\n{findings_text}\n\n"
            f"Claims:\n{claims_text}\n\n"
            f"Sources:\n{sources_text}\n\n"
            "Write a polished markdown article with this structure:\n"
            "1) Title\n"
            "2) Standfirst (1-2 sentences)\n"
            "3) Introduction\n"
            "4) Main Sections (H2/H3)\n"
            "5) Key Takeaways (bullets)\n"
            "6) Conclusion\n"
            "7) References (if sources are provided)\n\n"
            "Rules:\n"
            "- Keep tone professional and readable.\n"
            "- Do not use hype or clickbait language.\n"
            "- Use only provided sources; never invent citations.\n"
            "- Use inline citations like [1], [2] when stating facts.\n"
            "- Mention specific tools/brands only if they appear in the provided findings/claims/source materials.\n"
            "- Do not invent exact percentages or hard numbers; include numbers only when clearly supported by provided sources.\n"
            "- When discussing pricing, use 'free tier' or 'low-cost' unless a source explicitly says fully free.\n"
            "- If you include a section about human oversight, provide one concrete example sentence.\n"
            "- If evidence is limited, state uncertainty clearly.\n"
            "- Never output hidden reasoning tags like <think>.\n"
        )
        if weak_sources:
            user_msg += (
                "\nLimited-evidence mode:\n"
                "- Treat this as practical guidance, not source-verified reporting.\n"
                "- Do NOT use inline citations like [1], [2].\n"
                "- Do NOT include a References section.\n"
                "- Avoid precise claims that require external verification.\n"
            )

        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=1800,
            temperature=0.25,
        )
        if not res.ok:
            return res

        doc = _strip_internal_reasoning(str((res.data or {}).get("text") or "").strip())
        doc = _clean_text(doc)
        doc = _normalize_pricing_language(doc)
        if weak_sources or not source_lines:
            doc = _strip_inline_numeric_citations(doc)
            doc = _replace_references_section(doc, [])
        else:
            doc = _replace_references_section(doc, matched_sources or source_lines)

        return AgentResult(
            ok=True,
            data={
                "document": doc + ("\n" if doc and not doc.endswith("\n") else ""),
                "format": "markdown",
                "sources": (matched_sources or source_lines) if not weak_sources else [],
                "source_meta": source_meta,
            },
        )
