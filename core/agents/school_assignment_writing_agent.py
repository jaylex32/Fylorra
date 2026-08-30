from __future__ import annotations

import re
from typing import Any

from core.agents.llm_agent import _LLMBaseAgent
from core.pipeline.agent import AgentCapability, AgentResult


def _clean_text(text: str) -> str:
    out = str(text or "")
    # Fix common mojibake seen in copy/paste and PDF extraction.
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


def _strip_internal_reasoning(text: str) -> str:
    out = str(text or "")
    # Remove model reasoning blocks if a provider leaks them.
    out = re.sub(r"(?is)<\s*(think|analysis|reasoning)[^>]*>.*?<\s*/\s*\1\s*>", "", out)
    out = re.sub(r"(?is)```(?:thinking|analysis|reasoning).*?```", "", out)
    # Drop single leaked tag lines that may remain.
    lines = []
    for line in out.splitlines():
        s = line.strip().lower()
        if s in {"<think>", "</think>", "<analysis>", "</analysis>", "<reasoning>", "</reasoning>"}:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _request_terms(request: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(request or "").lower())
    stop = {
        "create",
        "write",
        "make",
        "build",
        "project",
        "assignment",
        "school",
        "homework",
        "essay",
        "report",
        "about",
        "topic",
        "person",
        "people",
        "that",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "the",
        "a",
        "an",
        "of",
        "for",
        "on",
    }
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 4 or t in stop:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:8]


def _source_relevance_score(title: str, url: str, terms: list[str]) -> int:
    if not terms:
        return 1
    hay = f"{title} {url}".lower()
    hay_tokens = set(re.findall(r"[a-z0-9]+", hay))
    score = 0
    for term in terms:
        if term in hay_tokens:
            score += 1
            continue
        stem = term[:5]
        if any(tok.startswith(stem) for tok in hay_tokens):
            score += 1
    return score


def _source_matches_request(title: str, url: str, request: str) -> bool:
    terms = _request_terms(request)
    if not terms:
        return True
    hay = f"{title} {url}".lower()
    hay_tokens = set(re.findall(r"[a-z0-9]+", hay))
    for term in terms:
        if term in hay_tokens:
            return True
        stem = term[:5]
        if stem and any(tok.startswith(stem) for tok in hay_tokens):
            return True
    return False


def _render_real_sources(
    sources: Any,
    source_meta: Any,
    request: str = "",
) -> list[str]:
    rendered: list[str] = []
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
            if not _source_matches_request(title, url, request):
                continue
            prefix = f"[{sid}] " if sid is not None else ""
            line = f"{prefix}{title or url}"
            if url and url != title:
                line = f"{line} - {url}"
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            rendered.append(line)

    if rendered:
        return rendered

    # Fallback: keep only explicit, real-looking source lines (URL-bearing or bracketed citations).
    if isinstance(sources, list):
        for item in sources:
            line = str(item or "").strip()
            if not line:
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if "http://" not in line and "https://" not in line and not re.search(r"\[\d+\]", line):
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            rendered.append(line)
    return rendered


def _replace_works_cited_section(doc: str, real_sources: list[str]) -> str:
    text = str(doc or "").strip()
    if not text:
        return text

    # Remove any existing Works Cited/Bibliography section produced by the model.
    pattern = re.compile(
        r"(?ms)^\s*##\s+(Works Cited|Bibliography)\s*\n.*?(?=^\s*##\s+|\Z)",
        re.IGNORECASE,
    )
    text = pattern.sub("", text).rstrip()

    if not real_sources:
        return text + ("\n" if text else "")

    lines = [text, "", "## Works Cited"]
    for src in real_sources:
        lines.append(f"- {src}")
    return "\n".join(lines).strip() + "\n"


