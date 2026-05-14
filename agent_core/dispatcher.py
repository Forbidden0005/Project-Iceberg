"""
Intent dispatcher.

Given raw user input + conversation history, decide whether this is:
  - chat:   answer conversationally from the LLM
  - tools:  execute one or more tools and report results
  - mixed:  execute tools AND have the LLM narrate / interpret the results

Classification strategy (fastest to slowest):
  1. _fast_classify() -- pure heuristics, zero latency.  Only fires on inputs
     that are unambiguously one class.  Returns None when uncertain so the LLM
     gets to decide.  Better to fall through than to guess wrong.
  2. LLM classifier  -- structured JSON response, mode + reasoning.
     Only runs if fast-classify returned None AND an LLM is available.
  3. _heuristic()    -- action-verb regex fallback when LLM is unavailable or
     returns unparseable output.
"""

import json
import re
from typing import Any, Optional

from agent_core.constants import (HISTORY_WINDOW_FOR_PLANNING,
                                  LLM_CLASSIFY_MAX_TOKENS,
                                  LLM_PLAN_TEMPERATURE)

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

# First word implies a tool call.  Only used in fast-path Rule 2.
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
    "delete",
    "remove",
    "move",
    "rename",
    "read",
    "open",
    "show",
    "search",
    "google",
    "find",
    "sysinfo",
}

# Standalone greetings / acknowledgements -- almost always pure chat.
# "new" removed: can mean "create a new file".
# "yes/no" removed: context-dependent ("yes do it" is a tool followup).
_PURE_CHAT_WORDS = {
    "hi",
    "hey",
    "hello",
    "howdy",
    "sup",
    "yo",
    "greetings",
    "thanks",
    "thank",
    "ok",
    "okay",
    "cool",
    "nice",
    "great",
    "perfect",
    "alright",
    "sure",
}

# Starting with one of these, with no action verb anywhere, is almost always chat.
# "do/does/did" deliberately excluded -- "do something" is an action.
_QUESTION_STARTERS = {
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
    "is",
    "are",
    "was",
    "were",
    "could",
    "should",
    "would",
    "will",
    "explain",
    "describe",
    "tell",
    "define",
}

# Words that signal a secondary natural-language clause ("and tell me", "and
# summarize") -- their presence next to an action verb suggests mixed mode.
_NARRATION_WORDS = {"tell", "summarize", "summarise", "describe", "explain", "show", "report"}


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
    # Public entry point
    # ------------------------------------------------------------------

    def classify(self, user_input: str, history: list[dict[str, str]] = None) -> dict[str, Any]:
        """Return {"mode": "chat|tools|mixed", "reasoning": str}.

        Tries the zero-cost fast path first; only invokes the LLM when the
        intent is genuinely ambiguous.
        """
        history = history or []

        # Fast path -- zero LLM calls for high-confidence cases
        fast = self._fast_classify(user_input)
        if fast is not None:
            return fast

        # No LLM available -- fall back to regex heuristic
        if self.llm is None:
            return self._heuristic(user_input)

        # Full LLM classification for ambiguous inputs
        system = self._CLASSIFIER_PROMPT.format(tools=self.tools_description)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
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
    # Fast heuristic path (no LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _fast_classify(user_input: str) -> Optional[dict[str, Any]]:
        """Return a confident classification without touching the LLM.

        Conservative by design: returns None (fall through to LLM) whenever
        there is any doubt.  A wrong fast-path answer is worse than a slow
        correct one.

        Rules (checked in order):
          R1. Input is a pure greeting / social word (1-2 tokens, no action verb)
              -> chat
          R2. Input starts with an action verb AND has no 'and <narration>' clause
              -> tools
          R3. Input starts with a question word AND has no action verb anywhere
              -> chat
          R4. Very short input (<=2 words), no action verb, no question needed
              -> chat
          R5. Anything else -> None (LLM decides)
        """
        stripped = user_input.strip()
        if not stripped:
            return {"mode": "chat", "reasoning": "fast: empty input"}

        words = re.findall(r"[a-z']+", stripped.lower())
        if not words:
            return {"mode": "chat", "reasoning": "fast: no words"}

        word_set = set(words)
        first_word = words[0]
        has_action = bool(word_set & _ACTION_VERBS)

        # R1: pure greeting -- only when input is very short and has no action verb
        if first_word in _PURE_CHAT_WORDS and len(words) <= 4 and not has_action:
            return {"mode": "chat", "reasoning": "fast: greeting/social"}

        # R2: leading action verb, but only if the intent is unambiguously tools
        # Skip if "and" connects to a narration word (potential mixed mode).
        if first_word in _ACTION_VERBS:
            has_and_narration = "and" in word_set and bool(word_set & _NARRATION_WORDS)
            if not has_and_narration:
                return {
                    "mode": "tools",
                    "reasoning": "fast: leading action verb '" + first_word + "'",
                }
            # "scan X and tell me Y" -- ambiguous, let LLM decide
            return None

        # R3: clear question starter with no action verb
        if first_word in _QUESTION_STARTERS and not has_action:
            return {"mode": "chat", "reasoning": "fast: question with no action verb"}

        # Ambiguous -- let the LLM decide
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(raw: str) -> Optional[dict[str, Any]]:
        if not raw:
            return None
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            raw = m.group(0)
        try:
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    def _heuristic(user_input: str) -> dict[str, Any]:
        """Last-resort fallback: action-verb regex, no LLM required."""
        words = set(re.findall(r"[a-z]+", user_input.lower()))
        if words & _ACTION_VERBS:
            return {"mode": "tools", "reasoning": "heuristic: action verb present"}
        return {"mode": "chat", "reasoning": "heuristic: no action verb"}
