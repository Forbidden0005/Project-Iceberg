"""
Orchestrator - top-level agent.

Flow per user turn:
  1. Dispatcher classifies intent: chat | tools | mixed
  2. Route:
       chat   -> LLM answers conversationally
       tools  -> Planner builds steps; Executor runs them
       mixed  -> Plan + execute, then LLM narrates the results
  3. Update conversation history + long-term memory
"""

from typing import Any, Optional

from agent_core.constants import (CONVERSATION_HISTORY_LIMIT,
                                  LLM_CHAT_MAX_TOKENS, LLM_CHAT_TEMPERATURE,
                                  LLM_NARRATE_MAX_TOKENS, LLM_PLAN_TEMPERATURE)
from agent_core.dispatcher import Dispatcher
from agent_core.llm import get_provider
from agent_core.logger import Logger
from agents.file_agent import FileAgent
from agents.system_agent import SystemAgent
from executor.executor import Executor
from memory.long_memory import LongMemory
from memory.short_memory import ShortMemory
from planner.planner import Planner
from safety.manager import SafetyManager
from tools.registry import describe_for_llm

CHAT_SYSTEM_PROMPT = """You are a helpful local AI assistant running on the user's own machine.
You are friendly, concise, and direct. When the user just wants to chat or asks a
question, answer it naturally without any JSON or tool syntax. Keep replies short
unless the user asks for detail.

You have full memory of this conversation, including any tools you have already run.
Prior assistant messages may include tool execution results labelled as [Tool: name].
When the user asks a follow-up question about something that already happened (e.g.
"what did that scan find?" or "what files did you list?"), use those prior results as
your context and answer directly — do not say you lack information or need to run the
tool again."""

NARRATE_SYSTEM_PROMPT = """You are summarising the output of tool calls the assistant just
ran for the user. Be concise and speak in plain language. If something failed, say so
clearly. Do not invent information that isn't in the tool output."""


