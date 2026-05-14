"""Tests for the natural-language layer."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent_core import llm as llm_mod
from agent_core.dispatcher import Dispatcher
from planner.planner import Planner
from tools.registry import describe_for_llm

# --------------------------------------------------------------------
# Mock LLM. Returns a queued list of responses in order.
# --------------------------------------------------------------------


class MockLLM:
    name = "mock"
    model = "mock-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("MockLLM out of queued responses")
        return self.responses.pop(0)

    def complete(self, prompt, **kwargs):
        return self.chat([{"role": "user", "content": prompt}], **kwargs)


# --------------------------------------------------------------------


class DispatcherTests(unittest.TestCase):
    def test_chat_classification(self):
        llm = MockLLM(['{"mode":"chat","reasoning":"greeting"}'])
        d = Dispatcher(llm, "list_dir, scan")
        out = d.classify("hey how's it going")
        self.assertEqual(out["mode"], "chat")

    def test_tools_classification(self):
        llm = MockLLM(['{"mode":"tools","reasoning":"listing"}'])
        d = Dispatcher(llm, "list_dir, scan")
        out = d.classify("show me what's in my home folder")
        self.assertEqual(out["mode"], "tools")

    def test_mixed_classification(self):
        llm = MockLLM(['{"mode":"mixed","reasoning":"scan and summarise"}'])
        d = Dispatcher(llm, "list_dir, scan")
        out = d.classify("scan my desktop and tell me what's old")
        self.assertEqual(out["mode"], "mixed")

    def test_llm_garbage_falls_back_to_heuristic(self):
        llm = MockLLM(["I think you want to chat maybe"])  # not JSON
        d = Dispatcher(llm, "list_dir")
        out = d.classify("list my desktop")
        self.assertEqual(out["mode"], "tools")  # heuristic matched "list"

    def test_no_llm_uses_heuristic(self):
        d = Dispatcher(None, "list_dir")
        self.assertEqual(d.classify("list my files")["mode"], "tools")
        self.assertEqual(d.classify("how are you")["mode"], "chat")

    def test_invalid_mode_defaults_to_chat(self):
        llm = MockLLM(['{"mode":"dance","reasoning":"?"}'])
        d = Dispatcher(llm, "")
        self.assertEqual(d.classify("anything")["mode"], "chat")

    def test_handles_fenced_json(self):
        llm = MockLLM(['```json\n{"mode":"tools","reasoning":"x"}\n```'])
        d = Dispatcher(llm, "")
        self.assertEqual(d.classify("do something")["mode"], "tools")

    def test_handles_chatty_preamble(self):
        llm = MockLLM(['Sure! Here is the answer: {"mode":"chat","reasoning":"greeting"}'])
        d = Dispatcher(llm, "")
        self.assertEqual(d.classify("hi")["mode"], "chat")


class LLMPlannerTests(unittest.TestCase):
    def test_llm_plan_preferred(self):
        llm = MockLLM(['[{"tool":"list_dir","args":{"path":"~/Downloads"}}]'])
        p = Planner(llm=llm, tools_description=describe_for_llm())
        plan = p.create_plan("show me what's in downloads")
        self.assertEqual(plan, [{"tool": "list_dir", "args": {"path": "~/Downloads"}}])

    def test_llm_empty_array_returns_none(self):
        """LLM returning [] means 'can't do this' - planner refuses.

        Previously this fell through to regex parsing of the user input, which
        let the planner invent actions from words in the utterance when the
        LLM had explicitly declined. Contract tightened per agentic-engineering
        'stable contracts' principle: LLM output is authoritative when an LLM
        is configured.
        """
        llm = MockLLM(["[]"])
        p = Planner(llm=llm, tools_description="")
        plan = p.create_plan("list .")
        # Empty array from LLM -> no plan (not regex-fallback-from-input).
        self.assertIn(plan, (None, []))

    def test_llm_garbage_returns_none(self):
        """Non-JSON LLM output is a planner failure, not regex-fallback fuel."""
        llm = MockLLM(["I don't know"])
        p = Planner(llm=llm, tools_description="")
        plan = p.create_plan("list")
        # Malformed LLM output -> no plan. Don't silently parse user input.
        self.assertIsNone(plan)

    def test_no_llm_uses_regex(self):
        """Without an LLM, regex fallback handles simple patterns."""
        p = Planner(llm=None, tools_description="")
        plan = p.create_plan("list")
        self.assertIsNotNone(plan)
        self.assertEqual(plan[0]["tool"], "list_dir")

    def test_malformed_step_skipped(self):
        llm = MockLLM(['[{"tool":"list_dir","args":{}}, "garbage", {"no_tool":"x"}]'])
        p = Planner(llm=llm, tools_description="")
        plan = p.create_plan("do stuff")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["tool"], "list_dir")

    def test_fenced_output(self):
        llm = MockLLM(['```json\n[{"tool":"scan","args":{"path":".","mode":"LOW"}}]\n```'])
        p = Planner(llm=llm, tools_description="")
        plan = p.create_plan("scan here")
        self.assertEqual(plan[0]["tool"], "scan")

    def test_history_passed_to_llm(self):
        llm = MockLLM(['[{"tool":"list_dir","args":{}}]'])
        p = Planner(llm=llm, tools_description="")
        p.create_plan(
            "do it",
            history=[
                {"role": "user", "content": "should I list my desktop?"},
                {"role": "assistant", "content": "Want me to list it?"},
            ],
        )
        # The last call's messages should contain the history
        roles = [m["role"] for m in llm.calls[0]]
        self.assertIn("user", roles)
        # history turns + new turn + system
        self.assertGreaterEqual(len(llm.calls[0]), 3)


class ProviderAutoDetectTests(unittest.TestCase):
    """get_provider() should try lmstudio -> ollama -> anthropic."""

    def test_picks_lmstudio_when_reachable(self):
        with (
            patch.object(llm_mod.LMStudioProvider, "is_reachable", return_value=True),
            patch.object(llm_mod.OllamaProvider, "is_reachable", return_value=True),
            patch.object(llm_mod, "_load_config", return_value={}),
            patch.dict(os.environ, {}, clear=True),
        ):
            p = llm_mod.get_provider()
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "lmstudio")

    def test_falls_through_to_ollama(self):
        with (
            patch.object(llm_mod.LMStudioProvider, "is_reachable", return_value=False),
            patch.object(llm_mod.OllamaProvider, "is_reachable", return_value=True),
            patch.object(llm_mod, "_load_config", return_value={}),
            patch.dict(os.environ, {}, clear=True),
        ):
            p = llm_mod.get_provider()
            self.assertEqual(p.name, "ollama")

    def test_returns_none_when_nothing_reachable(self):
        with (
            patch.object(llm_mod.LMStudioProvider, "is_reachable", return_value=False),
            patch.object(llm_mod.OllamaProvider, "is_reachable", return_value=False),
            patch.object(llm_mod, "_load_config", return_value={}),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertIsNone(llm_mod.get_provider())


if __name__ == "__main__":
    unittest.main()
