"""
test_reflection.py — Unit tests for the self-improvement / reflection subsystem.

Covers:
  - Lesson dataclass (serialisation, effective_confidence blending)
  - LessonStore (add, search, remove, dedup, prune)
  - ReflectionEngine (rule-based path; LLM path via mock)
  - Planner lesson injection (_lessons_block)
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from reflection.lesson import Lesson
from reflection.store import LessonStore
from reflection.engine import ReflectionEngine, TurnContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lesson(**kwargs) -> Lesson:
    defaults = dict(text="When listing dirs, prefer scan_dir.", trigger="listing directory")
    defaults.update(kwargs)
    return Lesson(**defaults)


def _store_with_path(path: str) -> LessonStore:
    return LessonStore(path=path)


# ---------------------------------------------------------------------------
# Lesson dataclass tests
# ---------------------------------------------------------------------------


class LessonTests(unittest.TestCase):

    def test_defaults(self):
        l = Lesson(text="Do X.", trigger="situation Y")
        self.assertTrue(l.id)
        self.assertEqual(l.category, "planning")
        self.assertEqual(l.source, "llm")
        self.assertAlmostEqual(l.confidence, 0.7)

    def test_helpfulness_no_uses(self):
        l = Lesson(text="Do X.", trigger="Y")
        self.assertEqual(l.helpfulness, 0.0)

    def test_helpfulness_with_uses(self):
        l = Lesson(text="Do X.", trigger="Y", use_count=4, helpful_count=3)
        self.assertAlmostEqual(l.helpfulness, 0.75)

    def test_effective_confidence_few_uses(self):
        l = Lesson(text="T", trigger="T", confidence=0.8, use_count=2, helpful_count=2)
        # Under 3 uses → raw confidence returned
        self.assertAlmostEqual(l.effective_confidence, 0.8)

    def test_effective_confidence_many_uses(self):
        # 10 uses, 10 helpful → very high
        l = Lesson(text="T", trigger="T", confidence=0.5, use_count=10, helpful_count=10)
        self.assertGreater(l.effective_confidence, 0.7)

    def test_roundtrip(self):
        l = _make_lesson(category="error", confidence=0.6, source="rule")
        restored = Lesson.from_dict(l.to_dict())
        self.assertEqual(restored.id, l.id)
        self.assertEqual(restored.text, l.text)
        self.assertEqual(restored.category, "error")
        self.assertAlmostEqual(restored.confidence, 0.6)

    def test_repr_truncates(self):
        l = Lesson(text="A" * 100, trigger="T")
        r = repr(l)
        self.assertIn("...", r)


# ---------------------------------------------------------------------------
# LessonStore tests
# ---------------------------------------------------------------------------


class LessonStoreTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)  # start with no file
        self.store = _store_with_path(self.tmp.name)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_add_and_count(self):
        self.store.add(_make_lesson(text="Lesson A.", trigger="situation A"))
        self.assertEqual(self.store.count(), 1)

    def test_persistence(self):
        self.store.add(_make_lesson(text="Persisted lesson.", trigger="persist test"))
        # Reload from disk
        store2 = _store_with_path(self.tmp.name)
        self.assertEqual(store2.count(), 1)
        self.assertEqual(store2.all()[0].text, "Persisted lesson.")

    def test_remove(self):
        lesson = _make_lesson(text="Remove me.", trigger="remove test")
        self.store.add(lesson)
        self.assertEqual(self.store.count(), 1)
        removed = self.store.remove(lesson.id)
        self.assertTrue(removed)
        self.assertEqual(self.store.count(), 0)

    def test_remove_nonexistent(self):
        removed = self.store.remove("not-a-real-id")
        self.assertFalse(removed)

    def test_deduplication(self):
        # Add the same lesson text twice — second should be rejected
        lesson = _make_lesson(text="Unique lesson text for dedup test.", trigger="dedup")
        self.store.add(lesson)
        # Identical lesson (different id)
        self.store.add(_make_lesson(text="Unique lesson text for dedup test.", trigger="dedup"))
        self.assertEqual(self.store.count(), 1)

    def test_all_newest_first(self):
        self.store.add(_make_lesson(text="First lesson.", trigger="first"))
        self.store.add(_make_lesson(text="Second lesson.", trigger="second"))
        lessons = self.store.all()
        self.assertEqual(lessons[0].text, "Second lesson.")

    def test_mark_used(self):
        lesson = _make_lesson()
        self.store.add(lesson)
        self.store.mark_used([lesson.id], helpful=True)
        updated = self.store.all()[0]
        self.assertEqual(updated.use_count, 1)
        self.assertEqual(updated.helpful_count, 1)

    def test_mark_used_not_helpful(self):
        lesson = _make_lesson()
        self.store.add(lesson)
        self.store.mark_used([lesson.id], helpful=False)
        updated = self.store.all()[0]
        self.assertEqual(updated.use_count, 1)
        self.assertEqual(updated.helpful_count, 0)

    def test_search_returns_list(self):
        self.store.add(_make_lesson(text="Scan dirs with scan_dir.", trigger="scanning a directory"))
        results = self.store.search("scan directory contents", top_n=3)
        self.assertIsInstance(results, list)

    def test_search_empty_store(self):
        results = self.store.search("anything")
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# ReflectionEngine rule-based tests
# ---------------------------------------------------------------------------


class ReflectionEngineRuleTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        self.store = _store_with_path(self.tmp.name)
        # No LLM → pure rule-based path
        self.engine = ReflectionEngine(store=self.store, provider=None)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_chat_success_produces_no_lesson(self):
        ctx = TurnContext(user_request="Hello!", intent="chat", success=True)
        lesson = self.engine.reflect(ctx)
        self.assertIsNone(lesson)
        self.assertEqual(self.store.count(), 0)

    def test_failed_tool_produces_lesson(self):
        ctx = TurnContext(
            user_request="List my downloads",
            intent="tools",
            results=[{"tool": "list_dir", "success": False, "output": "Permission denied"}],
            success=False,
            error="Permission denied",
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.category, "error")
        self.assertIn("list_dir", lesson.text)
        self.assertEqual(lesson.source, "rule")
        self.assertEqual(self.store.count(), 1)

    def test_multi_tool_success_produces_lesson(self):
        ctx = TurnContext(
            user_request="Scan and summarise my project",
            intent="tools",
            results=[
                {"tool": "scan_dir", "success": True, "output": "..."},
                {"tool": "read_file", "success": True, "output": "..."},
                {"tool": "create_file", "success": True, "output": "..."},
            ],
            success=True,
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.category, "planning")

    def test_planning_failure_produces_lesson(self):
        ctx = TurnContext(
            user_request="Do something impossible",
            intent="tools",
            results=[],
            success=False,
            error="No plan could be generated",
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNotNone(lesson)
        self.assertIn("planning", lesson.category)

    def test_reflect_async_does_not_crash(self):
        ctx = TurnContext(
            user_request="crash test",
            intent="tools",
            results=[{"tool": "list_dir", "success": False, "output": "err"}],
            success=False,
        )
        # Should not raise even in background thread
        self.engine.reflect_async(ctx)
        import time; time.sleep(0.1)  # let thread finish


# ---------------------------------------------------------------------------
# ReflectionEngine LLM path tests (mocked)
# ---------------------------------------------------------------------------


class ReflectionEngineLLMTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        self.store = _store_with_path(self.tmp.name)
        self.mock_llm = MagicMock()
        self.engine = ReflectionEngine(store=self.store, provider=self.mock_llm)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_llm_valid_json_produces_lesson(self):
        self.mock_llm.chat.return_value = json.dumps({
            "text": "When scanning dirs use scan_dir not list_dir.",
            "trigger": "scanning directory contents",
            "category": "tool_use",
            "confidence": 0.85,
        })
        ctx = TurnContext(
            user_request="List everything in my project",
            intent="tools",
            results=[{"tool": "list_dir", "success": True, "output": "..."}],
            success=True,
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.source, "llm")
        self.assertEqual(lesson.category, "tool_use")
        self.assertAlmostEqual(lesson.confidence, 0.85)

    def test_llm_null_produces_no_lesson(self):
        self.mock_llm.chat.return_value = "null"
        ctx = TurnContext(
            user_request="Hello",
            intent="tools",
            results=[{"tool": "list_dir", "success": True, "output": "..."}],
            success=True,
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNone(lesson)
        self.assertEqual(self.store.count(), 0)

    def test_llm_garbage_falls_back_to_rules(self):
        self.mock_llm.chat.return_value = "not valid json at all!!!"
        ctx = TurnContext(
            user_request="Do something",
            intent="tools",
            results=[{"tool": "scan_dir", "success": False, "output": "err"}],
            success=False,
            error="scan failed",
        )
        lesson = self.engine.reflect(ctx)
        # Rule fallback should still produce a lesson for the failure
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.source, "rule")

    def test_llm_fenced_json(self):
        self.mock_llm.chat.return_value = (
            "```json\n"
            '{"text":"Use X not Y.","trigger":"doing X","category":"planning","confidence":0.7}\n'
            "```"
        )
        ctx = TurnContext(
            user_request="Do X",
            intent="tools",
            results=[{"tool": "read_file", "success": True, "output": "ok"}],
            success=True,
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.text, "Use X not Y.")

    def test_generic_lesson_rejected(self):
        self.mock_llm.chat.return_value = json.dumps({
            "text": "Always be helpful and accurate in responses.",
            "trigger": "any request",
            "category": "planning",
            "confidence": 0.9,
        })
        ctx = TurnContext(
            user_request="Search the web",
            intent="tools",
            results=[{"tool": "web_search", "success": True, "output": "results"}],
            success=True,
        )
        lesson = self.engine.reflect(ctx)
        self.assertIsNone(lesson)  # generic phrase filtered out

    def test_set_provider(self):
        new_provider = MagicMock()
        self.engine.set_provider(new_provider)
        self.assertIs(self.engine._provider, new_provider)


# ---------------------------------------------------------------------------
# Planner lesson injection tests
# ---------------------------------------------------------------------------


class PlannerLessonInjectionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        self.store = _store_with_path(self.tmp.name)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_no_store_returns_empty(self):
        from planner.planner import Planner
        p = Planner(lesson_store=None)
        block = p._lessons_block("anything")
        self.assertEqual(block, "")

    def test_empty_store_returns_empty(self):
        from planner.planner import Planner
        p = Planner(lesson_store=self.store)
        block = p._lessons_block("list my files")
        self.assertEqual(block, "")

    def test_relevant_lesson_injected(self):
        from planner.planner import Planner
        self.store.add(Lesson(
            text="Prefer scan_dir over list_dir for large dirs.",
            trigger="listing or scanning directory contents",
            confidence=0.8,
        ))
        p = Planner(lesson_store=self.store)
        block = p._lessons_block("list all files in my project folder")
        self.assertIn("Self-Improvement", block)
        self.assertIn("scan_dir", block)

    def test_block_appended_to_system_prompt(self):
        from planner.planner import Planner
        self.store.add(Lesson(
            text="When user says 'search', use web_search tool.",
            trigger="web search request",
            confidence=0.9,
        ))
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "[]"
        p = Planner(llm=mock_llm, lesson_store=self.store)
        p._llm_plan("search for python tutorials", [])
        # Verify the system message passed to LLM contained the lesson
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_content = messages[0]["content"]
        self.assertIn("Self-Improvement", system_content)


if __name__ == "__main__":
    unittest.main()
