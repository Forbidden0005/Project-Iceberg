"""
engine.py — ReflectionEngine: the core self-improvement loop.

After each completed turn the orchestrator calls reflect(). The engine
evaluates what happened and, if something is worth learning, writes a Lesson
to the LessonStore.

Strategy:
  1. LLM-first: ask the active LLM to write a lesson. The prompt is tight
     and structured so the output is easy to parse.
  2. Rule-based fallback: if no LLM is available (or the LLM call fails),
     apply a small set of deterministic rules that catch the most common
     failure patterns.
  3. Always reflect on failures; reflect on successes only when the LLM
     identifies something non-obvious.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from typing import Optional

from reflection.lesson import Lesson, LessonCategory
from reflection.store import LessonStore

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Input contract
# ------------------------------------------------------------------


@dataclass
class TurnContext:
    """Everything the engine needs to evaluate a completed turn.

    Attributes:
        user_request:  The raw user message.
        intent:        Dispatcher classification: "chat" | "tools" | "mixed".
        plan:          List of planned tool calls (may be empty for chat turns).
        results:       List of ToolResult-like dicts with at least {"tool", "success", "output"}.
        final_response: The text the assistant sent back.
        success:       True if the turn completed without errors.
        error:         Error message if the turn failed, else None.
    """

    user_request: str
    intent: str = "chat"
    plan: list[dict] = None  # type: ignore[assignment]
    results: list[dict] = None  # type: ignore[assignment]
    final_response: str = ""
    success: bool = True
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.plan is None:
            self.plan = []
        if self.results is None:
            self.results = []


# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------


class ReflectionEngine:
    """Evaluates completed turns and extracts reusable lessons.

    Usage::

        engine = ReflectionEngine(store, provider)

        # Called by the orchestrator after each turn — runs in a background thread.
        engine.reflect_async(ctx)

        # Or synchronously (blocks until done):
        lesson = engine.reflect(ctx)
    """

    # LLM prompt template — kept short to avoid token waste on local models.
    _PROMPT = """\
You are an AI assistant evaluating your own recent action to extract one reusable lesson.

USER REQUEST: {request}
INTENT: {intent}
TOOLS USED: {tools}
OUTCOME: {outcome}
{error_block}
RESPONSE SUMMARY: {response_summary}

If there is ONE specific, concrete, actionable lesson worth remembering for similar future requests, respond with valid JSON only — no other text:
{{
  "text": "When <situation>, do <action> because <reason>.",
  "trigger": "short phrase describing when to apply this (10 words max)",
  "category": "planning|tool_use|error|user_preference",
  "confidence": <float 0.0-1.0>
}}

If nothing notable to learn, respond with exactly: null

