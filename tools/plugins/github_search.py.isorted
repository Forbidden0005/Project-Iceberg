"""
GitHub Search plugin for Project Iceberg.

Hits the GitHub Search API to find repositories and code files.
No authentication needed for public searches (60 req/hour unauthenticated).
Set GITHUB_TOKEN env var to raise the limit to 5,000 req/hour.

Tools exposed:
  github_search(query, kind, max_results) -> formatted result string
"""

import os

try:
    import requests as _requests
except ImportError:
    _requests = None


# ---------------------------------------------------------------------------
# Core search function
# ---------------------------------------------------------------------------


def github_search(
    query: str,
    kind: str = "repositories",
    max_results: int = 8,
) -> str:
    """
    Search GitHub for repositories or code files.

    Args:
        query:       Search terms, e.g. "windows desktop security python".
                     Supports GitHub qualifiers like "language:python", "stars:>100".
        kind:        "repositories" (default) or "code".  Repositories returns
                     project-level results; code returns individual file matches.
        max_results: How many results to return (max 10).

    Returns:
        Formatted string with names, descriptions, URLs, and star counts.

    Examples:
        github_search("windows security python")
        github_search("UAC bypass python", kind="code")
        github_search("antivirus evasion language:python stars:>50")
    """
    if _requests is None:
        return "[error] requests library not installed"

    query = (query or "").strip()
    if not query:
        return "[error] empty query"

    # Clamp results to a sensible range
    max_results = max(1, min(max_results, 10))

    # Validate kind
    if kind not in ("repositories", "code"):
        kind = "repositories"

    # Build request
    url = f"https://api.github.com/search/{kind}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ProjectIceberg/1.0",
    }
    # Token resolution: env var > config.json > unauthenticated (60 req/hour)
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        try:
            import json as _json

            _cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
            with open(os.path.normpath(_cfg_path)) as _f:
                token = _json.load(_f).get("github_token", "")
        except Exception:
            pass
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "q": query,
        "per_page": max_results,
        "sort": "stars" if kind == "repositories" else "indexed",
        "order": "desc",
    }

    try:
        resp = _requests.get(url, headers=headers, params=params, timeout=12)
    except Exception as exc:
        return f"[network error] {exc}"

    if resp.status_code == 403:
        return "[error] GitHub rate limit hit. Set GITHUB_TOKEN env var to increase limit."
    if resp.status_code == 422:
        return f"[error] Invalid query: {query}"
    if not resp.ok:
        return f"[error] GitHub API returned {resp.status_code}: {resp.text[:200]}"

    try:
        data = resp.json()
    except Exception:
        return "[error] Could not parse GitHub API response"

    items = data.get("items", [])
    total = data.get("total_count", 0)

    if not items:
        return f"No GitHub results found for: {query}"

    lines: list[str] = [
        f"GitHub search: '{query}'  ({total:,} total results, showing top {len(items)})\n"
    ]

    if kind == "repositories":
        for i, item in enumerate(items, 1):
            name = item.get("full_name", "?")
            raw_desc = item.get("description") or ""
            # Clamp description — some repos put entire READMEs in this field
            desc = (
                (raw_desc[:200] + "…") if len(raw_desc) > 200 else (raw_desc or "(no description)")
            )
            url_ = item.get("html_url", "")
            stars = item.get("stargazers_count", 0)
            lang = item.get("language") or "?"
            updated = (item.get("updated_at") or "")[:10]
            topics = item.get("topics", [])
            topic_str = ("  |  Topics: " + ", ".join(topics[:5])) if topics else ""
            lines.append(
                f"{i}. [{name}]({url_})\n"
                f"   {desc}\n"
                f"   ★ {stars:,}  |  Language: {lang}  |  Updated: {updated}{topic_str}"
            )
    else:  # code
        for i, item in enumerate(items, 1):
            repo_name = item.get("repository", {}).get("full_name", "?")
            file_path = item.get("path", "?")
            file_url = item.get("html_url", "")
            lines.append(f"{i}. {file_path}\n" f"   Repo: {repo_name}\n" f"   {file_url}")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "github_search",
        github_search,
        description=(
            "Search GitHub for repositories or code files. "
            "Use for finding open-source projects, example scripts, or code snippets on GitHub. "
            "Set kind='repositories' (default) to find projects, kind='code' to find individual files. "
            "Supports GitHub search qualifiers: language:python, stars:>100, etc."
        ),
        category="web",
        args=[
            {
                "name": "query",
                "required": True,
                "description": "Search terms. GitHub qualifiers like 'language:python' are supported.",
            },
            {
                "name": "kind",
                "required": False,
                "description": "'repositories' (default) or 'code'.",
            },
            {
                "name": "max_results",
                "required": False,
                "description": "Number of results to return (1-10, default 8).",
            },
        ],
    )
