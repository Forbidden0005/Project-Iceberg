# Codebase Improvement Report

**Date:** 2026-04-21
**Mode:** safe
**Scope:** Applied agentic-engineering, ai-first-engineering, coding-standards, clean-codebase skills

---

## Metrics

| Metric                           | Before | After | Change |
|----------------------------------|-------:|------:|-------:|
| Unit tests                       |     46 |    47 |     +1 |
| Eval cases (planner + dispatcher)|      0 |    20 |    +20 |
| **Total tests passing**          | **46** | **67** | **+21** |
| Ruff errors (base config)        |      2 |     0 |     -2 |
| Ruff errors (full ruleset)       |    107 |     0 |   -107 |
| Type-annotated public surfaces   |  loose | tight |   —    |
| Magic numbers in logic           |    ~15 |     0 |   -15  |
| Tooling config files             |      0 |     3 |    +3  |
| Bugs caught by eval harness      |      0 |     1 |    +1  |

---

## Changes Applied

### Unit 1: Baseline measurement
Captured starting state in `baseline.json` so improvements are quantifiable per the clean-codebase skill Step 1.

### Unit 2: Tooling configuration
- `pyproject.toml` with ruff (pyflakes + pycodestyle + bugbear + pyupgrade + simplify + pylint subset), black (line-length 110), vulture configs
- `.editorconfig` for consistent whitespace
- Practical rule exclusions documented with rationale

### Unit 3: Automated lint fixes
107 ruff findings → 0. All safe modernizations:
- `typing.List` → `list`, `typing.Dict` → `dict` (53 sites)
- Import sorting across 17 files
- Removed unused imports (`datetime`, `time`)
- Simplified one nested-if in `executor/executor.py`
Intentional patterns (lazy voice imports, singleton TTS engine) got `noqa` comments with rationale, per coding-standards "explain WHY not WHAT".

### Unit 4: Typed contracts (ai-first-engineering "stable contracts")
New `agent_core/contracts.py` with `ToolCall` and `ToolResult` dataclasses. Executor now emits typed `ToolResult` instead of mixing success and error into the same string channel. `ToolCall.from_any()` and `ToolResult.__str__` delegation preserve backwards compatibility.

### Unit 5: Magic number elimination
New `agent_core/constants.py` centralizes every tunable number with rationale. Wired through `orchestrator_agent.py`, `llm.py`, `dispatcher.py`, `planner.py`, `memory/*`, `tools/*`, `voice/input.py`, `automation/scheduler.py`. Per coding-standards: no unexplained numbers scattered in logic.

### Unit 6: Encapsulation fixes
- Extracted `OrchestratorAgent.__init__` into `_build_llm_stack()`, `_build_execution_stack()`, `_build_memory_stack()` (coding-standards "long functions" rule)
- Added public `history_depth()` and `llm_info()` accessors so `main.py` stops reaching into private `_history`

### Unit 8: Eval harness (highest-value improvement)
**This is the single most important change.** Agentic-engineering and ai-first-engineering both lead with "eval coverage matters more than anecdotal confidence." Project had zero NL evals.

Delivered:
- `tests/evals/cases.py` — 20 structured cases (11 planner + 9 dispatcher), split between capability evals and regression evals, each with id, input, LLM response, expected outcome, notes
- `tests/evals/run.py` — CLI runner with baseline comparison, delta reporting (regressions/improvements/new cases), non-zero exit on regression so CI can gate
- `tests/evals/test_evals.py` — unittest wrapper exposing each case as an individual test method
- `tests/evals/baseline.json` — 20/20 passing baseline recorded

**Bug caught on first run:** `regress.plan_is_list_not_object`. When the LLM returned a bare JSON object instead of an array, the planner fell through to regex parsing the raw user input, inventing actions from user text. E.g. LLM returns `{"tool":"list_dir","args":{}}` for "list here" → planner output was `[{"tool":"list_dir","args":{"path":"here"}}]` — path invented from user's word.

**Contract fix:** When an LLM is configured, its output is authoritative (malformed/empty → None). Regex fallback only fires when no LLM is configured. Two existing `test_nl.py` tests encoded the buggy contract and were updated with comments linking to the eval case that exposed the issue.

### Unit 9: Command dispatch table
`main.py` if/elif chain → dict of `{name: handler}`. Fewer branches, trivially extensible, no more direct access to agent internals.

---

## Validation

- [x] 67/67 tests pass (46 original + 20 evals + 1 updated test)
- [x] `ruff check .` clean with full ruleset
- [x] End-to-end CLI smoke test passes (status, tools, reset, exit)
- [x] Eval baseline saved for regression detection
- [x] Safety gating still fail-closed in non-interactive mode (unchanged, still tested)
- [x] Backwards compatibility: `ToolCall.from_any` accepts old dict format; `ToolResult.__str__` delegates to output so existing print-based callers unchanged

---

## Not Done (Explicitly Scoped Out)

- **Unit 7 (integration test for full orchestrator pipeline):** The eval harness covers the planner+dispatcher path end-to-end with mocked LLMs; a dedicated integration test would add exercise for the memory+executor+narrate chain, but per agentic-engineering "measure where it hurts most," the planner/dispatcher path is the one with LLM variability and is now well-covered.

- **Semantic memory upgrade:** `utils/embedding.py` is still bag-of-words TF. Working but could use `sentence-transformers` for true semantic recall. Not in this skill's scope.

- **Streaming LLM output:** Chat responses block until complete. Listed for future work.

---

## Key Takeaways from Applying the Skills

1. **The eval harness was the single highest-leverage change.** It caught a real bug on first run — one that would have shipped unnoticed to a user with a flaky local model. Agentic-engineering's "eval-first loop" isn't academic; it has immediate ROI.

2. **Typed contracts clarify responsibilities.** Before `ToolResult`, executor callers had to string-match error prefixes to know if a tool succeeded. After: `result.ok` is the answer. This is what ai-first-engineering means by "stable contracts at module boundaries."

3. **Fallback paths need clear triggers.** The planner bug was classic: "LLM missing" and "LLM misbehaving" were both routed to the same fallback, creating surprising behavior when the two conditions diverged. Agentic-engineering's "avoid hidden coupling" maps directly to this.

4. **Magic numbers mask intent.** Extracting them into a named constants module with rationale comments is low-effort and high-clarity. Coding-standards is right to call this out explicitly.

5. **Auto-fixers are the bulk of hygiene work.** 98 of 107 ruff findings were safe mechanical fixes. Running them first (clean-codebase Step 2) cleared the noise so the remaining 9 meaningful cases could get proper noqa rationale.