Rules for a good lesson:
- Must be specific to this kind of request, not generic advice
- Must be actionable (tells the planner what to do differently)
- Confidence > 0.8 only for clear-cut patterns
- Do not repeat advice about being helpful or accurate (too generic)"""

    def __init__(
        self,
        store: LessonStore,
        provider=None,  # Optional[LLMProvider]
    ) -> None:
        self._store = store
        self._provider = provider

    def set_provider(self, provider) -> None:
        """Hot-swap the LLM provider (called when orchestrator switches backends)."""
        self._provider = provider

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def reflect_async(self, ctx: TurnContext) -> None:
        """Fire-and-forget: run reflect() in a daemon thread."""
        t = threading.Thread(target=self._safe_reflect, args=(ctx,), daemon=True)
        t.start()

    def reflect(self, ctx: TurnContext) -> Optional[Lesson]:
        """Synchronous reflection — returns the lesson if one was created, else None."""
        return self._safe_reflect(ctx)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _safe_reflect(self, ctx: TurnContext) -> Optional[Lesson]:
        """Wrapper that ensures reflection never crashes the calling thread."""
        try:
            return self._reflect(ctx)
        except Exception as exc:
            logger.debug("[reflection] unexpected error: %s", exc)
            return None

    def _reflect(self, ctx: TurnContext) -> Optional[Lesson]:
        # Chat-only turns with no tools and no error rarely yield useful lessons.
        if ctx.intent == "chat" and not ctx.plan and ctx.success:
            return None

        lesson = self._llm_reflect(ctx) if self._provider else None

        if lesson is None:
            lesson = self._rule_reflect(ctx)

        if lesson is not None:
            self._store.add(lesson)

        return lesson

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _llm_reflect(self, ctx: TurnContext) -> Optional[Lesson]:
        """Ask the active LLM to extract a lesson. Returns None on any failure."""
        try:
            prompt = self._build_prompt(ctx)
            messages = [{"role": "user", "content": prompt}]
            raw = self._provider.chat(messages, max_tokens=256, temperature=0.2)
            return self._parse_llm_response(raw)
        except Exception as exc:
            logger.debug("[reflection] LLM reflection failed (%s), using rules", exc)
            return self._rule_reflect(ctx)

    def _build_prompt(self, ctx: TurnContext) -> str:
        tools_summary = ", ".join(r.get("tool", "?") for r in ctx.results) or "none"
        outcome = "SUCCESS" if ctx.success else "FAILURE"
        error_block = f"ERROR: {ctx.error}\n" if ctx.error else ""
        response_summary = (ctx.final_response[:200] + "...") if len(ctx.final_response) > 200 else ctx.final_response
        return self._PROMPT.format(
            request=ctx.user_request[:300],
            intent=ctx.intent,
            tools=tools_summary,
            outcome=outcome,
            error_block=error_block,
            response_summary=response_summary or "(none)",
        )

    def _parse_llm_response(self, raw: str) -> Optional[Lesson]:
        raw = raw.strip()
        if raw.lower() == "null" or not raw:
            return None

        # Strip markdown fences if present.
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract the first JSON object.
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return None
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return None

        if not isinstance(data, dict):
            return None

        text = data.get("text", "").strip()
        trigger = data.get("trigger", "").strip()
        if not text or not trigger:
            return None

        category = data.get("category", "planning")
        if category not in ("planning", "tool_use", "error", "user_preference"):
            category = "planning"

        confidence = float(data.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))

        # Reject obviously generic lessons.
        generic_phrases = ["be helpful", "be accurate", "always respond", "make sure to"]
        if any(phrase in text.lower() for phrase in generic_phrases):
            return None

        return Lesson(
            text=text,
            trigger=trigger,
            category=category,
            confidence=confidence,
            source="llm",
        )

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _rule_reflect(self, ctx: TurnContext) -> Optional[Lesson]:
        """Generate a lesson from deterministic rules when no LLM is available."""

        # Rule 1: A tool failed.
        failed_tools = [r for r in ctx.results if not r.get("success", True)]
        if failed_tools:
            tool_name = failed_tools[0].get("tool", "unknown_tool")
            error_hint = str(failed_tools[0].get("output", ""))[:120]
            return Lesson(
                text=(
                    f"The tool '{tool_name}' failed during this type of request. "
                    f"Verify preconditions before calling it, or try an alternative. "
                    f"Error hint: {error_hint}"
                ),
                trigger=f"using {tool_name} for {ctx.intent} request",
                category="error",
                confidence=0.6,
                source="rule",
            )

        # Rule 2: Multiple tools were chained — the sequence might be useful.
        if len(ctx.results) >= 3 and ctx.success:
            tool_chain = " → ".join(r.get("tool", "?") for r in ctx.results[:5])
            return Lesson(
                text=(
                    f"For requests like '{ctx.user_request[:80]}', "
                    f"this tool sequence worked well: {tool_chain}."
                ),
                trigger=ctx.user_request[:80],
                category="planning",
                confidence=0.5,
                source="rule",
            )

        # Rule 3: The overall turn failed with no tool results (plan failed).
        if not ctx.success and not ctx.results and ctx.error:
            return Lesson(
                text=(
                    f"Planning failed for a '{ctx.intent}' request with this error: "
                    f"{ctx.error[:150]}. Check if the planner prompt covers this case."
                ),
                trigger=f"planning failure for {ctx.intent} intent",
                category="planning",
                confidence=0.55,
                source="rule",
            )

        # Nothing rule-worthy.
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _category(raw: str) -> LessonCategory:
        valid = {"planning", "tool_use", "error", "user_preference"}
        return raw if raw in valid else "planning"  # type: ignore[return-value]
