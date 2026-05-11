"""Handles system-level and web tool calls."""

from agent_core.contracts import ToolCall, ToolResult
from tools.registry import get_tool


class SystemAgent:
    category = "system"

    def __init__(self, logger):
        self.logger = logger

    def handle(self, step: ToolCall | dict) -> ToolResult:
        """Execute a system/web tool call.

        Accepts either a ToolCall or a legacy dict for backwards compatibility.
        Always returns a ToolResult.
        """
        call = ToolCall.from_any(step) if not isinstance(step, ToolCall) else step
        if call is None:
            return ToolResult.failure("?", f"Malformed step: {step!r}")

        func = get_tool(call.tool)
        if not func:
            return ToolResult.failure(call.tool, f"Tool not found: {call.tool}")

        self.logger.debug(f"[SystemAgent] {call.tool}({call.args})")
        try:
            output = func(**call.args)
            return ToolResult.success(call.tool, str(output))
        except TypeError as e:
            return ToolResult.failure(call.tool, f"Bad arguments for {call.tool}: {e}")
        except Exception as e:
            self.logger.error(f"[SystemAgent error] {call.tool}: {e}")
            return ToolResult.failure(call.tool, f"Error in {call.tool}: {e}")