class OrchestratorAgent:
    def __init__(self, interactive: bool = True, history_limit: int = CONVERSATION_HISTORY_LIMIT):
        self.logger = Logger()
        self._history: list[dict[str, str]] = []
        self._history_limit = history_limit
        self.mcp_manager = None  # kept alive so the background loop + connections persist

        # MCP servers must load before _build_llm_stack so their tools appear
        # in describe_for_llm() and the planner/dispatcher know about them.
        self._load_mcp_servers()
        self._build_llm_stack()
        self._build_execution_stack(interactive=interactive)
        self._build_memory_stack()

    # ------------------------------------------------------------------
    # Dependency wiring (extracted from __init__ per coding-standards)
    # ------------------------------------------------------------------

    def _load_mcp_servers(self) -> None:
        """Connect to configured MCP servers and register their tools."""
        # Lazy import: keeps startup fast when mcp_servers is not configured.
        from tools.mcp_loader import (load_mcp_servers,  # noqa: PLC0415
                                      read_mcp_config)

        mcp_cfg = read_mcp_config()
        if not mcp_cfg:
            return

        self.mcp_manager = load_mcp_servers(mcp_cfg)
        count = len(self.mcp_manager.connected_servers) if self.mcp_manager else 0
        self.logger.info(f"[mcp] {count}/{len(mcp_cfg)} server(s) connected")

    def _build_llm_stack(self) -> None:
        """Probe providers and set up LLM-aware components."""
        self.llm = get_provider(logger=self.logger)
        self.llm_active = self.llm is not None

        tools_desc = describe_for_llm()
        self.planner = Planner(llm=self.llm, tools_description=tools_desc)
        self.dispatcher = Dispatcher(self.llm, tools_description=tools_desc)

    def _build_execution_stack(self, interactive: bool) -> None:
        """Build the tool-execution pipeline."""
        self.safety = SafetyManager(interactive=interactive)
        self.file_agent = FileAgent(self.logger)
        self.system_agent = SystemAgent(self.logger)
        self.executor = Executor(
            logger=self.logger,
            file_agent=self.file_agent,
            system_agent=self.system_agent,
            safety=self.safety,
        )

    def _build_memory_stack(self) -> None:
        """Short + long-term memory stores."""
        self.short_memory = ShortMemory()
        self.long_memory = LongMemory()

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _push(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        if len(self._history) > self._history_limit:
            # Keep the tail; we could summarise older turns later
            self._history = self._history[-self._history_limit :]

    def reset_history(self) -> None:
        self._history.clear()

    def history_depth(self) -> int:
        """How many turns are currently in the rolling conversation."""
        return len(self._history)

    def llm_info(self) -> str:
        """Human-readable description of the active LLM (or 'none')."""
        if not self.llm_active:
            return "none"
        return f"{self.llm.name} ({getattr(self.llm, 'model', 'unknown')})"

    def mcp_info(self) -> str:
        """Human-readable summary of connected MCP servers."""
        if not self.mcp_manager or not self.mcp_manager.connected_servers:
            return "none"
        return ", ".join(self.mcp_manager.connected_servers)

    def shutdown(self) -> None:
        """Graceful shutdown — close MCP connections and background loop."""
        if self.mcp_manager:
            self.mcp_manager.shutdown()
            self.mcp_manager = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, user_input: str) -> list[str]:
        user_input = (user_input or "").strip()
        if not user_input:
            return ["(empty input)"]

        self.logger.info(f"[input] {user_input}")

        # Long-term memory lookup (non-fatal)
        context = self.long_memory.search(user_input)
        if context:
            self.logger.debug(f"[memory] matched {len(context)} prior entries")

        # Decide how to handle this turn
        intent = self.dispatcher.classify(user_input, history=self._history)
        mode = intent["mode"]
        self.logger.debug(f"[intent] {mode} - {intent.get('reasoning','')}")

        if mode == "chat":
            output = [self._chat(user_input)]
        elif mode == "tools":
            output = self._run_tools(user_input, narrate=False)
        else:  # mixed
            output = self._run_tools(user_input, narrate=True)

        # For the UI: plain text output (ToolResult.__str__ = result.output)
        display = [str(r) for r in output]

        # For history: label each tool result so the LLM knows what ran.
        # Chat and narration results (plain str) pass through unchanged.
        def _history_line(r: Any) -> str:
            if hasattr(r, "tool") and r.tool:
                status = "" if r.ok else " [FAILED]"
                return f"[Tool: {r.tool}{status}]\n{r.output}"
            return str(r)

        history_content = "\n\n".join(_history_line(r) for r in output if str(r).strip())

        # Update histories
        self._push("user", user_input)
        self._push("assistant", history_content or "(no output)")
        self.short_memory.add({"input": user_input, "output": display, "mode": mode})
        self.long_memory.add(user_input)

        return display

    # ------------------------------------------------------------------
    # Modes
    # ------------------------------------------------------------------

    def _chat(self, user_input: str) -> str:
        if not self.llm_active:
            return (
                "Chat mode needs an LLM backend. Start LM Studio or Ollama, "
                "or set ANTHROPIC_API_KEY. Meanwhile I can still run tools."
            )
        try:
            messages: list[dict[str, str]] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
            messages.extend(self._history[-self._history_limit :])
            messages.append({"role": "user", "content": user_input})
            return self.llm.chat(
                messages,
                max_tokens=LLM_CHAT_MAX_TOKENS,
                temperature=LLM_CHAT_TEMPERATURE,
            )
        except Exception as e:
            self.logger.error(f"[chat error] {e}")
            return f"[chat error] {e}"

    def _run_tools(self, user_input: str, narrate: bool) -> list:
        plan = self.planner.create_plan(user_input, history=self._history)
        if not plan:
            # Even in tools mode, if we can't plan and we have an LLM, fall back to chat
            if self.llm_active:
                return [self._chat(user_input)]
            return ["No plan generated. Try: list, scan, create file X, read X, search X, sysinfo"]

        self.logger.debug(f"[plan] {plan}")
        results = self.executor.execute(plan)

        if narrate and self.llm_active:
            narration = self._narrate(user_input, results)
            if narration:
                results = results + ["", narration]

        return results  # ToolResult objects + optional narration str

    def _narrate(self, user_input: str, results: list[Any]) -> Optional[str]:
        try:
            summary_parts = []
            for result in results:
                if hasattr(result, "tool"):
                    summary_parts.append(f"- {result.tool}: {result.output}")
                else:
                    summary_parts.append(f"- {result}")
            tool_report = "\n".join(summary_parts)

            messages = [
                {"role": "system", "content": NARRATE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"User asked: {user_input}\n\nTool output:\n{tool_report}\n\nSummarise for the user.",
                },
            ]
            return self.llm.chat(
                messages,
                max_tokens=LLM_NARRATE_MAX_TOKENS,
                temperature=LLM_PLAN_TEMPERATURE + 0.3,
            )
        except Exception as e:
            self.logger.error(f"[narrate error] {e}")
            return None
