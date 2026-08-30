"""
Fylorra - AI Search
Turn natural language queries into effective local index searches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import json
import re
import threading

from core.library_index import LibraryIndex, LibraryItem


@dataclass(frozen=True)
class AISearchResult:
    item: LibraryItem
    matched_query: str
    used_ai: bool = False
    used_rerank: bool = False


def _ai_rewrite_query(ai_manager, user_query: str) -> Optional[str]:
    """
    Ask the model to rewrite a user query into a compact keyword query suitable for SQLite FTS.
    """
    if not ai_manager or not getattr(ai_manager, "is_ready", False):
        return None

    prompt = (
        "Rewrite the user request into a compact query for a LOCAL file index.\n"
        "The query will be used with SQLite FTS (MATCH).\n"
        "Rules:\n"
        "- Output ONLY the query text (no JSON, no markdown).\n"
        "- Use 3 to 10 keywords/phrases.\n"
        "- Prefer vendor names, document types, identifiers, dates, and error phrases.\n"
        "- Use OR between alternatives when helpful.\n"
        "- Avoid punctuation and special operators. No colon, no brackets.\n"
        "User request: " + user_query
    )

    try:
        resp = ai_manager.model.create_chat_completion(
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            temperature=0.2,
            max_tokens=200,
        )
        content = (resp["choices"][0]["message"]["content"] or "").strip()
        # Take first non-empty line, strip quotes/backticks.
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            return None
        q = lines[0].strip("`\"' ").strip()
        return q or None
    except Exception:
        return None


def _sanitize_search_query(query: str, *, fallback: str = "") -> str:
    """
    Keep model/user text within the simple SQLite FTS syntax this app expects.
    Bad model rewrites with punctuation/operators can otherwise produce empty or failing searches.
    """
    q = (query or "").strip()
    if not q:
        q = (fallback or "").strip()
    if not q:
        return ""

    # Remove common wrappers and characters that are meaningful to FTS but confusing here.
    q = re.sub(r"^```(?:\w+)?\s*", " ", q, flags=re.IGNORECASE).strip()
    q = re.sub(r"\s*```$", " ", q).strip()
    q = re.sub(r"[\[\]{}():^~*+\"]", " ", q)
    q = q.replace("\\", " ").replace("/", " ")
    raw_tokens = q.split()

    tokens: list[str] = []
    for tok in raw_tokens:
        upper = tok.upper()
        if upper in {"OR", "AND", "NOT"}:
            if tokens and tokens[-1] not in {"OR", "AND", "NOT"}:
                tokens.append(upper)
            continue
        clean = "".join(ch for ch in tok if ch.isalnum() or ch in {"_", "-", "."}).strip("._-")
        if len(clean) >= 2:
            tokens.append(clean)

    if tokens and tokens[0].lower() in {"json", "markdown", "text"}:
        tokens.pop(0)

    # Avoid dangling operators.
    while tokens and tokens[-1] in {"OR", "AND", "NOT"}:
        tokens.pop()
    while tokens and tokens[0] in {"OR", "AND"}:
        tokens.pop(0)

    if not tokens:
        return _sanitize_search_query(fallback) if fallback and fallback != query else ""
    return " ".join(tokens[:16])


def _strip_wrappers(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            t = parts[1].strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    return t.strip()


def _extract_first_json_object(text: str) -> Optional[str]:
    t = _strip_wrappers(text)
    if not t:
        return None
    start = t.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return t[start : i + 1]
    return None


def _extract_json(text: str) -> Optional[dict]:
    t = _strip_wrappers(text)
    if not t:
        return None
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    candidate = _extract_first_json_object(t)
    if candidate:
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            try:
                import ast

                obj = ast.literal_eval(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    return None


def _ai_rerank(ai_manager, user_query: str, items: list[LibraryItem], *, top_n: int = 30, keep: int = 12) -> Optional[list[LibraryItem]]:
    if not ai_manager or not getattr(ai_manager, "is_ready", False):
        return None
    if not items:
        return None

    candidates = items[: max(1, int(top_n))]

    def snippet(it: LibraryItem) -> str:
        t = (it.ai_summary or it.extracted_text or "").strip()
        if not t:
            return ""
        t = re.sub(r"\s+", " ", t).strip()
        return t[:240]

    lines = []
    for i, it in enumerate(candidates, start=1):
        lines.append(f"{i}. name={it.name} ext={it.ext} text={snippet(it)}")

    prompt = (
        "You are ranking local files for a search.\n"
        "Return ONLY JSON:\n"
        "{\"order\": [list of candidate numbers, best first]}\n"
        f"User query: {user_query}\n"
        "Candidates:\n" + "\n".join(lines)
    )

    try:
        resp = ai_manager.model.create_chat_completion(
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            temperature=0.1,
            max_tokens=180,
        )
        content = (resp["choices"][0]["message"]["content"] or "").strip()
        data = _extract_json(content) or {}
        order = data.get("order")
        if not isinstance(order, list) or not order:
            return None
        ranked: list[LibraryItem] = []
        seen: set[int] = set()
        for v in order:
            try:
                idx = int(v)
            except Exception:
                continue
            if idx < 1 or idx > len(candidates) or idx in seen:
                continue
            seen.add(idx)
            ranked.append(candidates[idx - 1])
            if len(ranked) >= int(keep):
                break

        if not ranked:
            return None

        # Append remaining candidates (stable) to keep the list complete.
        for i, it in enumerate(candidates, start=1):
            if i not in seen:
                ranked.append(it)
        if len(items) > len(candidates):
            ranked.extend(items[len(candidates) :])
        return ranked
    except Exception:
        return None


def ai_search(
    library: LibraryIndex,
    user_query: str,
    *,
    ai_manager=None,
    limit: int = 50,
    rerank: bool = True,
    folder=None,
    progress_cb=None,
) -> list[AISearchResult]:
    """
    AI-assisted local search.
    - If AI is available, rewrite into strong keywords.
    - Always falls back to plain search.
    """
    user_query = (user_query or "").strip()
    if not user_query:
        return []

    def _call_with_timeout(fn, timeout_s: float, default=None):
        out = {"val": default}
        done = threading.Event()

        def run():
            try:
                out["val"] = fn()
            except Exception:
                out["val"] = default
            finally:
                done.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        done.wait(timeout_s)
        return out["val"]

    if progress_cb:
        try:
            progress_cb("Rewriting query…")
        except Exception:
            pass
    # Model calls can occasionally stall; keep the UI responsive by timing out and falling back.
    rewritten = _call_with_timeout(lambda: _ai_rewrite_query(ai_manager, user_query), 12.0, default=None)
    used_ai = bool(rewritten)

    def fallback_query(q: str) -> str:
        # FTS MATCH uses AND by default; NL queries often need OR semantics.
        stop = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "to",
            "from",
            "with",
            "without",
            "of",
            "in",
            "on",
            "for",
            "that",
            "this",
            "show",
            "find",
            "give",
            "me",
            "my",
            "all",
        }
        tokens = []
        for t in (q or "").replace("/", " ").replace("\\", " ").split():
            t2 = "".join(ch for ch in t if ch.isalnum() or ch in {"_", "-", "."}).strip()
            if len(t2) < 3:
                continue
            if t2.lower() in stop:
                continue
            tokens.append(t2)
        if not tokens:
            return q
        if len(tokens) == 1:
            return tokens[0]
        # OR tokens to avoid over-restricting.
        return " OR ".join(tokens[:8])

    search_query = _sanitize_search_query(rewritten or fallback_query(user_query), fallback=fallback_query(user_query))
    if not search_query:
        search_query = fallback_query(user_query)

    # Some callers want results constrained to a particular folder.
    # LibraryIndex supports this via a `folder=` kwarg; fall back gracefully for other implementations.
    if progress_cb:
        try:
            progress_cb(f"Searching index… ({search_query})")
        except Exception:
            pass
    try:
        try:
            items = library.search(search_query, limit=limit, folder=folder)
        except TypeError:
            items = library.search(search_query, limit=limit)
    except Exception:
        # Retry with the plain fallback query if AI produced an FTS-hostile query.
        search_query = _sanitize_search_query(fallback_query(user_query), fallback=user_query)
        try:
            try:
                items = library.search(search_query, limit=limit, folder=folder)
            except TypeError:
                items = library.search(search_query, limit=limit)
        except Exception:
            items = []
        used_ai = False

    # Belt-and-suspenders: enforce folder scoping even if the underlying index/search
    # implementation ignores/doesn't support `folder=`.
    if folder and items:
        try:
            from pathlib import Path

            scope = str(Path(folder).resolve()).replace("\\", "/").rstrip("/").lower() + "/"

            def in_scope(p: str) -> bool:
                try:
                    norm = str(p or "").replace("\\", "/").lower()
                    return norm.startswith(scope)
                except Exception:
                    return False

            items = [it for it in items if in_scope(getattr(it, "path", ""))]
        except Exception:
            pass
    used_rerank = False
    if rerank and ai_manager and getattr(ai_manager, "is_ready", False) and len(items) >= 6:
        if progress_cb:
            try:
                progress_cb("AI reranking…")
            except Exception:
                pass
        reranked = _call_with_timeout(
            lambda: _ai_rerank(ai_manager, user_query, items, top_n=30, keep=min(12, limit)),
            18.0,
            default=None,
        )
        if reranked:
            items = reranked[:limit]
            used_rerank = True

    if progress_cb:
        try:
            progress_cb(f"Done. {len(items)} result(s).")
        except Exception:
            pass
    return [AISearchResult(item=i, matched_query=search_query, used_ai=used_ai, used_rerank=used_rerank) for i in items]