def _strip_inline_numeric_citations(doc: str) -> str:
    text = str(doc or "")
    text = re.sub(r"\s*\[(?:\d+\s*(?:,\s*\d+\s*)*)\]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


class SchoolAssignmentWritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="school_assignment_writing_agent",
            role="writer",
            system_prompt=(
                "You are a school assignment writing assistant.\n"
                "Write clear, submission-ready assignments for any school topic.\n"
                "Do not use executive/business report structure.\n"
                "Keep writing natural, age-appropriate, and well organized."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="school_assignment_writing",
                    name="School Assignment Writing",
                    description="Create school-ready assignments from research notes.",
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

        summary = str(payload.get("summary") or payload.get("notes") or "").strip()
        findings = payload.get("findings") or payload.get("highlights") or []
        claims = payload.get("claims") or []
        sources = payload.get("sources") or []
        source_meta = payload.get("source_meta") or []
        real_sources = _render_real_sources(sources, source_meta, request=request)
        had_source_meta = isinstance(source_meta, list) and len(source_meta) > 0

        findings_text = "\n".join(f"- {_clean_text(str(x))}" for x in findings if str(x or "").strip()) if isinstance(findings, list) else _clean_text(str(findings or ""))
        sources_text = "\n".join(f"- {_clean_text(str(x))}" for x in real_sources) if real_sources else ""

        claims_lines: list[str] = []
        if isinstance(claims, list):
            for c in claims:
                if isinstance(c, dict):
                    text = str(c.get("text") or "").strip()
                    if not text:
                        continue
                    cite_ids: list[int] = []
                    for cid in (c.get("supporting_sources") or []):
                        try:
                            cite_ids.append(int(cid))
                        except Exception:
                            continue
                    cite_ids = sorted({x for x in cite_ids if x > 0})
                    cite = f" [{', '.join(str(x) for x in cite_ids)}]" if cite_ids else ""
                    claims_lines.append(f"- {_clean_text(text)}{cite}")
                else:
                    raw = str(c or "").strip()
                    if raw:
                        claims_lines.append(f"- {_clean_text(raw)}")
        claims_text = "\n".join(claims_lines)

        if had_source_meta and len(real_sources) < 1:
            audit_lines = ["# Source Quality Issue", ""]
            audit_lines.append("## Why This Was Not Auto-Written")
            audit_lines.append(
                "The available sources for this run were off-topic or too weakly related to the requested assignment topic, so a citation-backed final paper was not generated."
            )
            audit_lines.append("")
            audit_lines.append("## What To Do Next")
            audit_lines.append("- Re-run with a clearer prompt (example: `Create a school assignment on the history of electricity and key contributors.`).")
            audit_lines.append("- Enable/confirm web research so the system can fetch relevant sources.")
            audit_lines.append("- Review sources before submission.")
            if real_sources:
                audit_lines.append("")
                audit_lines.append("## Relevant Sources Found")
                for src in real_sources:
                    audit_lines.append(f"- {src}")
            return AgentResult(
                ok=True,
                data={
                    "document": "\n".join(audit_lines).strip() + "\n",
                    "format": "markdown",
                    "sources": real_sources,
                    "source_meta": source_meta,
                },
            )

        user_msg = (
            f"Assignment request:\n{request}\n\n"
            f"Summary notes:\n{summary}\n\n"
            f"Key findings:\n{findings_text}\n\n"
            f"Claims:\n{claims_text}\n\n"
            f"Sources:\n{sources_text}\n\n"
            "Write a school assignment in markdown with this structure:\n"
            "1) Title\n"
            "2) Introduction\n"
            "3) Background / Context\n"
            "4) Main Points (organized in clear paragraphs)\n"
            "5) Conclusion\n"
            "6) Works Cited (if sources are provided)\n\n"
            "Rules:\n"
            "- Keep the writing suitable for students and parents.\n"
            "- Use complete sentences with smooth flow.\n"
            "- Avoid duplication, fragments, and filler.\n"
            "- Include inline citations like [1], [2] for factual statements only when sources are provided.\n"
            "- Use ONLY the source IDs listed in Sources; do not invent or rename sources.\n"
            "- If sources disagree, state that briefly instead of guessing.\n"
            "- Never output hidden reasoning tags like <think> or analysis notes.\n"
            "- Do not include verification report sections.\n"
        )

        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=1800,
            temperature=0.2,
        )
        if not res.ok:
            return res

        doc = _strip_internal_reasoning(_clean_text(str(res.data.get("text") or "").strip()))
        if not real_sources:
            doc = _strip_inline_numeric_citations(doc)
        doc = _replace_works_cited_section(doc, real_sources)

        return AgentResult(
            ok=True,
            data={
                "document": doc + ("\n" if doc and not doc.endswith("\n") else ""),
                "format": "markdown",
                "sources": real_sources,
                "source_meta": source_meta,
            },
        )
