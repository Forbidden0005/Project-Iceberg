"""
Typed contracts for tool execution.

Replaces the loose dict-based plan format with proper dataclasses so the
planner, executor, and agents speak the same language. Matches the
ai-first-engineering principle of stable typed contracts at module boundaries.

Backwards-compatible helpers let existing tests that construct plans as raw
dicts keep working - the executor and sub-agents accept either form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A single planned tool invocation."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": dict(self.args)}

    @classmethod
    def from_any(cls, obj: Any) -> ToolCall | None:
        """Accept a ToolCall, a dict, or None; return a ToolCall or None."""
        if isinstance(obj, ToolCall):
            return obj
        if isinstance(obj, dict):
            name = obj.get("tool")
            if not isinstance(name, str) or not name:
                return None
            args = obj.get("args") or {}
            if not isinstance(args, dict):
                return None
            return cls(tool=name, args=args)
        return None


@dataclass
class ToolResult:
    """The outcome of running a single tool call.

    Tools historically returned strings for both success and error cases, which
    mixed two channels. ToolResult separates them: `ok` says whether the call
    succeeded, `output` is the display value. Existing code that just prints
    the result still works because __str__ delegates to output.
    """

    tool: str
    ok: bool
    output: str
    error: str | None = None

    def __str__(self) -> str:
        return self.output

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "ok": self.ok, "output": self.output, "error": self.error}

    @classmethod
    def success(cls, tool: str, output: str) -> ToolResult:
        return cls(tool=tool, ok=True, output=output)

    @classmethod
    def failure(cls, tool: str, message: str) -> ToolResult:
        return cls(tool=tool, ok=False, output=message, error=message)
