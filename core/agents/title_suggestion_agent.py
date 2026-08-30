from __future__ import annotations

import re
from typing import Any

from core.agents.llm_agent import _LLMBaseAgent, _safe_json
from core.pipeline.agent import AgentCapability, AgentResult


def _extract_heading_title(document: str) -> str:
    text = str(document or "")
    for line in text.splitlines():
        m = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if m:
            return str(m.group(1)).strip()
    return ""


def _clean_topic(request: str) -> str:
    text = str(request or "").strip()
    if not text:
        return ""
    patterns = [
        r"(?i)^\s*(create|write|make|generate)\s+",
        r"(?i)\b(a|an)\s+(school\s+)?(project|assignment|essay|report|biography)\b",
        r"(?i)\b(for|about|on)\b",
    ]
    out = text
    for pat in patterns:
        out = re.sub(pat, " ", out)
    out = re.sub(r"\s+", " ", out).strip(" .:-")
    return out


def _clean_title(title: str) -> str:
    t = str(title or "").strip()
    t = t.strip("\"'` ")
    t = re.sub(r"\s+", " ", t)
    return t[:140].strip()


def _dedupe_titles(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        t = _clean_title(raw)
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _fallback_titles(topic: str, current_title: str) -> list[str]:
    base = _clean_title(topic) or _clean_title(current_title) or "School Assignment"
    if base and base == base.lower():
        base = base.title()
    seeds = [
        base,
        f"The History of {base}",
        f"Understanding {base}",
        f"Key Facts About {base}",
        f"{base}: A School Assignment",
    ]
    return _dedupe_titles(seeds)[:5]


class TitleSuggestionAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="title_suggestion_agent",
            role="editor",
            system_prompt=(
                "You write polished, student-friendly assignment titles.\n"
                "Always return concise, school-appropriate options."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="title_suggestions",
                    name="Title Suggestions",
                    description="Generate five assignment title options for user selection.",
                    input_types=["text", "json"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=12,
                )
            ],
            config=config or {},
        )

    def execute(self, context, inputs: dict[str, Any] | None = None) -> AgentResult:
        payload = dict(inputs or {})
        document = str(
            payload.get("document")
            or payload.get("improved_text")
            or payload.get("text")
            or ""
        ).strip()
        request = str(payload.get("user_request") or context.user_request or "").strip()
        if "_" in request and " " not in request:
            request = request.replace("_", " ").strip()
        current_title = _extract_heading_title(document)
        topic = _clean_topic(request) or current_title

        prompt = (
            "Create exactly 5 title options for a school assignment.\n"
            "Return strict JSON with keys:\n"
            "- title_options (array of exactly 5 strings)\n"
            "- recommended_index (1-5)\n\n"
            "Rules:\n"
            "- Keep titles clear, professional, and age-appropriate.\n"
            "- Avoid clickbait and slang.\n"
            "- Keep each title under 14 words.\n"
            "- Match the assignment topic and final draft content.\n\n"
            f"User request: {request or '(none)'}\n"
            f"Detected topic: {topic or '(none)'}\n"
            f"Current title: {current_title or '(none)'}\n"
            f"Draft preview:\n{document[:1600]}"
        )

        titles: list[str] = []
        recommended_index = 1
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_format="json",
            max_tokens=260,
            temperature=0.2,
        )
        if res.ok:
            parsed = _safe_json(str((res.data or {}).get("text") or ""))
            raw_options = parsed.get("title_options")
            if isinstance(raw_options, list):
                titles = _dedupe_titles([str(x) for x in raw_options])
            try:
                recommended_index = int(parsed.get("recommended_index") or 1)
            except Exception:
                recommended_index = 1

        if len(titles) < 5:
            titles = _dedupe_titles(titles + _fallback_titles(topic=topic, current_title=current_title))

        # Guarantee exactly 5 options.
        while len(titles) < 5:
            titles.append(f"{topic or 'School Assignment'} ({len(titles) + 1})")
        titles = titles[:5]

        if recommended_index < 1 or recommended_index > len(titles):
            recommended_index = 1

        out: dict[str, Any] = {
            "document": document,
            "title_options": titles,
            "recommended_index": recommended_index,
            "recommended_title": titles[recommended_index - 1],
            "format": "markdown",
        }
        if payload.get("sources") is not None:
            out["sources"] = payload.get("sources")
        if payload.get("source_meta") is not None:
            out["source_meta"] = payload.get("source_meta")
        return AgentResult(ok=True, data=out)
