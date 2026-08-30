from __future__ import annotations

import base64
import html
import json
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import requests


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


def search_wikipedia(query: str, *, max_results: int = 5, timeout: int = 12) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(max_results or 1), 10))
    url = (
        "https://en.wikipedia.org/w/api.php"
        f"?action=query&list=search&srsearch={quote_plus(q)}&format=json&srlimit={limit}&utf8=1"
    )
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    results: list[dict[str, Any]] = []
    for item in list((payload.get("query") or {}).get("search") or []):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        slug = quote_plus(title).replace("+", "_")
        results.append(
            {
                "title": f"Wikipedia - {title}",
                "url": f"https://en.wikipedia.org/wiki/{slug}",
                "snippet": _strip_tags(str(item.get("snippet") or "")),
                "provider": "wikipedia",
            }
        )
    return results


def search_wikidata(query: str, *, max_results: int = 5, timeout: int = 12, language: str = "en") -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(max_results or 1), 10))
    url = (
        "https://www.wikidata.org/w/api.php"
        f"?action=wbsearchentities&search={quote_plus(q)}&language={quote_plus(language)}&format=json&limit={limit}"
    )
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    results: list[dict[str, Any]] = []
    for item in list(payload.get("search") or []):
        qid = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not qid or not label:
            continue
        results.append(
            {
                "title": f"Wikidata - {label}",
                "url": f"https://www.wikidata.org/wiki/{qid}",
                "snippet": desc,
                "provider": "wikidata",
            }
        )
    return results


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "form"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "form"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = str(data or "").strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def _strip_tags(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(text).strip()


def _json_to_text(value: Any, *, max_chars: int) -> str:
    """
    Convert JSON into a compact, human-readable text blob.

    This is intentionally conservative and generic: it collects string values and a
    few common metadata fields. It helps when a URL returns JSON (e.g. some LOC
    endpoints), which would otherwise be dropped and produce empty excerpts.
    """

    parts: list[str] = []
    seen: set[int] = set()

    def _add(text: str) -> None:
        if not text:
            return
        cleaned = re.sub(r"\s+", " ", str(text)).strip()
        if not cleaned:
            return
        parts.append(cleaned)

    def _walk(obj: Any) -> None:
        if obj is None:
            return
        oid = id(obj)
        if oid in seen:
            return
        seen.add(oid)

        if isinstance(obj, str):
            _add(obj)
            return
        if isinstance(obj, (int, float, bool)):
            return
        if isinstance(obj, list):
            for item in obj:
                _walk(item)
                if max_chars and sum(len(p) for p in parts) > max_chars:
                    return
            return
        if isinstance(obj, dict):
            # Prefer some common "document-like" keys first.
            preferred = ("title", "name", "headline", "description", "abstract", "summary", "extract", "snippet")
            for k in preferred:
                if k in obj and isinstance(obj.get(k), str):
                    _add(obj.get(k))
            for _, v in obj.items():
                _walk(v)
                if max_chars and sum(len(p) for p in parts) > max_chars:
                    return
            return

    _walk(value)
    blob = " ".join(parts)
    blob = re.sub(r"\s{2,}", " ", blob).strip()
    if max_chars and len(blob) > max_chars:
        blob = blob[:max_chars]
    return blob


def _decode_ddg_url(href: str) -> str:
    target = html.unescape(str(href or "").strip())
    if target.startswith("//"):
        target = "https:" + target
    if "uddg=" in target:
        try:
            qs = parse_qs(urlparse(target).query)
            if "uddg" in qs:
                decoded = html.unescape(unquote(str(qs["uddg"][0] or "").strip()))
                if decoded.startswith("//"):
                    decoded = "https:" + decoded
                return decoded
        except Exception:
            pass
    return target


def _looks_like_domain_url(text: str) -> bool:
    return bool(re.match(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:[/?#:]|$)", str(text or "").strip(), re.I))


def _coerce_absolute_http_url(url: str) -> str:
    target = html.unescape(str(url or "").strip())
    if not target:
        return ""
    if target.startswith("//"):
        target = "https:" + target
    elif target.startswith("/"):
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I):
        if _looks_like_domain_url(target):
            target = "https://" + target
        else:
            return ""
    return target


def _decode_bing_redirect(href: str) -> str:
    target = _coerce_absolute_http_url(href)
    if not target:
        return ""
    try:
        parsed = urlparse(target)
    except Exception:
        return target
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if not (host.endswith("bing.com") and path.startswith("/ck/a")):
        return target
    try:
        qs = parse_qs(parsed.query)
    except Exception:
        return target
    candidate = str((qs.get("u") or qs.get("url") or qs.get("r") or [""])[0] or "").strip()
    if not candidate:
        return target
    candidate = html.unescape(unquote(candidate))
    normalized = _coerce_absolute_http_url(candidate)
    if normalized:
        return normalized

    # Bing often packs the target URL in base64 with a small prefix.
    tokens = [candidate]
    if len(candidate) > 2 and candidate[:2].lower() == "a1":
        tokens.append(candidate[2:])
    for token in tokens:
        for maybe in (token, token.replace("-", "+").replace("_", "/")):
            try:
                padded = maybe + ("=" * (-len(maybe) % 4))
                decoded = base64.b64decode(padded).decode("utf-8", "ignore")
            except Exception:
                continue
            decoded = html.unescape(unquote(decoded.strip()))
            normalized = _coerce_absolute_http_url(decoded)
            if normalized:
                return normalized
    return target


def _sanitize_search_hit_url(href: str) -> str:
    target = _coerce_absolute_http_url(href)
    if not target:
        return ""

    # Decode DDG wrappers.
    try:
        parsed = urlparse(target)
    except Exception:
        return target
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if host.endswith("duckduckgo.com"):
        if path.startswith("/y.js"):
            return ""
        decoded = _decode_ddg_url(target)
        target = _coerce_absolute_http_url(decoded)
        if not target:
            return ""

    # Decode Bing click wrappers.
    target = _decode_bing_redirect(target)
    if not target:
        return ""
    try:
        parsed = urlparse(target)
    except Exception:
        return target
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if host.endswith("duckduckgo.com"):
        # Help/ad pages are not sources.
        if "duckduckgo-help-pages" in path or path.startswith("/y.js"):
            return ""
        if path.startswith("/l/"):
            return ""
    if host.endswith("bing.com") and path.startswith("/ck/a"):
        return ""
    return target


def _parse_anchor_results(html_text: str, *, class_token: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", html_text or "", re.I | re.S):
        attrs = str(match.group(1) or "")
        label = str(match.group(2) or "")
        class_match = re.search(r'class\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if not class_match:
            continue
        classes = {c.strip().lower() for c in class_match.group(1).split() if c.strip()}
        if class_token.lower() not in classes:
            continue
        href_match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if not href_match:
            continue
        href = _sanitize_search_hit_url(href_match.group(1))
        title = _strip_tags(label)
        if not href or not title:
            continue
        if title.strip().lower() in {"more info", "ad", "advertisement"}:
            continue
        results.append({"title": title, "url": href})
    return results


def _parse_ddg_html(html_text: str) -> list[dict[str, Any]]:
    return _parse_anchor_results(html_text, class_token="result__a")


def _parse_ddg_lite(html_text: str) -> list[dict[str, Any]]:
    return _parse_anchor_results(html_text, class_token="result-link")


def _parse_bing(html_text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for li in re.finditer(r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"[^>]*>(.*?)</li>', html_text or "", re.I | re.S):
        block = str(li.group(1) or "")
        match = re.search(r'<h2[^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.I | re.S)
        if not match:
            match = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.I | re.S)
        if not match:
            continue
        href = _sanitize_search_hit_url(match.group(1))
        title = _strip_tags(match.group(2))
        if not href or not title:
            continue
        results.append({"title": title, "url": href})
    return results


_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}
_FETCH_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL_S = 60 * 60 * 6  # 6 hours
_CACHE_MAX = 256
_CACHE_VERSION = "3"


def _normalize_url_for_dedupe(url: str) -> str:
    target = _coerce_absolute_http_url(url)
    if not target:
        return ""
    try:
        parsed = urlparse(target)
    except Exception:
        return target
    qs = parse_qs(parsed.query)
    filtered = {}
    for k, v in qs.items():
        key = (k or "").lower()
        if key.startswith("utm_") or key in {"fbclid", "gclid", "mc_cid", "mc_eid"}:
            continue
        filtered[k] = v
    query = "&".join(f"{k}={quote_plus(v[0])}" for k, v in filtered.items() if v)
    cleaned = parsed._replace(query=query, fragment="")
    return cleaned.geturl()


def _wants_news_results(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    keywords = (
        "news",
        "headline",
        "today",
        "this week",
        "weekly",
        "daily",
        "latest",
        "breaking",
        "recent",
        "update",
        "press release",
        "earnings",
        "announcement",
    )
    for k in keywords:
        if " " in k:
            if k in q:
                return True
            continue
        if re.search(rf"\b{re.escape(k)}\b", q):
            return True
    return False


def _domain_score(url: str) -> int:
    host = ""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        host = str(url or "").lower()
    if not host:
        return 0
    # Favor generally higher-quality, easier-to-parse sources.
    if host.endswith(".gov") or host.endswith(".mil"):
        return 6
    if host.endswith(".edu") or host.endswith(".ac.uk"):
        return 5
    if "wikipedia.org" in host or "wikidata.org" in host:
        return 5
    if "loc.gov" in host or "archives.gov" in host or "history.state.gov" in host:
        return 5
    if "britannica.com" in host:
        return 4
    if "reuters.com" in host or "apnews.com" in host:
        return 3
    if "github.com" in host:
        return 2
    return 1


def _resolve_redirect(url: str, *, timeout: int) -> str:
    target = str(url or "").strip()
    if not target:
        return ""
    try:
        resp = requests.get(target, headers={"User-Agent": _USER_AGENT}, timeout=timeout, allow_redirects=True)
        return str(resp.url or target)
    except Exception:
        return target


def _resolve_google_news_article(url: str, *, timeout: int) -> str:
    target = str(url or "").strip()
    if not target:
        return ""
    try:
        parsed = urlparse(target)
    except Exception:
        return target
    if "news.google." not in (parsed.netloc or "").lower():
        return target
    if "/rss/articles/" not in (parsed.path or ""):
        return target
    try:
        resp = requests.get(target, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    except Exception:
        return target
    if resp.status_code != 200:
        return target
    html_text = resp.text or ""
    def _reject_candidate(href: str) -> bool:
        try:
            host = urlparse(href).netloc.lower()
            path = urlparse(href).path.lower()
        except Exception:
            host = ""
            path = href.lower()
        if not href.startswith(("http://", "https://")):
            return True
        if host and (
            "news.google." in host
            or "accounts.google." in host
            or "support.google." in host
            or "googleusercontent.com" in host
            or "gstatic.com" in host
            or "google-analytics.com" in host
            or "doubleclick.net" in host
            or host.endswith("googleapis.com")
        ):
            return True
        if any(path.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            return True
        return False

    # Try canonical first.
    match = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', html_text, re.IGNORECASE)
    if match:
        href = match.group(1).strip()
        if href and not _reject_candidate(href):
            return href
    # Otherwise pick the first external https URL.
    for match in re.finditer(r'href="(https?://[^"]+)"', html_text, re.IGNORECASE):
        href = match.group(1).strip()
        if not href or _reject_candidate(href):
            continue
        return href
    return target


def _search_google_news_rss(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    feed = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(feed, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text or "")
    except Exception:
        return []
    items = root.findall(".//item")
    out: list[dict[str, Any]] = []
    for item in items[: max(1, int(max_results or 1)) * 2]:
        title = ""
        link = ""
        try:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
        except Exception:
            continue
        if not title or not link:
            continue
        final_url = _resolve_google_news_article(link, timeout=timeout)
        final_url = _resolve_redirect(final_url, timeout=timeout)
        out.append({"title": title, "url": final_url})
        if len(out) >= max(1, int(max_results or 1)):
            break
    return out


def _wants_encyclopedic_results(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    keywords = (
        "timeline",
        "chronology",
        "history of",
        "historical",
        "background",
        "overview",
        "what happened",
        "key dates",
        "major events",
        "treaty",
        "act",
        "law",
        "invasion",
        "occupation",
    )
    for k in keywords:
        if " " in k:
            if k in q:
                return True
            continue
        if re.search(rf"\b{re.escape(k)}\b", q):
            return True
    # If query includes a year, encyclopedic results are often useful.
    if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", q):
        return True
    return False


def _wants_academic_results(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    keywords = (
        "paper",
        "study",
        "journal",
        "systematic review",
        "meta-analysis",
        "doi",
        "arxiv",
        "preprint",
        "proceedings",
        "conference",
        "citation",
        "market size",
        "market report",
        "industry report",
        "whitepaper",
        "benchmark",
        "survey",
        "dataset",
        "policy brief",
    )
    for k in keywords:
        if " " in k:
            if k in q:
                return True
            continue
        if re.search(rf"\b{re.escape(k)}\b", q):
            return True
    return False


def _search_google_via_jina(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    url = f"https://r.jina.ai/http://www.google.com/search?q={quote_plus(q)}"
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=max(timeout, 20))
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    body = resp.text or ""
    matches = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", body)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _decode_google_redirect(href: str) -> str:
        target = str(href or "").strip()
        if not target:
            return ""
        try:
            parsed = urlparse(target)
        except Exception:
            return target
        host = (parsed.netloc or "").lower()
        if "google." in host and parsed.path.startswith("/url"):
            try:
                qs = parse_qs(parsed.query)
                qv = (qs.get("q") or [""])[0]
                if qv:
                    return qv
            except Exception:
                return target
        return target

    for title, href in matches:
        if len(out) >= max(1, int(max_results or 1)) * 3:
            break
        link = _decode_google_redirect(href)
        if not link:
            continue
        try:
            parsed = urlparse(link)
        except Exception:
            continue
        host = (parsed.netloc or "").lower()
        if not host:
            continue
        if (
            "google." in host
            or "gstatic.com" in host
            or "youtube.com" in host
            or "youtu.be" in host
            or "accounts.google.com" in host
            or "reddit.com" in host
            or "quora.com" in host
            or "stackexchange.com" in host
        ):
            continue
        norm = _normalize_url_for_dedupe(link)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        clean_title = _strip_tags(str(title or "")).strip()
        low_title = clean_title.lower()
        if low_title in {"read more", "learn more", "click here"}:
            continue
        if re.match(r"^\d+\s+answers?$", low_title):
            continue
        if not clean_title:
            clean_title = norm
        out.append({"title": clean_title, "url": norm})
    return out


def _search_wikipedia(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    params = {
        "action": "query",
        "list": "search",
        "srsearch": q,
        "srlimit": max(1, int(max_results or 1)),
        "format": "json",
        "utf8": 1,
    }
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        try:
            payload = json.loads(resp.text or "{}")
        except Exception:
            return []
    hits = (((payload or {}).get("query") or {}).get("search") or []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").strip()
        if not title:
            continue
        url = "https://en.wikipedia.org/wiki/" + quote_plus(title.replace(" ", "_"))
        out.append({"title": title, "url": url})
    return out


def _search_wikidata(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    params = {
        "action": "wbsearchentities",
        "search": q,
        "language": "en",
        "format": "json",
        "limit": max(1, int(max_results or 1)),
    }
    try:
        resp = requests.get(
            "https://www.wikidata.org/w/api.php",
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        try:
            payload = json.loads(resp.text or "{}")
        except Exception:
            return []
    hits = (payload or {}).get("search") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        return []
    out: list[dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        qid = str(hit.get("id") or "").strip()
        label = str(hit.get("label") or "").strip()
        desc = str(hit.get("description") or "").strip()
        if not qid:
            continue
        title = label or qid
        if desc:
            title = f"{title} — {desc}"
        url = f"https://www.wikidata.org/wiki/{qid}"
        out.append({"title": title, "url": url})
    return out


def _search_openalex(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    per_page = max(1, min(10, int(max_results or 5)))
    try:
        resp = requests.get(
            "https://api.openalex.org/works",
            params={"search": q, "per_page": per_page},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    results = (payload or {}).get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    out: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("display_name") or "").strip()
        if not title:
            continue
        landing = ""
        primary = item.get("primary_location") or {}
        if isinstance(primary, dict):
            landing = str(primary.get("landing_page_url") or "").strip()
        if not landing:
            # Prefer DOI resolver if present.
            doi = str(item.get("doi") or "").strip()
            if doi.startswith("https://doi.org/"):
                landing = doi
        if not landing:
            landing = str(item.get("id") or "").strip()
        if not landing:
            continue
        out.append({"title": title, "url": landing})
    return out


def _search_crossref(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    rows = max(1, min(10, int(max_results or 5)))
    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query": q, "rows": rows},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    items = (((payload or {}).get("message") or {}).get("items") or []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        titles = item.get("title") or []
        title = str(titles[0] if isinstance(titles, list) and titles else "").strip()
        url = str(item.get("URL") or "").strip()
        if not title or not url:
            continue
        out.append({"title": title, "url": url})
    return out


def _search_loc(query: str, *, max_results: int, timeout: int) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    url = f"https://www.loc.gov/search/?q={quote_plus(q)}&fo=json"
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    items = list((payload or {}).get("results") or []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for item in items:
        if len(out) >= max(1, int(max_results or 1)):
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        href = str(item.get("url") or "").strip()
        if not title or not href:
            continue
        out.append({"title": f"{title} | Library of Congress", "url": href})
    return out


def _cache_prune(cache: dict, *, now: float) -> None:
    if len(cache) <= _CACHE_MAX:
        return
    # Drop oldest entries.
    items = sorted(cache.items(), key=lambda kv: kv[1][0])
    for key, _val in items[: max(1, len(cache) - _CACHE_MAX)]:
        cache.pop(key, None)


def _query_terms(query: str) -> list[str]:
    text = str(query or "").replace("_", " ").strip().lower()
    if not text:
        return []
    raw = re.findall(r"[a-z0-9][a-z0-9-]+", text)
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "about",
        "into",
        "over",
        "under",
        "than",
        "also",
        "such",
        "their",
        "they",
        "them",
        "what",
        "when",
        "where",
        "which",
        "while",
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
        "topic",
        "key",
        "current",
        "status",
        "person",
        "people",
        "that",
        "who",
        "invented",
        "inventor",
    }
    out: list[str] = []
    seen: set[str] = set()
    for token in raw:
        if token.isdigit():
            continue
        if token in stop:
            continue
        if len(token) < 3:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    # Keep some signal even when prompt is noisy.
    if not out:
        for token in raw:
            if token.isdigit():
                continue
            if len(token) < 3:
                continue
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
            if len(out) >= 8:
                break
    return out[:12]


def _query_relevance_score(query_tokens: list[str], title: str, url: str) -> int:
    if not query_tokens:
        return 0
    hay = f"{title} {url}".replace("_", " ").lower()
    hay_tokens = set(re.findall(r"[a-z0-9][a-z0-9-]+", hay))
    score = 0
    for token in query_tokens:
        if token in hay_tokens:
            score += 3
            continue
        stem = token[:5]
        if stem and any(h.startswith(stem) for h in hay_tokens):
            score += 2
            continue
        if token in hay:
            score += 1
    return score


def search_web(query: str, *, max_results: int = 5, timeout: int = 12) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    cache_key = (f"{_CACHE_VERSION}:{q.lower()}", int(max_results or 5))
    now = time.time()
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return list(cached[1])

    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    query_tokens = _query_terms(q)
    simplified_query = " ".join(query_tokens[:8]).strip()
    query_variants = [q]
    if simplified_query and simplified_query.lower() != q.lower():
        query_variants.append(simplified_query)

    def _collect(query_text: str) -> None:
        urls = [
            ("ddg_html", f"https://duckduckgo.com/html/?q={quote_plus(query_text)}"),
            ("ddg_lite", f"https://lite.duckduckgo.com/lite/?q={quote_plus(query_text)}"),
            ("bing", f"https://www.bing.com/search?q={quote_plus(query_text)}"),
        ]

        if _wants_encyclopedic_results(query_text):
            for item in _search_wikipedia(query_text, max_results=min(4, int(max_results or 5)), timeout=timeout):
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                title = str(item.get("title") or href)
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "origin": "wikipedia"})
            for item in _search_loc(query_text, max_results=min(4, int(max_results or 5)), timeout=timeout):
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                title = str(item.get("title") or href)
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "origin": "loc"})
            for item in _search_wikidata(query_text, max_results=min(3, int(max_results or 5)), timeout=timeout):
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                title = str(item.get("title") or href)
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "origin": "wikidata"})

        if _wants_academic_results(query_text):
            for item in _search_openalex(query_text, max_results=min(3, int(max_results or 5)), timeout=timeout):
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                title = str(item.get("title") or href)
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "origin": "openalex"})
            for item in _search_crossref(query_text, max_results=min(3, int(max_results or 5)), timeout=timeout):
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                title = str(item.get("title") or href)
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "origin": "crossref"})

        if _wants_news_results(query_text):
            for item in _search_google_news_rss(query_text, max_results=min(4, int(max_results or 5)), timeout=timeout):
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                title = str(item.get("title") or href)
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "origin": "google_news_rss"})

        for kind, url in urls:
            try:
                resp = session.get(url, timeout=max(timeout, 20))
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            html_text = resp.text or ""
            if kind == "ddg_html":
                parsed = _parse_ddg_html(html_text)
            elif kind == "ddg_lite":
                parsed = _parse_ddg_lite(html_text)
            else:
                parsed = _parse_bing(html_text)
            for item in parsed:
                href = _normalize_url_for_dedupe(str(item.get("url") or ""))
                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({"title": str(item.get("title") or href), "url": href, "origin": kind})

    for variant in query_variants:
        _collect(variant)
        if len(results) >= max(1, int(max_results or 1)) * 2:
            break

    if len(results) < max(1, int(max_results or 1)):
        fallback_query = simplified_query or q
        for item in _search_google_via_jina(
            fallback_query, max_results=max(2, int(max_results or 5)), timeout=timeout
        ):
            href = _normalize_url_for_dedupe(str(item.get("url") or ""))
            title = str(item.get("title") or href)
            if not href or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href, "origin": "jina_google"})

    # Hard fallback for noisy prompts: always try Wikipedia with simplified keywords.
    if not results and simplified_query:
        for item in _search_wikipedia(simplified_query, max_results=max(2, int(max_results or 5)), timeout=timeout):
            href = _normalize_url_for_dedupe(str(item.get("url") or ""))
            title = str(item.get("title") or href)
            if not href or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href, "origin": "wikipedia"})
        for item in _search_wikidata(simplified_query, max_results=min(3, int(max_results or 5)), timeout=timeout):
            href = _normalize_url_for_dedupe(str(item.get("url") or ""))
            title = str(item.get("title") or href)
            if not href or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href, "origin": "wikidata"})

    # Rank + trim for a more useful mix.
    if simplified_query:
        rank_terms = _query_terms(simplified_query)
    else:
        rank_terms = query_tokens
    scored = [
        (
            _query_relevance_score(rank_terms, str(item.get("title") or ""), str(item.get("url") or "")),
            item,
        )
        for item in results
    ]
    max_rel = max((score for score, _ in scored), default=0)
    if max_rel > 0:
        if max_rel >= 4:
            threshold = max_rel - 1
        elif max_rel >= 2:
            threshold = 2
        else:
            threshold = 1
        candidates = [item for score, item in scored if score >= threshold]
        if not candidates:
            candidates = [item for score, item in scored if score > 0]
    else:
        candidates = [item for _, item in scored]
    ranked = sorted(
        candidates,
        key=lambda r: (
            -_query_relevance_score(rank_terms, str(r.get("title") or ""), str(r.get("url") or "")),
            -_domain_score(str(r.get("url") or "")),
            0 if str(r.get("origin") or "").startswith(("wikipedia", "wikidata")) else 1,
        ),
    )
    final: list[dict[str, Any]] = []
    seen_final: set[str] = set()
    for item in ranked:
        href = _normalize_url_for_dedupe(str(item.get("url") or ""))
        if not href or href in seen_final:
            continue
        seen_final.add(href)
        final.append({"title": str(item.get("title") or href), "url": href})
        if len(final) >= max(1, int(max_results or 1)):
            break

    _SEARCH_CACHE[cache_key] = (now, final)
    _cache_prune(_SEARCH_CACHE, now=now)
    return final


def fetch_url_text(url: str, *, max_chars: int = 4000, timeout: int = 12) -> str:
    target = str(url or "").strip()
    if not target:
        return ""
    now = time.time()
    cached = _FETCH_CACHE.get(target)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return cached[1][:max_chars] if max_chars else cached[1]

    # Prefer structured summaries for Wikipedia articles (less boilerplate).
    try:
        parsed = urlparse(target)
    except Exception:
        parsed = None
    if parsed and parsed.netloc.lower().endswith("wikipedia.org") and "/wiki/" in parsed.path:
        title = parsed.path.split("/wiki/", 1)[1].split("#", 1)[0].strip()
        if title:
            best = ""
            try:
                resp = requests.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                    headers={"User-Agent": _USER_AGENT},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    extract = str((data or {}).get("extract") or "").strip()
                    if extract:
                        best = extract
            except Exception:
                best = ""

            # For longer prompts (history projects), the summary is usually too short and omits key names.
            # Attempt to fetch the full article HTML and extract main text when we have room.
            if max_chars and max_chars >= 6000:
                try:
                    resp = requests.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/html/{title}",
                        headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
                        timeout=timeout,
                    )
                    if resp.status_code == 200 and (resp.text or "").strip():
                        parser = _TextExtractor()
                        try:
                            parser.feed(resp.text)
                            full_text = parser.get_text()
                        except Exception:
                            full_text = _strip_tags(resp.text or "")
                        full_text = re.sub(r"\s+", " ", str(full_text or "")).strip()
                        if full_text and len(full_text) > len(best) + 200:
                            best = full_text
                except Exception:
                    pass

            if best:
                _FETCH_CACHE[target] = (now, best)
                _cache_prune(_FETCH_CACHE, now=now)
                return best[:max_chars] if max_chars else best
    try:
        resp = requests.get(target, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    except Exception:
        return ""
    if resp.status_code != 200:
        # Fallback to a simplified text proxy if direct fetch fails.
        try:
            proxy = f"https://r.jina.ai/{target}" if "://" in target else f"https://r.jina.ai/http://{target}"
            resp = requests.get(proxy, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        except Exception:
            return ""
        if resp.status_code != 200:
            return ""
    ctype = (resp.headers.get("content-type") or "").lower()

    # Some providers return JSON (e.g. certain .gov endpoints). Extract text from it instead
    # of returning empty, because downstream evidence-gating expects non-empty excerpts.
    if "json" in ctype:
        try:
            payload = resp.json()
        except Exception:
            payload = None
        text = _json_to_text(payload, max_chars=max_chars or 0) if payload is not None else ""
        if text:
            _FETCH_CACHE[target] = (now, text)
            _cache_prune(_FETCH_CACHE, now=now)
            time.sleep(0.2)
            return text[:max_chars] if max_chars else text
        # Fall through; some servers mislabel HTML as JSON.

    if "html" in ctype:
        parser = _TextExtractor()
        try:
            parser.feed(resp.text)
            text = parser.get_text()
        except Exception:
            text = _strip_tags(resp.text or "")
    else:
        text = resp.text or ""

    def _clean_extracted_text(target_url: str, raw_text: str) -> str:
        cleaned = str(raw_text or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        lowered = cleaned.lower()
        # Remove common navigation / boilerplate that pollutes LLM prompts.
        boilerplate_phrases = [
            "skip to main content",
            "skip to content",
            "top of page",
            "sign in",
            "log in",
            "cookie",
            "privacy policy",
            "terms of use",
            "subscribe",
            "newsletter",
        ]
        for phrase in boilerplate_phrases:
            cleaned = re.sub(re.escape(phrase), " ", cleaned, flags=re.IGNORECASE)
        if "loc.gov" in target_url.lower() or "library of congress" in lowered:
            cleaned = re.sub(r"special holiday hours in effect[^.]*\.", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\blibrary of congress\b", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\bnotice\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    text = _clean_extracted_text(target, text)
    if len(text) > max_chars:
        text = text[:max_chars]
    _FETCH_CACHE[target] = (now, text)
    _cache_prune(_FETCH_CACHE, now=now)
    time.sleep(0.2)
    return text
