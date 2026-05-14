"""Web search via DuckDuckGo. Falls back to HTML scrape if API is thin."""

import re

from agent_core.constants import (WEB_SEARCH_DEFAULT_MAX_RESULTS,
                                  WEB_SEARCH_TIMEOUT_SECONDS)

try:
    import requests
except ImportError:
    requests = None


def web_search(query: str, max_results: int = WEB_SEARCH_DEFAULT_MAX_RESULTS) -> str:
    if not query or not query.strip():
        return "Empty query"

    if requests is None:
        return "[error] requests library not installed (pip install requests)"

    query = query.strip()

    # Try the Instant Answer API first
    try:
        res = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=WEB_SEARCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "AI_Assistant/1.0"},
        )
        data = res.json()

        results: list[str] = []

        if data.get("AbstractText"):
            results.append(data["AbstractText"])

        for item in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(item, dict) and "Text" in item:
                results.append(item["Text"])

        if results:
            return "\n---\n".join(results[:max_results])
    except Exception:
        pass  # Fall through to HTML scrape

    # Fallback: HTML scrape (very small scale)
    try:
        res = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=WEB_SEARCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 AI_Assistant/1.0"},
        )
        snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', res.text, re.S)
        cleaned = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets if s.strip()]
        if cleaned:
            return "\n---\n".join(cleaned[:max_results])
    except Exception:
        pass

    return f"No results for: {query}"
