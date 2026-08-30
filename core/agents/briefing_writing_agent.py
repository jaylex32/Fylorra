from __future__ import annotations

from typing import Any
from datetime import datetime
import re

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent


class BriefingWritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="briefing_writing_agent",
            role="writer",
            system_prompt=(
                "You are an executive intelligence editor.\n"
                "Produce a concise, high-signal briefing with prioritized items and clear implications."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="briefing_writing",
                    name="Executive Briefing Writing",
                    description="Generate a concise intelligence briefing.",
                    input_types=["json", "text"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=35,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        request = str(payload.get("user_request") or context.user_request or "").strip()
        notes = payload.get("notes") or payload.get("summary") or payload.get("raw") or ""
        findings = payload.get("findings") or payload.get("highlights") or []
        sources = payload.get("sources") or []
        source_meta = payload.get("source_meta") or []

        if isinstance(findings, list):
            findings_text = "\n".join(f"- {x}" for x in findings if x)
        else:
            findings_text = str(findings)
        if source_meta:
            lines = []
            for meta in source_meta:
                try:
                    sid = int(meta.get("id") or 0)
                except Exception:
                    sid = 0
                title = str(meta.get("title") or "").strip()
                url = str(meta.get("url") or "").strip()
                published = str(meta.get("published_at") or "").strip()
                if not title and url:
                    title = url
                if not title and not url:
                    continue
                prefix = f"[{sid}] " if sid else ""
                line = f"{prefix}{title}".strip()
                if published:
                    line = f"{line} (Published: {published})"
                if url:
                    line = f"{line} - {url}"
                lines.append(line)
            sources_text = "\n".join(f"- {x}" for x in lines if x)
        elif isinstance(sources, list):
            sources_text = "\n".join(f"- {x}" for x in sources if x)
        else:
            sources_text = str(sources)

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
        word_target = 1200 if freq == "weekly" else 900
        user_msg = (
            f"Executive briefing request ({freq}):\n{request}\n\n"
            f"Notes:\n{notes}\n\n"
            f"Findings:\n{findings_text}\n\n"
            f"Sources:\n{sources_text}\n\n"
            "Write a markdown executive intelligence briefing with these REQUIRED sections:\n"
            "1) Title with date/time\n"
            "2) At a Glance (3 bullets: what happened + why it matters)\n"
            "3) Must Read (2-3 stories; include source, published time if known, summary, why it matters, action item if any)\n"
            "4) Should Read (2-3 stories; concise summaries)\n"
            "5) Trend Watch (What's Accelerating, What's Slowing, What's New)\n"
            "6) Good to Know (bulleted items with links and citations)\n"
            "7) FYI - Quick Hits (one-line summaries)\n"
            "8) What to Watch (near-term and longer-term items)\n"
            "9) Sources (list)\n"
            f"Target length: {'1000-1500' if freq == 'weekly' else '500-1000'} words (aim ~{word_target}).\n"
            "Rules:\n"
            "- Use citations [1], [2] inline for specific facts and statistics.\n"
            "- Prioritize recency; if dates are unknown, label items as 'recent'.\n"
            "- Keep story summaries under 150 words.\n"
            "- Avoid confidence scoring, dissenting perspectives, or speculative forecasts.\n"
            "- Maintain a crisp, professional tone."
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=1700,
            temperature=0.25,
        )
        if not res.ok:
            return res
        text = str(res.data.get("text") or "")
        text = _normalize_title(text, freq)
        text = _normalize_dateline(text)
        text = _replace_sources_section(text, sources, source_meta)
        return AgentResult(
            ok=True,
            data={
                "document": text,
                "format": "markdown",
                "sources": sources,
            },
        )


def _normalize_title(doc: str, freq: str) -> str:
    if not doc:
        return doc
    lines = doc.splitlines()
    date_str = datetime.now().strftime("%B %d, %Y")
    month_names = (
        "january|february|march|april|may|june|july|august|september|october|november|december"
    )
    month_rx = re.compile(month_names, re.I)
    bare_date_rx = re.compile(r"\\b\\d{1,2}\\s+20\\d{2}\\b")
    for idx, line in enumerate(lines):
        if line.strip().startswith("#"):
            heading = line.lstrip("#").strip()
            if bare_date_rx.search(heading) or not month_rx.search(heading):
                label = "Executive Intelligence Briefing"
                lines[idx] = f"# {label} - {date_str}"
            break
    else:
        lines.insert(0, f"# Executive Intelligence Briefing - {date_str}")
    return "\n".join(lines)


def _normalize_dateline(doc: str) -> str:
    if not doc:
        return doc
    lines = doc.splitlines()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    updated = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("date/time") or low.startswith("date:") or low.startswith("as of"):
            updated.append(f"Date/Time: {now}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        for idx, line in enumerate(updated[:10]):
            if line.strip().startswith("#"):
                updated.insert(idx + 1, f"Date/Time: {now}")
                replaced = True
                break
    return "\n".join(updated)


def _replace_sources_section(
    doc: str, sources: list | str, source_meta: list[dict[str, Any]] | None
) -> str:
    if not doc:
        return doc
    lines: list[str] = []
    if source_meta:
        for meta in source_meta:
            try:
                sid = int(meta.get("id") or 0)
            except Exception:
                sid = 0
            title = str(meta.get("title") or "").strip()
            url = str(meta.get("url") or "").strip()
            published = str(meta.get("published_at") or "").strip()
            if not title and url:
                title = url
            if not title and not url:
                continue
            prefix = f"[{sid}] " if sid else ""
            line = f"{prefix}{title}".strip()
            if published:
                line = f"{line} (Published: {published})"
            if url:
                line = f"{line} - {url}"
            lines.append(line)
    elif isinstance(sources, list):
        lines = [str(x).strip() for x in sources if str(x).strip()]
    else:
        raw = str(sources or "").strip()
        if raw:
            lines = [raw]
    if not lines:
        return doc
    sources_block = "\n".join(f"- {line}" for line in lines)
    pattern = re.compile(r"(?is)\n##\\s+Sources\\b.*$")
    cleaned = pattern.sub("", doc).rstrip()
    return f"{cleaned}\n\n## Sources\n{sources_block}\n"
