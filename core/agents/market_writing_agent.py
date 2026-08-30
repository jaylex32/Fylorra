from __future__ import annotations

from typing import Any
import re

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent


class MarketWritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="market_writing_agent",
            role="writer",
            system_prompt=(
                "You are a strategic market analyst.\n"
                "Deliver a rigorous market opportunity report with scoring, ranking, and recommendations.\n"
                "Use professional, decision-ready language."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="market_writing",
                    name="Market Opportunity Writing",
                    description="Generate a scored opportunity report.",
                    input_types=["json", "text"],
                    output_types=["text"],
                    requires_internet=False,
                    estimated_time_seconds=55,
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
        claims = payload.get("claims") or []
        source_analysis = payload.get("source_analysis") or {}
        critical = payload.get("critical_analysis") or {}
        context_sections = payload.get("context_sections") or {}

        if isinstance(findings, list):
            findings_text = "\n".join(f"- {x}" for x in findings if x)
        else:
            findings_text = str(findings)
        if isinstance(sources, list):
            sources_text = "\n".join(f"- {x}" for x in sources if x)
        else:
            sources_text = str(sources)
        if isinstance(claims, list):
            claim_lines = []
            for c in claims:
                if not isinstance(c, dict):
                    continue
                text = str(c.get("text") or "")
                score = c.get("confidence_score")
                label = str(c.get("confidence_label") or "")
                flags = c.get("flags") or []
                flags_text = ", ".join(str(x) for x in flags if x)
                conf = f"{score}%" if isinstance(score, (int, float)) else ""
                bits = " | ".join(x for x in (conf, label, flags_text) if x)
                cite_ids = []
                for cid in (c.get("supporting_sources") or []):
                    try:
                        cite_ids.append(int(cid))
                    except Exception:
                        continue
                for cid in (c.get("contradicting_sources") or []):
                    try:
                        cite_ids.append(int(cid))
                    except Exception:
                        continue
                cite_ids = sorted({c for c in cite_ids if c})
                cite_text = f" [{', '.join(str(c) for c in cite_ids)}]" if cite_ids else ""
                if bits:
                    text = f"{text} ({bits})"
                if text:
                    claim_lines.append(f"- {text}{cite_text}")
            claims_text = "\n".join(claim_lines)
        else:
            claims_text = str(claims)

        def _block(label: str, value: Any) -> str:
            if isinstance(value, dict):
                return f"{label}:\n" + "\n".join(f"- {k}: {v}" for k, v in value.items())
            if isinstance(value, list):
                return f"{label}:\n" + "\n".join(f"- {x}" for x in value)
            return f"{label}:\n{value}"

        source_analysis_text = _block("Source analysis", source_analysis)
        critical_text = _block("Critical analysis", critical)
        context_text = _block("Context sections", context_sections)

        top_n = int(self.config.get("top_n_opportunities") or payload.get("top_n_opportunities") or 3)
        weights = payload.get("scoring_weights") or self.config.get("scoring_weights") or {}
        company_ctx = payload.get("company_context") or self.config.get("company_context") or {}
        weight_text = "\n".join(f"- {k}: {v}" for k, v in weights.items()) if weights else "Default (equal weight)."
        company_text = "\n".join(f"- {k}: {v}" for k, v in company_ctx.items()) if company_ctx else "None provided."

        user_msg = (
            f"Market opportunity request:\n{request}\n\n"
            f"Notes:\n{notes}\n\n"
            f"Findings:\n{findings_text}\n\n"
            f"Claims with confidence:\n{claims_text}\n\n"
            f"{source_analysis_text}\n\n"
            f"{critical_text}\n\n"
            f"{context_text}\n\n"
            f"Scoring weights:\n{weight_text}\n\n"
            f"Company context:\n{company_text}\n\n"
            f"Sources:\n{sources_text}\n\n"
            "Write a professional market opportunity analysis in markdown with these REQUIRED sections:\n"
            "1) Title\n"
            "2) Executive Summary (2-3 short paragraphs)\n"
            "3) Opportunity Overview (table with Opportunity, Score, Market Size, Growth, Competition, Fit, Barriers, Recommendation)\n"
            "4) Scoring Framework (brief description of the five dimensions)\n"
            f"5) Detailed Analysis (top {top_n} opportunities with market dynamics, competition, strategic fit, "
            "financial projections TAM/SAM/SOM, go-to-market, and risks)\n"
            "6) Confidence Assessment (High/Medium/Low with percent ranges)\n"
            "7) Critical Analysis (assumptions, dependencies, barriers, risks)\n"
            "8) What We Don't Know (data gaps and unknowns)\n"
            "9) Recommendations by Priority (High, Medium, Monitor, Do Not Pursue)\n"
            "10) Sources\n"
            "Rules:\n"
            "- Score each opportunity 0-10 on Market Size, Growth Rate, Competitive Intensity, Strategic Fit, Barriers to Entry.\n"
            "- Compute overall score as the average (or weighted if provided) and label rating (Excellent/Good/Fair/Poor).\n"
            "- Include TAM/SAM/SOM and 3-year revenue potential when data allows; if unknown, state assumptions.\n"
            "- Cite sources inline using [1], [2] for facts and market data.\n"
            "- Avoid hype; be decision-focused and realistic.\n"
            "- For Confidence Assessment, use headings with ranges:\n"
            "  - High Confidence (80-90%)\n"
            "  - Medium Confidence (60-75%)\n"
            "  - Low Confidence (40-55%)\n"
            "- Avoid AI-sounding filler and keep language executive-ready."
        )
        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=2100,
            temperature=0.25,
        )
        if not res.ok:
            return res
        text = str(res.data.get("text") or "")

        def _restore_confidence_headers(doc: str) -> str:
            if not doc:
                return doc
            lines = doc.splitlines()
            out = []
            for line in lines:
                stripped = line.strip()
                low = stripped.lower()
                if low.startswith("### high confidence") or low.startswith("## high confidence"):
                    line = line.split("(")[0].rstrip()
                    line = f"{line} (80-90%)"
                elif low.startswith("### medium confidence") or low.startswith("## medium confidence"):
                    line = line.split("(")[0].rstrip()
                    line = f"{line} (60-75%)"
                elif low.startswith("### low confidence") or low.startswith("## low confidence"):
                    line = line.split("(")[0].rstrip()
                    line = f"{line} (40-55%)"
                elif low.startswith("- **high confidence") or low.startswith("* **high confidence"):
                    line = line.replace("**High Confidence**", "**High Confidence (80-90%)**")
                elif low.startswith("- **medium confidence") or low.startswith("* **medium confidence"):
                    line = line.replace("**Medium Confidence**", "**Medium Confidence (60-75%)**")
                elif low.startswith("- **low confidence") or low.startswith("* **low confidence"):
                    line = line.replace("**Low Confidence**", "**Low Confidence (40-55%)**")
                out.append(line)
            return "\n".join(out)

        text = _restore_confidence_headers(text)
        text = _replace_sources_section(text, sources, source_meta)
        return AgentResult(
            ok=True,
            data={
                "document": text,
                "format": "markdown",
                "sources": sources,
                "claims": claims,
                "source_meta": source_meta,
                "source_analysis": source_analysis,
            },
        )


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
            if not title and url:
                title = url
            if not title and not url:
                continue
            prefix = f"[{sid}] " if sid else ""
            if url:
                lines.append(f"{prefix}{title} - {url}".strip())
            else:
                lines.append(f"{prefix}{title}".strip())
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
