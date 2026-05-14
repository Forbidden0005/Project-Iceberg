"""Executes a planned list of steps with safety gating and agent routing."""

from agent_core.contracts import ToolCall, ToolResult
from safety.manager import SafetyManager
from tools.loader import load_plugins
from tools.registry import TOOL_REGISTRY, get_category


class Executor:
    def __init__(self, logger, file_agent, system_agent, safety: SafetyManager = None):
        self.logger = logger
        self.safety = safety or SafetyManager()
        self.file_agent = file_agent
        self.system_agent = system_agent

        n = load_plugins()
        if n:
            self.logger.info(f"[plugins] loaded {n}")

    def _route(self, tool_name: str):
        category = get_category(tool_name)
        if category == "file":
            return self.file_agent
        return self.system_agent

    def execute(self, steps):
        """Run each step. Accepts ToolCall objects or legacy dicts.

        Returns a list of ToolResult. ToolResult stringifies to its output, so
        existing callers that just print results still work unchanged.
        """
        results: list[ToolResult] = []

        for step in steps:
            call = ToolCall.from_any(step)
            if call is None:
                results.append(ToolResult.failure("?", f"Malformed step: {step!r}"))
                continue

            tool_name = call.tool

            if tool_name not in TOOL_REGISTRY:
                results.append(ToolResult.failure(tool_name, f"Tool not found: {tool_name}"))
                continue

            if not self.safety.check_permission(tool_name):
                self.logger.warning(f"[safety] denied: {tool_name}")
                results.append(ToolResult.failure(tool_name, f"Permission denied for: {tool_name}"))
                continue

            if self.safety.requires_confirmation(tool_name) and not self.safety.confirm(
                f"Run {tool_name}({call.args})?"
            ):
                results.append(ToolResult.failure(tool_name, f"Cancelled: {tool_name}"))
                continue

            agent = self._route(tool_name)
            self.logger.info(f"[exec] {tool_name}({call.args})")
            # Sub-agents now accept ToolCall and return ToolResult directly.
            result = agent.handle(call)
            if not isinstance(result, ToolResult):
                # Defensive: wrap unexpected return values
                result = ToolResult.success(tool_name, str(result))
            results.append(result)

        return results
