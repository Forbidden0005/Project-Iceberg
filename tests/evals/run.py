"""
Eval runner for the NL layer.

Implements the agentic-engineering skill's eval-first loop:
  1. Run all cases
  2. Compute pass rate
  3. Compare against baseline (tests/evals/baseline.json)
  4. Report deltas (new failures = regressions, new passes = improvements)

Usage:
  python -m tests.evals.run            # run + print report
  python -m tests.evals.run --update   # update baseline after intentional change

Exits non-zero if any regression is detected, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make project root importable when run as a module
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.dispatcher import Dispatcher  # noqa: E402
from planner.planner import Planner  # noqa: E402
from tests.evals.cases import DISPATCHER_CASES, PLANNER_CASES, DispatcherCase, PlannerCase  # noqa: E402

BASELINE_PATH = Path(__file__).parent / "baseline.json"


# ---------------------------------------------------------------------
# Mock LLM - deterministic, one queued response per call.
# ---------------------------------------------------------------------


class MockLLM:
    name = "mock"
    model = "mock-eval"

    def __init__(self, response: str):
        self.response = response

    def chat(self, messages, **kwargs):
        return self.response


# ---------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    category: str  # "planner" | "dispatcher"
    passed: bool
    expected: Any
    actual: Any
    notes: str


# ---------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------


def run_planner_case(case: PlannerCase) -> CaseResult:
    llm = MockLLM(case.llm_response)
    planner = Planner(llm=llm, tools_description="(eval)")
    actual = planner.create_plan(case.input)

    if case.expected is None:
        # None means we expect the planner to refuse / fall back
        passed = actual is None or actual == []
    elif case.expected == []:
        passed = actual is None or actual == []
    else:
        passed = actual == case.expected

    return CaseResult(
        case_id=case.id,
        category="planner",
        passed=passed,
        expected=case.expected,
        actual=actual,
        notes=case.notes,
    )


def run_dispatcher_case(case: DispatcherCase) -> CaseResult:
    llm = MockLLM(case.llm_response)
    dispatcher = Dispatcher(llm, tools_description="(eval)")
    result = dispatcher.classify(case.input, history=case.history)
    actual_mode = result["mode"]
    passed = actual_mode == case.expected_mode

    return CaseResult(
        case_id=case.id,
        category="dispatcher",
        passed=passed,
        expected=case.expected_mode,
        actual=actual_mode,
        notes=case.notes,
    )


def run_all() -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in PLANNER_CASES:
        results.append(run_planner_case(case))
    for case in DISPATCHER_CASES:
        results.append(run_dispatcher_case(case))
    return results


# ---------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------


def load_baseline() -> dict[str, bool]:
    if not BASELINE_PATH.exists():
        return {}
    try:
        with BASELINE_PATH.open(encoding="utf-8") as f:
            return json.load(f).get("cases", {})
    except Exception:
        return {}


def save_baseline(results: list[CaseResult]) -> None:
    payload = {
        "total": len(results),
        "passing": sum(1 for r in results if r.passed),
        "cases": {r.case_id: r.passed for r in results},
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def compare_to_baseline(results: list[CaseResult], baseline: dict[str, bool]) -> dict[str, list[str]]:
    diff = {"new_failures": [], "new_passes": [], "new_cases": []}
    for r in results:
        if r.case_id not in baseline:
            diff["new_cases"].append(r.case_id)
        elif baseline[r.case_id] and not r.passed:
            diff["new_failures"].append(r.case_id)
        elif not baseline[r.case_id] and r.passed:
            diff["new_passes"].append(r.case_id)
    return diff


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------


def format_value(v: Any, maxlen: int = 120) -> str:
    s = repr(v)
    if len(s) > maxlen:
        s = s[:maxlen] + "..."
    return s


def print_report(results: list[CaseResult], diff: dict[str, list[str]]) -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    by_category: dict[str, list[CaseResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    print("=" * 70)
    print(f"Eval report: {passed}/{total} passing")
    print("=" * 70)

    for category, items in sorted(by_category.items()):
        cat_pass = sum(1 for r in items if r.passed)
        print(f"\n[{category}] {cat_pass}/{len(items)} passing")
        for r in items:
            icon = "PASS" if r.passed else "FAIL"
            print(f"  {icon}  {r.case_id}")
            if not r.passed:
                print(f"        expected: {format_value(r.expected)}")
                print(f"        actual:   {format_value(r.actual)}")
                if r.notes:
                    print(f"        notes:    {r.notes}")

    # Deltas vs baseline
    if diff["new_failures"] or diff["new_passes"] or diff["new_cases"]:
        print("\n" + "=" * 70)
        print("Delta vs baseline")
        print("=" * 70)
        if diff["new_failures"]:
            print(f"REGRESSIONS ({len(diff['new_failures'])}):")
            for cid in diff["new_failures"]:
                print(f"  - {cid}")
        if diff["new_passes"]:
            print(f"IMPROVEMENTS ({len(diff['new_passes'])}):")
            for cid in diff["new_passes"]:
                print(f"  + {cid}")
        if diff["new_cases"]:
            print(f"NEW CASES ({len(diff['new_cases'])}): (not yet in baseline)")
            for cid in diff["new_cases"]:
                print(f"  ? {cid}")


# ---------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NL evals.")
    parser.add_argument("--update", action="store_true", help="Update baseline with current results")
    parser.add_argument("--quiet", action="store_true", help="Only print summary line")
    args = parser.parse_args()

    results = run_all()
    baseline = load_baseline()
    diff = compare_to_baseline(results, baseline)

    if args.quiet:
        passed = sum(1 for r in results if r.passed)
        print(f"{passed}/{len(results)} passing, " f"{len(diff['new_failures'])} regressions")
    else:
        print_report(results, diff)

    if args.update:
        save_baseline(results)
        print(f"\nBaseline updated at {BASELINE_PATH}")
        return 0

    # Exit non-zero on regressions so CI can gate
    return 1 if diff["new_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
