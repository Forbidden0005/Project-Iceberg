"""Unit tests. Run: python -m unittest discover tests"""

import os
import shutil
import sys
import tempfile
import unittest

# Make project root importable when tests run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from automation.condition import evaluate
from memory.long_memory import LongMemory
from memory.short_memory import ShortMemory
from planner.planner import Planner
from safety.manager import SafetyManager
from tools.file_tools import create_file, delete_file, list_dir, read_file
from tools.scan_tools import scan
from utils.embedding import cosine_similarity, text_to_vector


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.p = Planner()

    def test_list(self):
        plan = self.p.create_plan("list")
        self.assertIsNotNone(plan)
        self.assertEqual(plan[0]["tool"], "list_dir")

    def test_create_file(self):
        plan = self.p.create_plan("create file notes.txt")
        self.assertEqual(plan[0]["tool"], "create_file")
        self.assertEqual(plan[0]["args"]["path"], "notes.txt")

    def test_move(self):
        plan = self.p.create_plan("move a.txt to b.txt")
        self.assertEqual(plan[0]["tool"], "move_file")
        self.assertEqual(plan[0]["args"], {"src": "a.txt", "dst": "b.txt"})

    def test_search(self):
        plan = self.p.create_plan("search python asyncio")
        self.assertEqual(plan[0]["tool"], "web_search")
        self.assertEqual(plan[0]["args"]["query"], "python asyncio")

    def test_scan_mode(self):
        plan = self.p.create_plan("scan . HIGH")
        self.assertEqual(plan[0]["tool"], "scan")
        self.assertEqual(plan[0]["args"]["mode"], "HIGH")

    def test_empty(self):
        self.assertIsNone(self.p.create_plan(""))
        self.assertIsNone(self.p.create_plan("   "))

    def test_gibberish(self):
        # Nothing matches -> None
        self.assertIsNone(self.p.create_plan("asdf qwerty zxcv"))


class EmbeddingTests(unittest.TestCase):
    def test_identical(self):
        v = text_to_vector("hello world")
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0, places=5)

    def test_disjoint(self):
        a = text_to_vector("cat dog")
        b = text_to_vector("python rust")
        self.assertEqual(cosine_similarity(a, b), 0.0)

    def test_partial_overlap(self):
        a = text_to_vector("python is great")
        b = text_to_vector("python is slow")
        score = cosine_similarity(a, b)
        self.assertTrue(0.0 < score < 1.0)

    def test_empty(self):
        self.assertEqual(cosine_similarity({}, {"a": 1.0}), 0.0)
        self.assertEqual(text_to_vector(""), {})


class ShortMemoryTests(unittest.TestCase):
    def test_capacity(self):
        m = ShortMemory(capacity=3)
        for i in range(5):
            m.add(i)
        self.assertEqual(len(m), 3)
        self.assertEqual(list(m), [2, 3, 4])

    def test_recent(self):
        m = ShortMemory()
        for i in range(10):
            m.add(i)
        self.assertEqual(m.recent(3), [7, 8, 9])


class LongMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "mem.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_search_finds_similar(self):
        m = LongMemory(path=self.path, similarity_threshold=0.0)
        m.add("I love python programming")
        m.add("rust is a great language")
        m.add("my cat is named whiskers")

        results = m.search("python is fun")
        self.assertTrue(len(results) >= 1)
        self.assertIn("python", results[0].lower())

    def test_persistence(self):
        m1 = LongMemory(path=self.path)
        m1.add("test entry for persistence check")

        m2 = LongMemory(path=self.path, similarity_threshold=0.0)
        results = m2.search("test")
        self.assertEqual(results, ["test entry for persistence check"])

    def test_dedup_rejects_near_identical(self):
        m = LongMemory(path=self.path)
        m.add("I love python programming very much")
        m.add("I love python programming very much")
        self.assertEqual(len(m.data), 1)

    def test_noise_filter_rejects_short_input(self):
        m = LongMemory(path=self.path)
        m.add("hello")
        m.add("ok")
        m.add("")
        self.assertEqual(len(m.data), 0)

    def test_noise_filter_rejects_log_lines(self):
        m = LongMemory(path=self.path)
        m.add("2026-04-21 10:44:42 [INFO] [input] some user text here")
        self.assertEqual(len(m.data), 0)

    def test_deduplicate_method_cleans_existing(self):
        m = LongMemory(path=self.path)
        # Manually insert duplicates bypassing the add() guard
        from utils.embedding import text_to_vector

        vec = text_to_vector("python programming is wonderful stuff")
        m.data = [
            {"text": "python programming is wonderful stuff", "vec": vec},
            {"text": "python programming is wonderful stuff", "vec": vec},
            {
                "text": "rust language is also great indeed",
                "vec": text_to_vector("rust language is also great indeed"),
            },
        ]
        m._save()
        removed = m.deduplicate()
        self.assertEqual(removed, 1)
        self.assertEqual(len(m.data), 2)


class AppendFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_append_creates_if_missing(self):
        from tools.file_tools import append_file

        path = os.path.join(self.tmp, "new.txt")
        result = append_file(path, content="first line\n")
        self.assertIn("Appended", result)
        self.assertTrue(os.path.exists(path))

    def test_append_adds_content(self):
        from tools.file_tools import append_file

        path = os.path.join(self.tmp, "log.txt")
        append_file(path, content="line 1\n")
        append_file(path, content="line 2\n")
        with open(path) as f:
            content = f.read()
        self.assertEqual(content, "line 1\nline 2\n")


class ContractTests(unittest.TestCase):
    """Verify ToolCall/ToolResult contracts work end-to-end."""

    def test_toolcall_from_dict(self):
        from agent_core.contracts import ToolCall

        tc = ToolCall.from_any({"tool": "list_dir", "args": {"path": "."}})
        self.assertIsNotNone(tc)
        self.assertEqual(tc.tool, "list_dir")
        self.assertEqual(tc.args, {"path": "."})

    def test_toolcall_rejects_garbage(self):
        from agent_core.contracts import ToolCall

        self.assertIsNone(ToolCall.from_any({"no_tool": "x"}))
        self.assertIsNone(ToolCall.from_any("garbage"))
        self.assertIsNone(ToolCall.from_any(None))

    def test_toolresult_str_delegates(self):
        from agent_core.contracts import ToolResult

        r = ToolResult.success("test", "output text")
        self.assertEqual(str(r), "output text")
        self.assertTrue(r.ok)

    def test_toolresult_failure(self):
        from agent_core.contracts import ToolResult

        r = ToolResult.failure("test", "boom")
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "boom")


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "safety", "policy.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_defaults_and_deny(self):
        s = SafetyManager(policy_path=self.path, interactive=False)
        self.assertTrue(s.check_permission("list_dir"))
        self.assertFalse(s.check_permission("run_shell"))

    def test_confirm_fails_closed_non_interactive(self):
        s = SafetyManager(policy_path=self.path, interactive=False)
        self.assertTrue(s.requires_confirmation("delete_file"))
        self.assertFalse(s.confirm("really?"))

    def test_set_rule(self):
        s = SafetyManager(policy_path=self.path, interactive=False)
        s.set_rule("list_dir", "deny")
        self.assertFalse(s.check_permission("list_dir"))


class ConditionTests(unittest.TestCase):
    def test_always_never(self):
        self.assertTrue(evaluate("always"))
        self.assertFalse(evaluate("never"))
        self.assertTrue(evaluate(""))  # empty = always

    def test_file_exists(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            self.assertTrue(evaluate(f"file_exists {path}"))
            self.assertFalse(evaluate(f"file_missing {path}"))
        finally:
            os.unlink(path)

        self.assertFalse(evaluate("file_exists /does/not/exist/xyz"))
        self.assertTrue(evaluate("file_missing /does/not/exist/xyz"))

    def test_unknown_fails_closed(self):
        self.assertFalse(evaluate("mystery_op something"))


class FileToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_create_read_delete(self):
        path = os.path.join(self.tmp, "x.txt")
        create_file(path, content="hello")
        self.assertEqual(read_file(path), "hello")
        self.assertIn("Deleted", delete_file(path))
        self.assertFalse(os.path.exists(path))

    def test_list_dir_sorted(self):
        create_file(os.path.join(self.tmp, "b.txt"))
        create_file(os.path.join(self.tmp, "a.txt"))
        out = list_dir(self.tmp).splitlines()
        self.assertEqual(out, ["a.txt", "b.txt"])

    def test_delete_directory_refused(self):
        subdir = os.path.join(self.tmp, "sub")
        os.makedirs(subdir)
        result = delete_file(subdir)
        self.assertIn("Refusing", result)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "a", "b"))
        os.makedirs(os.path.join(self.tmp, "c"))
        with open(os.path.join(self.tmp, "root.txt"), "w") as f:
            f.write("root content")
        with open(os.path.join(self.tmp, "a", "b", "deep.txt"), "w") as f:
            f.write("deep content")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_low_walks_whole_tree(self):
        """Regression: original code returned after first dir."""
        out = scan(self.tmp, "LOW")
        self.assertIn("a", out)
        self.assertIn("b", out)
        self.assertIn("c", out)

    def test_medium_includes_files(self):
        out = scan(self.tmp, "MEDIUM")
        self.assertIn("root.txt", out)
        self.assertIn("deep.txt", out)

    def test_high_includes_content(self):
        out = scan(self.tmp, "HIGH")
        self.assertIn("root content", out)
        self.assertIn("deep content", out)

    def test_bad_path(self):
        self.assertIn("not found", scan("/nope/nope/nope", "LOW").lower())

    def test_bad_mode(self):
        self.assertIn("unknown mode", scan(self.tmp, "EXTREME").lower())


if __name__ == "__main__":
    unittest.main()
