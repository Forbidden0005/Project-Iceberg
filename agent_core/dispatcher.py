"""
Intent dispatcher.

Given raw user input + conversation history, decide whether this is:
  - chat:   answer conversationally from the LLM
  - tools:  execute one or more tools and report results
  - mixed:  execute tools AND have the LLM narrate / interpret the results

The classifier is the LLM itself, asked to return a small JSON object.
If the LLM is unavailable or produces garbage, we fall back heuristically.
"""

import json
import re
from typing import Any, Optional

from agent_core.constants import HISTORY_WINDOW_FOR_PLANNING, LLM_CLASSIFY_MAX_TOKENS, LLM_PLAN_TEMPERATURE

# Keywords that heuristically suggest a tool action. Used when we have no LLM
# or when LLM output is unparseable.
_ACTION_VERBS = {
    "list",
    "ls",
    "dir",
    "scan",
    "scrape",
    "extract",
    "crawl",
    "create",
    "make",
    "new",
    "delete",
    "remove",
    "move",
    "rename",
    "read",
    "open",
    "show",
    "search",
    "google",
    "look up",
    "find",
    "sysinfo",
}


class Dispatcher:
    _CLASSIFIER_PROMPT = """You classify user requests for a local AI assistant.

You will be given the user's latest message and optional conversation history.
Decide whether the message requires running tools on the user's machine, or
just a conversational reply.

Available tools:
{tools}

Respond with ONLY a JSON object, no prose, no markdown fences:
  {{"mode": "chat" | "tools" | "mixed", "reasoning": "<one short sentence>"}}

- "chat":   user is asking a question, chatting, or wants explanation only
- "tools":  user wants the assistant to DO something concrete on the system
- "mixed":  user wants both (e.g. "list my desktop and tell me what looks old")

Examples:
  "hey how are you"                       -> {{"mode":"chat","reasoning":"greeting"}}
  "explain recursion"                     -> {{"mode":"chat","reasoning":"explanation"}}
  "list the current directory"            -> {{"mode":"tools","reasoning":"directory listing"}}
  "what's in my downloads folder?"        -> {{"mode":"tools","reasoning":"directory listing"}}
  "scan my desktop and summarize it"      -> {{"mode":"mixed","reasoning":"scan then explain"}}
"""

    def __init__(self, llm, tools_description: str = ""):
        self.llm = llm
        self.tools_description = tools_description or "(none)"

    # ------------------------------------------------------------------

    def classify(self, user_input: str, history: list[dict[str, str]] = None) -> dict[str, Any]:
        """Return {"mode": "chat|tools|mixed", "reasoning": str}."""
        history = history or []

        if self.llm is None:
            return self._heuristic(user_input)

        system = self._CLASSIFIER_PROMPT.format(tools=self.tools_description)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        # Include a small tail of conversation history for context
        messages.extend(history[-HISTORY_WINDOW_FOR_PLANNING:])
        messages.append({"role": "user", "content": user_input})

        try:
            raw = self.llm.chat(
                messages,
                max_tokens=LLM_CLASSIFY_MAX_TOKENS,
                temperature=LLM_PLAN_TEMPERATURE,
            )
        except Exception:
            return self._heuristic(user_input)

        parsed = self._extract_json(raw)
        if not parsed or "mode" not in parsed:
            return self._heuristic(user_input)

        mode = parsed.get("mode", "chat").lower()
        if mode not in {"chat", "tools", "mixed"}:
            mode = "chat"
        return {"mode": mode, "reasoning": parsed.get("reasoning", "")}

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(raw: str) -> Optional[dict[str, Any]]:
        if not raw:
            return None
        raw = raw.strip()
        # Strip fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        # If model added leading prose, grab the first {...}
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            raw = m.group(0)
        try:
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    def _heuristic(user_input: str) -> dict[str, Any]:
        words = set(re.findall(r"[a-z]+", user_input.lower()))
        if words & _ACTION_VERBS:
            return {"mode": "tools", "reasoning": "heuristic: action verb present"}
        return {"mode": "chat", "reasoning": "heuristic: no action verb"}
