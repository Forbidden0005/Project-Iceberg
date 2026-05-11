"""Runs workflows when their conditions match."""

from typing import Any

from automation.condition import evaluate


class AutomationEngine:
    def __init__(self, agent: Any, workflows: list[dict[str, Any]]):
        self.agent = agent
        self.workflows = workflows

    def tick(self) -> None:
        """Check every workflow once. Called by the Scheduler."""
        for wf in self.workflows:
            try:
                self._tick_one(wf)
            except Exception as e:
                print(f"[workflow error] {wf.get('name', '?')}: {e}")

    def _tick_one(self, wf: dict[str, Any]) -> None:
        if not evaluate(wf.get("condition", "always")):
            return

        for action in wf.get("actions", []):
            # Actions are natural-language strings fed back through the agent
            self.agent.run(action)
