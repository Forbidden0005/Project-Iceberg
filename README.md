# Penguin

Local AI agent that takes natural language. Chats, runs tools on your machine, or does both depending on what you ask.

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

No configuration needed. On startup it auto-detects whichever LLM backend is running:

1. **LM Studio** (`http://localhost:1234`) — local, OpenAI-compatible
2. **Ollama** (`http://localhost:11434`) — local
3. **Anthropic** (cloud) — if `ANTHROPIC_API_KEY` is set

If nothing is reachable, it falls back to regex-only mode and still runs tool commands.

## How natural language works

Every user turn goes through three stages:

```
you type something
      |
      v
  [Dispatcher]  --->  classify: chat | tools | mixed
      |
      +-- chat:   LLM answers conversationally
      +-- tools:  LLM plans tool calls, executor runs them
      +-- mixed:  tools run, then LLM narrates the result
```

So things like:

| You say | What happens |
|---|---|
| `hey what's up` | Chat reply |
| `explain async in python` | Chat reply |
| `list my downloads folder` | Runs `list_dir(~/Downloads)` |
| `what's in this directory?` | Runs `list_dir(.)` |
| `make a note called ideas.txt` | Runs `create_file(ideas.txt)` |
| `scan my desktop and tell me what looks old` | Runs scan + LLM narrates |

The conversation has memory, so this works:
```
> what's in my home folder?
  <list appears>
> and how big is the Downloads one?
  <the model knows "the Downloads one" refers to Downloads in your home>
```

## Configuration

**Environment variables** (simplest):
```bash
# Force a specific backend
AI_ASSISTANT_PROVIDER=lmstudio
LMSTUDIO_MODEL=qwen2.5-coder-7b

# Or use Anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

**Or** copy `config.example.json` to `config.json` and edit.

## Commands

- `help` — show this
- `tools` — list available tools
- `status` — show which LLM is active and history length
- `reset` — clear conversation history
- `exit` or `quit` — leave

Everything else is natural language.

## Architecture

```
main.py
  |
  OrchestratorAgent
    |-- Dispatcher       classify intent (chat|tools|mixed)
    |-- Planner          tool calls from natural language (LLM or regex)
    |-- Executor         safety-gated tool dispatch
    |     |-- FileAgent     file/scan tools
    |     |-- SystemAgent   web/sysinfo/plugin tools
    |-- SafetyManager    policy.json: allow|confirm|deny per tool
    |-- ShortMemory      rolling deque of recent turns
    |-- LongMemory       JSON + cosine-similarity recall
    |-- LLM provider     auto-detected: lmstudio|ollama|anthropic
    |
  AutomationEngine       runs workflows on a timer
  Scheduler              threaded, ticks the engine
```

## Safety

`safety/policy.json` (auto-created):

| tool | rule |
|---|---|
| list_dir, scan, read_file, web_search | allow |
| create_file, delete_file, move_file | confirm |
| run_shell | deny |

Confirm asks `y/N` before running. In non-interactive mode it denies (fail-closed). Edit the JSON to change. Since the LLM can now propose destructive ops freely from natural language, these gates matter more than before.

## Plugins

Drop a Python file in `tools/plugins/`:

```python
def hello(name: str = "world"):
    return f"hi {name}"

def register(registry):
    registry.register(
        "hello", hello,
        description="Say hi.",
        category="system",
        args=[{"name": "name", "required": False, "description": "Who to greet."}],
    )
```

Loaded automatically on startup. The `args` schema is what the LLM reads when deciding how to call your tool.

## Workflows

```json
{
  "name": "cleanup_temp",
  "interval": 10,
  "condition": "file_exists temp.txt",
  "actions": ["delete file temp.txt"]
}
```

Drop in `workflows/`. Conditions: `always`, `never`, `file_exists <path>`, `file_missing <path>`.

## Tests

```bash
python -m unittest discover tests
```

46 tests covering planner, dispatcher, auto-detect, memory, safety, scan, file tools, workflows.

## Layout

```
agent_core/    logger, LLM providers, dispatcher
agents/        orchestrator + sub-agents
automation/    workflow engine
executor/      safety-gated tool dispatch
memory/        short + long-term memory
planner/       NL -> tool calls
safety/        policy-based gating
tools/         builtin tools, registry, plugins
utils/         embedding
voice/         voice mode (optional)
workflows/     user workflow files
logs/          runtime log
tests/         unit tests
```
