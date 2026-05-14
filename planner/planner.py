"""
Planner - turns a user utterance into a list of tool-call steps.

Strategy:
  1. If an LLM is configured, use it to plan. Tools are described dynamically
     from the live registry (plugins show up automatically).
  2. Otherwise fall back to regex parsing.

Each step: {"tool": str, "args": dict}
"""

import json
import re
from typing import Any, Optional

from agent_core.constants import (HISTORY_WINDOW_FOR_PLANNING,
                                  LLM_PLAN_MAX_TOKENS, LLM_PLAN_TEMPERATURE)


class Planner:
    def __init__(self, llm=None, tools_description: str = ""):
        """
        llm: agent_core.llm.LLMProvider or None
        tools_description: pre-rendered tool list for the prompt
        """
        self.llm = llm
        self.tools_description = tools_description or "(none available)"

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def create_plan(
        self,
        text: str,
        history: list[dict[str, str]] = None,
    ) -> Optional[list[dict[str, Any]]]:
        text = (text or "").strip()
        if not text:
            return None

        if self.llm is not None:
            # LLM output is authoritative.  If it returns [] or garbage, honour
            # that refusal — never silently fall back to regex, which would let
            # the planner invent actions the LLM explicitly declined to take.
            return self._llm_plan(text, history or [])

        return self._regex_plan(text)

    # ------------------------------------------------------------------
    # LLM planner
    # ------------------------------------------------------------------

    _SYSTEM_TEMPLATE = """You are the planning component of a local AI assistant.
Translate the user's latest message into a JSON array of tool calls.

Available tools:
{tools}

Rules:
- Respond with ONLY a JSON array. No prose, no markdown fences.
- Each element MUST have the shape: {{"tool": "<n>", "args": {{...}}}}
- Use only the tool names listed above. Do not invent tools.
- If the user's request cannot be achieved with these tools, return [].
- Prefer the minimum number of steps that accomplish the goal.
- For file paths, preserve the user's exact spelling and case.
- You CAN scrape websites when scrape_paginated is available. Use it freely.

Examples:
  User: list my downloads folder
  -> [{{"tool":"list_dir","args":{{"path":"~/Downloads"}}}}]

  User: make a note called todo.txt
  -> [{{"tool":"create_file","args":{{"path":"todo.txt"}}}}]

  User: scrape https://example.com pages 1-3
  -> [{{"tool":"scrape_paginated","args":{{"url":"https://example.com","selector":"a","max_pages":3}}}}]

  User: what's the weather
  -> []
"""

    def _llm_plan(self, text: str, history: list[dict[str, str]]) -> Optional[list[dict[str, Any]]]:
        system = self._SYSTEM_TEMPLATE.format(tools=self.tools_description)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        messages.extend(
            history[-HISTORY_WINDOW_FOR_PLANNING:]
        )  # short context window for references like "yes do it"
        messages.append({"role": "user", "content": text})

        try:
            raw = self.llm.chat(
                messages,
                max_tokens=LLM_PLAN_MAX_TOKENS,
                temperature=LLM_PLAN_TEMPERATURE,
            )
        except Exception:
            return None

        return self._parse_plan(raw)

    @staticmethod
    def _parse_plan(raw: str) -> Optional[list[dict[str, Any]]]:
        if not raw:
            return None
        s = raw.strip()
        # Strip markdown fences
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)

        # Find the first JSON array in the response (handles chatty models)
        m = re.search(r"\[.*\]", s, re.S)
        if m:
            s = m.group(0)

        try:
            data = json.loads(s)
        except Exception:
            return None

        if not isinstance(data, list):
            return None

        cleaned: list[dict[str, Any]] = []
        for step in data:
            if not isinstance(step, dict):
                continue
            name = step.get("tool")
            if not name or not isinstance(name, str):
                continue
            args = step.get("args", {}) or {}
            if not isinstance(args, dict):
                continue
            cleaned.append({"tool": name, "args": args})
        return cleaned or None

    # ------------------------------------------------------------------
    # Regex fallback (used when no LLM or LLM fails)
    # ------------------------------------------------------------------

    def _regex_plan(self, text: str) -> Optional[list[dict[str, Any]]]:
        lower = text.lower()
        steps: list[dict[str, Any]] = []

        m = re.search(r"create (?:a )?file (?:called |named )?(\S+)", lower)
        if m:
            steps.append({"tool": "create_file", "args": {"path": m.group(1)}})

        m = re.search(r"delete (?:the )?file (\S+)", lower)
        if m:
            steps.append({"tool": "delete_file", "args": {"path": m.group(1)}})

        m = re.search(r"move (\S+) (?:to|->) (\S+)", lower)
        if m:
            steps.append({"tool": "move_file", "args": {"src": m.group(1), "dst": m.group(2)}})

        m = re.search(r"read (?:the )?(?:file )?(\S+\.[a-z0-9]+)", lower)
        if m:
            steps.append({"tool": "read_file", "args": {"path": m.group(1)}})

        m = re.search(r"append (.+?) (?:to )(\S+)", lower)
        if m:
            steps.append(
                {"tool": "append_file", "args": {"path": m.group(2), "content": m.group(1)}}
            )

        m = re.search(r"scan(?:\s+(\S+))?(?:\s+(low|medium|high))?", lower)
        if m and "scan" in lower:
            p = m.group(1) if m.group(1) and m.group(1) not in {"low", "medium", "high"} else "."
            mode = (m.group(2) or "LOW").upper()
            steps.append({"tool": "scan", "args": {"path": p, "mode": mode}})

        if re.search(r"\blist\b", lower) and not steps:
            m = re.search(r"list (?:the )?(?:directory |dir |folder )?(\S+)", lower)
            p = m.group(1) if m else "."
            steps.append({"tool": "list_dir", "args": {"path": p}})

        # GitHub-specific search: "search github for X" / "find on github X"
        m_gh = re.search(
            r"(?:search|find|look up|look for)\s+(?:on\s+)?github\s+(?:for\s+)?(.+)", lower
        )
        if m_gh:
            q = m_gh.group(1).strip(" ?.!")
            # Detect if the user wants code files vs. repositories
            kind = "code" if re.search(r"\b(script|file|code|snippet)s?\b", q) else "repositories"
            steps.append({"tool": "github_search", "args": {"query": q, "kind": kind}})
        elif not steps:
            m = re.search(r"(?:search|google|look up)(?:\s+for)?\s+(.+)", lower)
            if m:
                q = m.group(1).strip(" ?.!")
                steps.append({"tool": "web_search", "args": {"query": q}})

        # Scrape pattern: scrape URL [selector "CSS"] [pages X-Y]
        # Supports: scrape URL pages 1-3 selector "a.link"
        #           scrape URL selector "a.link" pages 1-3
        #           scrape URL selector "a.link"
        #           scrape URL pages 1-3
        m = re.search(r"scrape\s+(https?://\S+)(?:\s+(.+))?", lower)
        if m:
            url = m.group(1)
            rest = m.group(2) or ""

            # Extract selector if present
            selector = "a"  # default
            selector_match = re.search(r'selector\s+["\']([^"\']+)["\']', rest)
            if selector_match:
                selector = selector_match.group(1)
                rest = re.sub(r'selector\s+["\'][^"\']+["\']', "", rest).strip()

            # Extract pages if present
            max_pages = 10  # default
            pages_match = re.search(r"pages?\s+(\d+)(?:-(\d+))?", rest)
            if pages_match:
                if pages_match.group(2):  # range like "1-4"
                    max_pages = int(pages_match.group(2))
                else:  # single page like "page 5"
                    max_pages = int(pages_match.group(1))

            steps.append(
                {
                    "tool": "scrape_paginated",
                    "args": {"url": url, "selector": selector, "max_pages": max_pages},
                }
            )

        if re.search(r"\b(sysinfo|system info|system information)\b", lower):
            steps.append({"tool": "sysinfo", "args": {}})

        return steps or None
