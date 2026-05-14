"""
SafetyManager - gates tool calls.

Rules live in safety/policy.json (auto-created with sane defaults).
- allowed:    tool is permitted
- requires_confirmation: ask user before running (destructive ops)
- denied:     refuse outright

When confirmation is required but running in non-interactive mode,
the call is denied by default (fail-closed).
"""

import json
import os
import sys

DEFAULT_POLICY = {
    # tool_name -> one of: allow | confirm | deny
    "list_dir": "allow",
    "scan": "allow",
    "read_file": "allow",
    "web_search": "allow",
    "sysinfo": "allow",
    "create_file": "confirm",
    "append_file": "confirm",
    "delete_file": "confirm",
    "move_file": "confirm",
    "run_shell": "deny",
}


class SafetyManager:
    def __init__(self, policy_path: str = "safety/policy.json", interactive: bool = True):
        self.policy_path = policy_path
        self.interactive = interactive
        self.policy = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.policy_path):
            os.makedirs(os.path.dirname(self.policy_path), exist_ok=True)
            with open(self.policy_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_POLICY, f, indent=2)
            return dict(DEFAULT_POLICY)

        try:
            with open(self.policy_path, encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge defaults for any missing keys
            merged = dict(DEFAULT_POLICY)
            merged.update(loaded)
            return merged
        except Exception:
            return dict(DEFAULT_POLICY)

    def _rule(self, tool_name: str) -> str:
        return self.policy.get(tool_name, "allow")

    def check_permission(self, tool_name: str) -> bool:
        return self._rule(tool_name) != "deny"

    def requires_confirmation(self, tool_name: str) -> bool:
        return self._rule(tool_name) == "confirm"

    def confirm(self, prompt: str) -> bool:
        """Ask the user y/n. In non-interactive mode, refuse."""
        if not self.interactive or not sys.stdin.isatty():
            return False
        try:
            answer = input(f"[CONFIRM] {prompt} [y/N] ").strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes"}

    def set_rule(self, tool_name: str, rule: str) -> None:
        """Runtime override. Not persisted unless save() is called."""
        if rule not in {"allow", "confirm", "deny"}:
            raise ValueError(f"invalid rule: {rule}")
        self.policy[tool_name] = rule

    def save(self) -> None:
        with open(self.policy_path, "w", encoding="utf-8") as f:
            json.dump(self.policy, f, indent=2)
