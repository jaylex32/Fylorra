from __future__ import annotations

from typing import Any

from core.pipeline.agent import AgentCapability, AgentResult
from core.agents.llm_agent import _LLMBaseAgent


class WritingAgent(_LLMBaseAgent):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(
            agent_id="writing_agent",
            role="writer",
            system_prompt=(
                "You are a critical, professional writing agent.\n"
                "Turn inputs into a balanced, publication-ready report with calibrated uncertainty.\n"
                "Use clear headings, an executive summary, and concise paragraphs.\n"
                "Prefer markdown with section headings and bullet lists where helpful.\n"
                "Avoid hype; include risks, caveats, and opposing perspectives."
            ),
            capabilities=[
                AgentCapability(
                    capability_id="writing",
                    name="Professional Writing",
                    description="Transform notes into a structured document.",
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
        notes = payload.get("notes") or payload.get("summary") or payload.get("raw") or ""
        findings = payload.get("findings") or payload.get("highlights") or []
        sources = payload.get("sources") or []
        source_meta = payload.get("source_meta") or []
        claims = payload.get("claims") or []
        temporal = payload.get("temporal_context") or {}
        source_analysis = payload.get("source_analysis") or {}
        source_validation = payload.get("source_validation") or {}
        critical = payload.get("critical_analysis") or {}
        dissenting = payload.get("dissenting_views") or []
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

        temporal_text = _block("Temporal context", temporal)
        source_analysis_text = _block("Source analysis", source_analysis)
        source_validation_text = _block("Source validation", source_validation)
        critical_text = _block("Critical analysis", critical)
        dissenting_text = _block("Dissenting views", dissenting)
        context_text = _block("Context sections", context_sections)

        user_msg = (
            f"User request:\n{request}\n\n"
            f"Notes:\n{notes}\n\n"
            f"Findings:\n{findings_text}\n\n"
            f"Claims with confidence:\n{claims_text}\n\n"
            f"{temporal_text}\n\n"
            f"{source_analysis_text}\n\n"
            f"{source_validation_text}\n\n"
            f"{critical_text}\n\n"
            f"{dissenting_text}\n\n"
            f"{context_text}\n\n"
            f"Sources:\n{sources_text}\n\n"
            "Write a professional report in markdown with these REQUIRED sections:\n"
            "1) Title\n"
            "2) Executive Summary\n"
            "3) Key Findings (bullets)\n"
            "4) Analysis (balanced; cite sources)\n"
            "5) Critical Analysis (assumptions, dependencies, barriers, risks)\n"
            "6) Challenges & Considerations (Regulatory, Safety & Risk, Sustainability, Ethics, Implementation)\n"
            "7) Dissenting Perspectives (mainstream vs alternative)\n"
            "8) Confidence Assessment (High/Medium/Low predictions with rationale)\n"
            "9) What We Don't Know (unknowns, data gaps, further research)\n"
            "10) Risk Factors (technical, business, timeline, adoption)\n"
            "11) Recommendations (tiered by confidence with caveats)\n"
            "12) Sources (if provided)\n"
            "For Confidence Assessment, use headings with ranges:\n"
            "- High Confidence (80-90%)\n"
            "- Medium Confidence (60-75%)\n"
            "- Low Confidence (40-55%)\n"
            "Use complete sentences and a formal tone.\n"
            "Avoid AI-sounding filler (e.g., 'As an AI', 'In conclusion', 'Additionally' repeated).\n"
            "Prefer concise, confident phrasing with varied sentence structure.\n"
            "Cite sources inline using [1], [2] when referencing facts.\n"
            "Distribute citations across relevant sources; do not cite everything as [1].\n"
            "For any forward-looking claim, include a confidence label and caveat.\n"
            "If sources are limited, explicitly note that findings are preliminary."
        )

        res = self._run_llm(
            context=context,
            system_prompt=self.system_prompt,
            user_message=user_msg,
            response_format="text",
            max_tokens=1900,
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
