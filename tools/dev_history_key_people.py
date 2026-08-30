"""
Quick inspection tool for Workflow Automation "History Project" outputs.

Usage (PowerShell):
  python tools/dev_history_key_people.py
  python tools/dev_history_key_people.py --execution "<home>\\.fylorra\\pipelines\\executions\\<id>.json"
  python tools/dev_history_key_people.py --markdown "<Documents>\\Workflows\\Exports\\workflow_output.md"
  python tools/dev_history_key_people.py --regenerate --hydrate-excerpts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.parse import unquote, urlparse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fetch_wikipedia_extract(url: str, *, max_chars: int, timeout: int) -> str:
    """
    Fetch a larger plain-text extract for Wikipedia pages.

    Note: core.integrations.web_search.fetch_url_text prefers the REST summary (short);
    for Key People grounding we want more body text so names appear.
    """
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return ""
    if not parsed.netloc.lower().endswith("wikipedia.org"):
        return ""
    if "/wiki/" not in parsed.path:
        return ""
    title = parsed.path.split("/wiki/", 1)[1].split("#", 1)[0].strip()
    if not title:
        return ""
    title = unquote(title)
    try:
        import requests

        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "exsectionformat": "plain",
                "format": "json",
                "titles": title,
            },
            timeout=timeout,
            headers={"User-Agent": "Fylorra/1.0"},
        )
    except Exception:
        return ""
    if resp.status_code != 200:
        return ""
    try:
        payload = resp.json()
    except Exception:
        return ""
    pages = (payload.get("query") or {}).get("pages") or {}
    for _, page in pages.items():
        extract = str((page or {}).get("extract") or "")
        extract = extract.strip()
        return extract[:max_chars] if max_chars else extract
    return ""


def _fetch_text_for_excerpt(url: str, *, max_chars: int, timeout: int) -> str:
    wiki = _fetch_wikipedia_extract(url, max_chars=max_chars, timeout=timeout)
    if wiki:
        return wiki
    try:
        from core.integrations.web_search import fetch_url_text

        return fetch_url_text(url, max_chars=max_chars, timeout=timeout)
    except Exception:
        return ""


def _latest_execution_file() -> Path | None:
    exec_dir = Path(os.path.expanduser("~/.fylorra/pipelines/executions"))
    files = sorted(exec_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_section(markdown: str, title: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(title)}\s*$\r?\n(.*?)(?=^##\s+|\Z)")
    match = pattern.search(markdown or "")
    return (match.group(1) if match else "").strip()


def _summarize_key_people(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        out.append(text)
    return out


def _warn_key_people(lines: list[str]) -> list[str]:
    warnings: list[str] = []
    for idx, line in enumerate(lines, start=1):
        txt = line.strip()
        if not txt:
            continue
        if not re.search(r"\[\s*\d+\s*\]", txt):
            warnings.append(f"{idx}: missing citation -> {txt}")
        head = re.sub(r"\[\d+\]", "", txt).strip()
        # Only split on safe separators so we don't break hyphenated names or abbreviations.
        head = re.split(r"\s*(?:---|--|—|–|:|\s-\s)\s*", head, maxsplit=1)[0].strip()
        if re.search(r"\b(?:battle|campaign|treaty|act|law|report)\b", head, flags=re.IGNORECASE):
            warnings.append(f"{idx}: looks like non-person entity -> {txt}")
        if len(head.split()) > 6:
            warnings.append(f"{idx}: too many tokens for a name -> {txt}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", type=str, default="")
    parser.add_argument("--markdown", type=str, default="")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Rebuild a structured (no-LLM) draft from the saved research output to test Key People extraction quickly.",
    )
    parser.add_argument(
        "--hydrate-excerpts",
        action="store_true",
        help="If the execution JSON lacks research.source_records, download text for each source_meta URL and build source_records so we can evidence-gate Key People without rerunning the full pipeline.",
    )
    parser.add_argument("--max-chars", type=int, default=12000, help="Max chars per fetched source excerpt.")
    parser.add_argument("--timeout", type=int, default=12, help="HTTP timeout (seconds) when hydrating excerpts.")
    args = parser.parse_args()

    if args.execution:
        exec_path = Path(args.execution)
    else:
        exec_path = _latest_execution_file()
    if exec_path and exec_path.exists():
        print(f"Execution: {exec_path}")
        payload = _read_json(exec_path)
        research = (payload.get("outputs") or {}).get("research") or {}
        draft = (payload.get("outputs") or {}).get("draft") or {}
        request = str(payload.get("request") or "").strip()
        key_figures = research.get("key_figures") or []
        print(f"Research key_figures: {len(key_figures)}")
        for item in key_figures[:20]:
            print(f"  - {item}")

        if args.hydrate_excerpts:
            try:
                source_records = list(research.get("source_records") or [])

                def _has_any_text(records: list[dict[str, Any]]) -> bool:
                    for rec in records:
                        if str(rec.get("text") or "").strip():
                            return True
                        if str(rec.get("text_excerpt") or "").strip():
                            return True
                    return False

                if source_records and _has_any_text(source_records):
                    print(f"\nExecution already has source_records with text: {len(source_records)}")
                else:
                    source_meta = list(research.get("source_meta") or [])
                    built: list[dict[str, Any]] = []
                    for meta in source_meta:
                        try:
                            sid = int(meta.get("id"))
                        except Exception:
                            continue
                        url = str(meta.get("url") or "").strip()
                        title = str(meta.get("title") or url).strip()
                        origin = str(meta.get("origin") or "web").strip()
                        if not url:
                            continue
                        text = _fetch_text_for_excerpt(url, max_chars=int(args.max_chars), timeout=int(args.timeout))
                        built.append(
                            {
                                "id": sid,
                                "title": title,
                                "url": url,
                                "origin": origin,
                                # Keep both keys because some pipeline code uses `text_excerpt`, while others use `text`.
                                "text": text,
                                "text_excerpt": text,
                            }
                        )
                    research = dict(research)
                    research["source_records"] = built
                    print(f"\nHydrated source_records: {len(built)}")
            except Exception as exc:
                print(f"\nFailed to hydrate excerpts: {exc}")

        doc = draft.get("document") or ""
        if args.regenerate:
            try:
                from core.agents.history_project_writing_agent import HistoryProjectWritingAgent
                from core.pipeline.context import PipelineContext

                ctx = PipelineContext(
                    pipeline_id=str(payload.get("pipeline_id") or "dev"),
                    user_request=request,
                    initial_parameters={},
                    services={},
                    stage_outputs={},
                    stage_metadata={},
                    working_directory=Path.cwd(),
                    temp_files=[],
                    current_stage=0,
                    total_stages=1,
                    should_abort=False,
                    abort_reason=None,
                    approval_pending=False,
                    approval_data=None,
                )
                agent = HistoryProjectWritingAgent(config={"structured_output": True})
                regenerated = agent.execute(ctx, inputs=research)
                if regenerated.ok and regenerated.data:
                    doc = str(regenerated.data.get("document") or doc)
                    print("\nRegenerated structured draft (no LLM).")
                else:
                    print(f"\nFailed to regenerate structured draft: {regenerated.message}")
            except Exception as exc:
                print(f"\nFailed to regenerate structured draft: {exc}")

        kp_section = _extract_section(doc, "Key People")
        kp_lines = [ln for ln in kp_section.splitlines() if ln.strip().startswith("-")]
        kp_lines = _summarize_key_people(kp_lines)
        print(f"\nDraft Key People lines: {len(kp_lines)}")
        for ln in kp_lines[:30]:
            print(f"  {ln}")

        warns = _warn_key_people(kp_lines)
        if warns:
            print("\nWarnings:")
            for w in warns[:50]:
                print(f"  - {w}")
        else:
            print("\nNo obvious issues detected in Key People formatting.")
    else:
        print("No execution JSON found. Use --execution to point to an execution file.")

    if args.markdown:
        md_path = Path(args.markdown)
        if md_path.exists():
            text = md_path.read_text(encoding="utf-8", errors="replace")
            kp_section = _extract_section(text, "Key People")
            kp_lines = [ln for ln in kp_section.splitlines() if ln.strip().startswith("-")]
            kp_lines = _summarize_key_people(kp_lines)
            print(f"\nMarkdown: {md_path}")
            print(f"Key People lines: {len(kp_lines)}")
            for ln in kp_lines[:30]:
                print(f"  {ln}")
            warns = _warn_key_people(kp_lines)
            if warns:
                print("\nWarnings:")
                for w in warns[:50]:
                    print(f"  - {w}")
        else:
            print(f"Markdown not found: {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
