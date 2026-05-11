"""Project Iceberg CLI entry point."""

import signal
import sys
import threading
from typing import Callable

from agents.orchestrator_agent import OrchestratorAgent
from automation.engine import AutomationEngine
from automation.scheduler import Scheduler
from automation.storage import load_workflows
from tools.registry import describe_all

BANNER = r"""
   _   ___    _             _     _              _
  /_\ |_ _|  /_\   ___ ___ (_)___| |_ __ _ _ __ | |_
 //_\\ | |  //_\\ / __/ __|| / __| __/ _` | '_ \| __|
/  _  \| | /  _  \\__ \__ \| \__ \ || (_| | | | | |_
\_/ \_/___|\_/ \_/|___/___/|_|___/\__\__,_|_| |_|\__|
"""

HELP = """
Just talk to it. Ask questions, give instructions, or chat.

Special commands:
  help         Show this help
  tools        List registered tools
  status       Show which LLM backend is active
  memory       View and clean up long-term memory
  reset        Clear conversation history
  exit | quit  Exit
"""


# --- Command handlers --------------------------------------------------


def _cmd_help(_agent: OrchestratorAgent) -> bool:
    print(HELP)
    return True


def _cmd_tools(_agent: OrchestratorAgent) -> bool:
    print(describe_all())
    return True


def _cmd_status(agent: OrchestratorAgent) -> bool:
    print(f"LLM: {agent.llm_info()}")
    print(f"MCP servers: {agent.mcp_info()}")
    print(f"History: {agent.history_depth()} turn(s)")
    return True


def _cmd_reset(agent: OrchestratorAgent) -> bool:
    agent.reset_history()
    print("Conversation history cleared.")
    return True


def _cmd_exit(_agent: OrchestratorAgent) -> bool:
    return False  # signals "stop the loop"


def _cmd_memory(agent: OrchestratorAgent) -> bool:
    count = len(agent.long_memory.data)
    print(f"Long-term memory: {count} entries")
    print(f"Short-term memory: {len(agent.short_memory)} entries")
    if count > 0:
        try:
            choice = input("  Deduplicate memory? [y/N] ").strip().lower()
            if choice in {"y", "yes"}:
                removed = agent.long_memory.deduplicate()
                print(f"  Removed {removed} duplicate(s). Now {len(agent.long_memory.data)} entries.")
        except (EOFError, KeyboardInterrupt):
            print()
    return True


# Dispatch table (coding-standards: replaces if/elif chains with lookup).
# Value is a callable that takes the agent and returns whether to continue.
COMMANDS: dict[str, Callable[[OrchestratorAgent], bool]] = {
    "help": _cmd_help,
    "tools": _cmd_tools,
    "status": _cmd_status,
    "reset": _cmd_reset,
    "memory": _cmd_memory,
    "exit": _cmd_exit,
    "quit": _cmd_exit,
}


def run_cli(agent: OrchestratorAgent) -> None:
    print(BANNER)
    if agent.llm_active:
        print(f"LLM: {agent.llm_info()}")
    else:
        print("LLM: none (regex-only mode). Start LM Studio, Ollama, or set ANTHROPIC_API_KEY.")
    print("Type 'help' for commands. Ctrl+C or 'exit' to quit.\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        lower = user_input.lower()
        if lower in COMMANDS:
            if not COMMANDS[lower](agent):
                break
            continue

        try:
            results = agent.run(user_input)
            for r in results:
                print(r)
        except Exception as e:
            print(f"[error] {e}")


def _install_signal_handlers(scheduler: Scheduler, agent: OrchestratorAgent) -> None:
    def _handler(_signum, _frame):
        print("\n[shutdown] stopping...")
        scheduler.stop()
        agent.shutdown()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, AttributeError):
        pass


def main() -> None:
    interactive = sys.stdin.isatty()
    agent = OrchestratorAgent(interactive=interactive)

    workflows = load_workflows()
    engine = AutomationEngine(agent, workflows)
    scheduler = Scheduler(engine)

    _install_signal_handlers(scheduler, agent)

    if workflows:
        threading.Thread(target=scheduler.start, daemon=True).start()
        agent.logger.info(f"[scheduler] running {len(workflows)} workflow(s)")

    mode = "cli"
    if interactive:
        try:
            choice = input("Mode (cli/voice) [cli]: ").strip().lower()
            if choice == "voice":
                mode = "voice"
        except (EOFError, KeyboardInterrupt):
            print()
            return

    if mode == "voice":
        # Lazy import keeps CLI mode working when voice deps aren't installed.
        from voice.voice_mode import run_voice_mode  # noqa: PLC0415

        run_voice_mode(agent)
    else:
        run_cli(agent)

    scheduler.stop()
    agent.shutdown()


if __name__ == "__main__":
    main()
