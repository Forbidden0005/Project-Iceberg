"""
Expose eval cases as standard unittest tests so they run with the rest of the
suite. Separate file from run.py so the richer CLI report (deltas vs baseline)
stays available for manual runs.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.evals.cases import DISPATCHER_CASES, PLANNER_CASES  # noqa: E402
from tests.evals.run import run_dispatcher_case, run_planner_case  # noqa: E402


class PlannerEvals(unittest.TestCase):
    """Capability + regression evals for the Planner's LLM path."""


class DispatcherEvals(unittest.TestCase):
    """Capability + regression evals for the Dispatcher classifier."""


def _make_planner_test(case):
    def test(self):
        result = run_planner_case(case)
        self.assertTrue(
            result.passed,
            msg=(
                f"\n  case:     {case.id}"
                f"\n  input:    {case.input!r}"
                f"\n  expected: {result.expected!r}"
                f"\n  actual:   {result.actual!r}"
                f"\n  notes:    {case.notes}"
            ),
        )

    test.__doc__ = case.notes or case.id
    return test


def _make_dispatcher_test(case):
    def test(self):
        result = run_dispatcher_case(case)
        self.assertTrue(
            result.passed,
            msg=(
                f"\n  case:     {case.id}"
                f"\n  input:    {case.input!r}"
                f"\n  expected: {result.expected!r}"
                f"\n  actual:   {result.actual!r}"
                f"\n  notes:    {case.notes}"
            ),
        )

    test.__doc__ = case.notes or case.id
    return test


# Dynamically attach one test method per case so they show up individually
for _case in PLANNER_CASES:
    _name = "test_" + _case.id.replace(".", "_")
    setattr(PlannerEvals, _name, _make_planner_test(_case))

for _case in DISPATCHER_CASES:
    _name = "test_" + _case.id.replace(".", "_")
    setattr(DispatcherEvals, _name, _make_dispatcher_test(_case))


if __name__ == "__main__":
    unittest.main()
