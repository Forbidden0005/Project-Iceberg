# Project Iceberg — Claude Configuration

**Last Updated**: 2026-05-13  
**Claude Version**: Sonnet 4.6  
**Project Lead**: Tyler

---

## 🎯 Project Mission

**Project Iceberg** is a local-first, privacy-focused AI assistant with multi-LLM support, MCP extensibility, and a modular tool architecture. The tagline: *"What you see is just the tip of the iceberg."*

**Core Value Prop**: Run a powerful AI assistant entirely on local hardware with automatic fallback across multiple LLM backends (LM Studio, Ollama, Anthropic), extensible via Model Context Protocol (MCP), with both CLI and web UI. Includes semantic memory (ChromaDB + nomic-embed-text), local voice (Whisper), vision tools (moondream/LLaVA via Ollama), and a fine-tuning pipeline (unsloth + LoRA).

**Target Users**: Technical users who want local control, privacy, and extensibility without sacrificing capability.

---

## 💬 Communication Protocol

### Critical Rule: Direct, Honest Communication

Tyler values **straight technical assessment** over softened responses:

- ✅ **If something won't work**: Say it immediately and plainly
- ✅ **If you're uncertain**: State the uncertainty upfront
- ✅ **If you need clarification**: Ask directly
- ❌ **Don't attempt and walk back**: Never start work then say "actually this won't work"
- ❌ **No fluff, no softening**: Skip preambles, get to the technical point

**Example — Good**:
```
That approach won't work here. The Flask session globals aren't thread-safe 
for background workers. Use a job queue (RQ/Celery) or move it to the 
orchestrator's state dict instead.
```

**Example — Bad**:
```
I think we could try that approach and see how it goes... [attempts] 
Actually, on second thought, this might not be the best solution...
```

---

## 🏗️ Architecture Overview

### System Architecture

```
main.py (CLI)  |  server.py (Web UI)
       |                |
       +----> OrchestratorAgent <----+
                   |
    +--------------+--------------+
    |              |              |
Dispatcher    Planner        Executor
 (classify)   (NL→tools)    (safety gates)
    |              |              |
    |              |        +-----+-----+
    |              |        |           |
    |              |   FileAgent  SystemAgent
    |              |
    +-----LLM Provider (auto-detect)
    |        |       |        |
  LMStudio Ollama Anthropic (regex fallback)
    |
    +-----MCP Servers (optional)
    |
Memory System
  ├─ ShortMemory (rolling deque)
  └─ LongMemory (JSON + cosine similarity)
    |
AutomationEngine
  └─ Scheduler (threaded workflows)
```

### Key Design Patterns

1. **Multi-LLM with Auto-Detection**
   - Probe order: LM Studio (`:1234`) → Ollama (`:11434`) → Anthropic
   - First reachable backend wins
   - Regex-only mode if no LLM available (still executes tools)

2. **Type-Safe Contracts**
   - `ToolCall` and `ToolResult` dataclasses in `agent_core/contracts.py`
   - Replaces loose dict-based plans with typed interfaces
   - All modules accept both legacy dicts and typed contracts for backward compat

3. **Safety-Gated Execution**
   - `safety/policy.json`: per-tool `allow|confirm|deny` rules
   - Fail-closed: confirm prompts default to deny in non-interactive mode
   - User can edit JSON to change tool policies

4. **Extensibility**
   - **MCP**: Connect external tool servers (filesystem, memory, GitHub, etc.)
   - **Plugins**: Drop Python files in `tools/plugins/`, auto-loaded on startup
   - **Workflows**: JSON-based automation with condition/action DSL

5. **Memory System**
   - **Short**: Rolling deque of recent turns (in-memory)
   - **Long**: JSON file with cosine-similarity recall for knowledge retrieval

---

## 🛠️ Tech Stack

### Core Dependencies

```
Python 3.11+
├─ requests         # HTTP client
├─ flask            # Web UI server
├─ mcp              # Model Context Protocol
├─ chromadb         # Semantic vector store (long-term memory)
├─ pillow           # Image I/O for vision tools
│
└─ (optional)
   ├─ openai-whisper  # Local offline speech recognition
   ├─ pyttsx3         # Text-to-speech output
   └─ pyaudio         # Microphone input
```

### ML / AI Infrastructure (via Ollama — no pip install)

```
Ollama models (pull once, use forever):
  nomic-embed-text   # Semantic embeddings for memory (ollama pull nomic-embed-text)
  moondream          # Vision analysis, fast ~1.7 GB (ollama pull moondream)
  llava              # Richer vision reasoning, ~4 GB (ollama pull llava)
```

### Development Tools

- **Formatting**: black, isort
- **Linting**: ruff
- **Cleanup**: autoflake, vulture
- **Testing**: unittest (46 tests across unit + eval suites)

### Codebase Stats

- **59 Python files** (production code — +4 for ML upgrade)
- **7 JSON files** (configs, workflows, test data)
- **Last cleanup**: 2026-05-11 (all lint warnings resolved)
- **ML upgrade**: 2026-05-13 (semantic memory, Whisper voice, vision tools, fine-tuning)

---

## 📁 Project Structure

```
Project Iceberg/
├── main.py                 # CLI entry point
├── server.py               # Flask web UI + API
├── Launch.bat              # Windows launcher (installs deps + starts server)
├── requirements.txt
├── config.example.json     # Template config
│
├── agent_core/             # Core orchestration logic
│   ├── dispatcher.py       # Intent classification (chat|tools|mixed)
│   ├── llm.py              # Multi-provider LLM abstraction
│   ├── contracts.py        # ToolCall/ToolResult dataclasses
│   ├── logger.py           # Logging setup
│   └── constants.py        # Config constants
│
├── agents/                 # Agent implementations
│   ├── orchestrator_agent.py  # Main coordinator
│   ├── file_agent.py       # File operations
│   └── system_agent.py     # System/web tools
│
├── planner/                # NL → tool calls
│   └── planner.py          # LLM-based + regex fallback
│
├── executor/               # Tool execution
│   └── executor.py         # Safety-gated dispatcher
│
├── tools/                  # Tool registry + implementations
│   ├── registry.py         # Central tool registration
│   ├── loader.py           # Auto-discovery
│   ├── file_tools.py       # File operations
│   ├── web_tools.py        # Web search, fetch
│   ├── scan_tools.py       # Directory scanning
│   ├── system_tools.py     # System info, launch_app
│   ├── mcp_loader.py       # MCP server integration
│   ├── mcp_catalog.py      # Built-in MCP server definitions
│   └── plugins/            # User-added tools (auto-loaded)
│
├── memory/                 # Memory systems
│   ├── short_memory.py     # Recent conversation turns
│   └── long_memory.py      # Persistent knowledge store
│
├── automation/             # Workflow engine
│   ├── engine.py           # Execution engine
│   ├── scheduler.py        # Threaded timer
│   ├── condition.py        # Workflow conditions
│   └── storage.py          # Workflow loader
│
├── safety/                 # Safety gates
│   ├── manager.py          # Policy enforcement
│   └── policy.json         # Per-tool allow/confirm/deny rules
│
├── voice/                  # Voice mode (optional)
│   ├── input.py            # Speech recognition
│   ├── output.py           # Text-to-speech
│   └── voice_mode.py       # Voice loop
│
├── modules/                # Dynamic module loading
│   ├── loader.py           # Module discovery
│   ├── base.py             # Module base class
│   └── core/module.py      # Core module implementation
│
├── training/               # Fine-tuning pipeline (unsloth + LoRA)
│   ├── export_history.py   # Export conversation history → JSONL dataset
│   ├── finetune.py         # LoRA fine-tune on local GPU (GTX 1080 Ti)
│   └── requirements_training.txt  # Heavy ML deps (install separately)
│
├── tools/
│   └── vision_tools.py     # analyze_image, capture_screen, read_text_from_image
│
├── utils/                  # Utilities
│   └── embedding.py        # SmartEmbedder: Ollama nomic-embed-text + BoW fallback
│
├── workflows/              # User workflow definitions
│   └── sample.json         # Example workflow
│
├── tests/                  # Test suite
│   ├── test_core.py        # Core functionality tests
│   ├── test_unit1.py       # Unit tests batch 1
│   ├── test_unit2.py       # Unit tests batch 2
│   ├── test_nl.py          # Natural language tests
│   └── evals/              # Eval harness
│       ├── run.py          # Eval runner
│       ├── cases.py        # Test cases
│       ├── test_evals.py   # Eval suite
│       └── baseline.json   # Expected outputs
│
├── logs/                   # Runtime logs
├── Reports/                # Cleanup/audit reports
└── static/                 # Web UI assets (if present)
```

---

## 🔑 Key Files to Know

### Entry Points

| File | Purpose | When to Edit |
|------|---------|--------------|
| `main.py` | CLI interface | Adding CLI commands or startup logic |
| `server.py` | Web UI + REST API | Adding web routes or UI features |
| `Launch.bat` | Windows launcher | Changing Windows startup flow |

### Core Logic

| File | Purpose | When to Edit |
|------|---------|--------------|
| `agent_core/dispatcher.py` | Intent classification (chat vs tools) | Changing classification logic |
| `agent_core/llm.py` | LLM provider abstraction | Adding new LLM backends |
| `planner/planner.py` | Natural language → tool calls | Improving planning prompts or regex fallback |
| `executor/executor.py` | Safety-gated tool execution | Adding execution hooks or logging |
| `agent_core/contracts.py` | Type definitions | Adding new contract types |

### Tools & Extensibility

| File | Purpose | When to Edit |
|------|---------|--------------|
| `tools/registry.py` | Central tool registration | Rarely (auto-populated by loaders) |
| `tools/*_tools.py` | Built-in tool implementations | Adding new tools or fixing existing ones |
| `tools/plugins/` | User-added tools | Adding custom tools (drop files here) |
| `tools/mcp_loader.py` | MCP integration | Debugging MCP server connections |
| `tools/mcp_catalog.py` | Built-in MCP server definitions | Adding new MCP servers to catalog |

### Memory & State

| File | Purpose | When to Edit |
|------|---------|--------------|
| `memory/short_memory.py` | Recent conversation turns | Changing memory window size |
| `memory/long_memory.py` | Persistent knowledge | Changing storage format or recall logic |

### Safety & Configuration

| File | Purpose | When to Edit |
|------|---------|--------------|
| `safety/policy.json` | Per-tool allow/confirm/deny rules | Changing tool safety policies |
| `config.example.json` | Config template | Adding new config options |

### Tests

| File | Purpose | When to Edit |
|------|---------|--------------|
| `tests/test_core.py` | Core functionality | Adding tests for core changes |
| `tests/evals/cases.py` | Eval test cases | Adding new eval scenarios |
| `tests/evals/run.py` | Eval runner | Changing eval harness logic |

---

## 🎯 Common Tasks & Workflows

### Adding a New Tool

1. **Option A: Plugin (Recommended for custom tools)**
   ```python
   # tools/plugins/my_tool.py
   def my_function(arg1: str, arg2: int = 42):
       """Tool description for LLM."""
       return f"Result: {arg1} x {arg2}"
   
   def register(registry):
       registry.register(
           "my_function",
           my_function,
           description="What this tool does",
           category="system",  # or "file", "web", etc.
           args=[
               {"name": "arg1", "required": True, "description": "First arg"},
               {"name": "arg2", "required": False, "description": "Second arg"},
           ],
       )
   ```
   Tool auto-loads on next startup.

2. **Option B: Built-in Tool**
   - Add function to appropriate `tools/*_tools.py` file
   - Call `registry.register()` in that file's `register()` function
   - Add safety policy to `safety/policy.json` if needed

### Adding a New LLM Provider

1. Edit `agent_core/llm.py`
2. Create new class inheriting from `LLMProvider`:
   ```python
   class MyProvider(LLMProvider):
       name = "myprovider"
       
       def chat(self, messages, **kwargs) -> str:
           # Implement chat logic
           pass
       
       @staticmethod
       def is_reachable(**kwargs) -> bool:
           # Implement health check
           pass
   ```
3. Add to `auto_detect_provider()` function
4. Update README.md with usage instructions

### Adding an MCP Server to Catalog

Edit `tools/mcp_catalog.py`:
```python
MCP_CATALOG = {
    "my-server": {
        "command": "npx",
        "args": ["-y", "@myorg/my-mcp-server"],
        "env": {"API_KEY": "<YOUR_API_KEY>"},  # optional
    },
    # ... rest of catalog
}
```

Web UI will show it in the MCP installer.

### Creating a Workflow

Create `workflows/my_workflow.json`:
```json
{
  "name": "cleanup_temp",
  "interval": 60,
  "condition": "file_exists temp.txt",
  "actions": [
    "delete file temp.txt",
    "create file status.txt with content 'cleaned'"
  ]
}
```

Conditions: `always`, `never`, `file_exists <path>`, `file_missing <path>`

### Running Tests

```bash
# All tests
python -m unittest discover tests

# Specific test file
python -m unittest tests.test_core

# Eval harness
python tests/evals/run.py
```

### Code Cleanup

```bash
# Format
black .
isort .

# Lint
ruff check --fix .

# Remove unused imports
autoflake --in-place --remove-all-unused-imports -r .

# Find dead code
vulture . --min-confidence 80
```

---

## 🔐 Safety & Security

### Policy Enforcement

`safety/policy.json` example:
```json
{
  "list_dir": "allow",
  "read_file": "allow",
  "create_file": "confirm",
  "delete_file": "confirm",
  "run_shell": "deny"
}
```

- **allow**: Runs immediately
- **confirm**: Prompts user (y/N) in interactive mode, denies in non-interactive
- **deny**: Always blocked

**Why this matters**: LLM can now propose destructive operations from natural language. Safety gates are the last line of defense.

### Adding a New Policy

Edit `safety/policy.json`:
```json
{
  "my_new_tool": "confirm"
}
```

Missing tools default to `"confirm"`.

---

## 🧪 Testing Philosophy

### Test Coverage

- **46 tests** across unit + eval suites
- **Unit tests**: Core functionality (dispatcher, planner, memory, tools)
- **Eval tests**: End-to-end NL → tool execution with expected output comparison

### Eval-Driven Development

The `tests/evals/` directory uses an eval harness:

1. Define test cases in `cases.py`
2. Run `python tests/evals/run.py` to generate `baseline.json`
3. Future runs compare against baseline
4. Failed evals show diff between expected and actual

**When to use evals**: Testing LLM-dependent behavior (planner accuracy, dispatcher classification)

**When to use unit tests**: Testing deterministic logic (tool execution, memory operations)

---

## 🚀 Development Workflow

### Starting Work

1. **Check existing tests**:
   ```bash
   python -m unittest discover tests
   ```
   All tests should pass before starting work.

2. **Read relevant code**:
   - Check the "Key Files to Know" section above
   - Use the architecture diagram to understand data flow

3. **Make changes**:
   - Follow type hints (use dataclasses where appropriate)
   - Add docstrings for public functions
   - Update tests if changing behavior

4. **Validate**:
   ```bash
   # Run tests
   python -m unittest discover tests
   
   # Format + lint
   black . && isort . && ruff check --fix .
   
   # Smoke test
   python main.py  # Try a few commands
   ```

### Code Style

- **Type hints everywhere**: `def foo(x: str) -> int:`
- **Docstrings**: Explain *what* and *why*, not *how*
- **Error handling**: Specific exceptions, not bare `except:`
- **Logging**: Use `agent_core/logger.py`, not print statements
- **Config**: Load from files, not hardcoded values

---

## 🔧 Debugging

### Common Issues

**LLM not detected**:
```bash
# Check which backends are reachable
python -c "from agent_core.llm import auto_detect_provider; print(auto_detect_provider())"
```

**MCP server won't connect**:
- Check Node.js/npx installed: `npx --version`
- Check server installed: `npx -y @server/name --version`
- Check logs in `logs/` directory

**Tool not working**:
```bash
# List registered tools
python main.py
> tools

# Check safety policy
cat safety/policy.json
```

**Memory issues**:
```bash
python main.py
> memory
# Shows count, can deduplicate
```

### Logging

- **File**: `logs/assistant.log`
- **Level**: INFO by default, DEBUG via env `LOG_LEVEL=DEBUG`
- **Format**: `[timestamp] [level] message`

---

## 📊 Performance Considerations

### Local LLM Constraints

Tyler's setup:
- **Windows 11**
- **GPU**: GTX 1080 Ti (11GB VRAM)
- **Typical models**: 7B-13B parameter models (qwen2.5-coder, llama3.2)

**Design for local-first**:
- Minimize LLM calls where possible (use regex fallback in planner)
- Keep prompts concise (token limits matter on local models)
- Batch operations when possible
- Consider GPU memory limits when suggesting new features

### Web UI Performance

- Flask runs in debug mode by default (single-threaded)
- Don't block request handlers with long operations
- Use background jobs or async for long tasks

---

## 🎯 Project Goals & Constraints

### What This Project IS

- ✅ Local-first AI assistant
- ✅ Privacy-focused (no cloud required)
- ✅ Extensible via MCP and plugins
- ✅ Multi-LLM support with graceful fallback
- ✅ Both CLI and web UI
- ✅ Production-quality tool execution with safety gates

### What This Project IS NOT

- ❌ Cloud-first or SaaS product
- ❌ Multi-user system (single-user, local install)
- ❌ Mobile app (desktop only)
- ❌ RAG system (simple memory, not vector DB)

### Design Principles

1. **Local Control**: User owns their data, LLM, and tools
2. **Graceful Degradation**: Works even if no LLM available (regex mode)
3. **Extensibility**: Easy to add tools, LLMs, and MCP servers
4. **Safety First**: Explicit gates on destructive operations
5. **Offline-Capable**: No internet required for core functionality

---

## 🛠️ Tyler's Preferences & Context

### Tyler's Environment

- **OS**: Windows 11
- **Python**: 3.11 (invoked via `py -3.11`)
- **GPU**: GTX 1080 Ti (11GB VRAM)
- **Local LLM**: LM Studio at `192.168.1.198:1234`, Ollama at `localhost:11434`
- **Editor**: Windsurf (AI-powered code editor)
- **Other Tools**: AutoHotkey v2 for Windows automation

### Tyler's Workflow

- **Project delivery**: zip-based
  - Upload project → Claude modifies → return updated zip
- **File organization**:
  - Work in `/home/claude`
  - Copy finals to `/mnt/user-data/outputs`
  - Always provide downloadable artifacts

### Tyler's Technical Background

- **Strong Python developer**: Builds production-quality modular systems
- **AI/Agent expertise**: Multi-agent architectures, tool calling, local LLMs
- **System design**: Orchestrator/planner/dispatcher patterns
- **Quality focus**: Type hints, docstrings, comprehensive tests
- **Code hygiene**: ruff, black, isort, autoflake, vulture

### What Tyler Values

1. **Direct communication** (see Communication Protocol above)
2. **Production quality**: Type hints, tests, error handling
3. **Local-first**: Prefers stdlib > external deps, offline > cloud
4. **Modularity**: Clear separation of concerns, typed contracts
5. **Eval-driven development**: Test assumptions with harnesses

---

## 🎓 Skills Available

Tyler has the following Claude Code skills available:

### Core Development
- `python-builder` — Production Python engineering
- `output-auditor` — Quality assessment of agent output
- `clean-codebase` — Code hygiene (ruff, black, etc.)

### Project Management
- `blueprint` — Multi-session project planning
- `compare-project-versions` — Version diff + migration plans
- `codebase-onboarding` — Generate onboarding guides

### Architecture
- `adapt-architecture` — Strangler fig migration patterns
- `agentic-engineering` — Eval-first agent development
- `agent-harness-construction` — Action space design

### AI/ML
- `continuous-agent-loop` — Autonomous loop patterns
- `ai-first-engineering` — AI-assisted development model
- `ai-regression-testing` — Test strategies for AI code

Use these skills when appropriate for the task at hand.

---

## 🚦 Current State & Priorities

### Project Status: Production-Ready

- ✅ Core functionality complete
- ✅ 46 tests passing
- ✅ Code hygiene excellent (cleanup 2026-05-11)
- ✅ Multi-LLM support working
- ✅ MCP integration functional
- ✅ Web UI + CLI both stable

### ML Upgrade (2026-05-13) — Completed

- ✅ **Semantic memory**: ChromaDB + nomic-embed-text (Ollama). Falls back to bag-of-words if Ollama is down.
- ✅ **Local voice**: openai-whisper replaces cloud SpeechRecognition. Fully offline, GTX 1080 Ti uses CUDA.
- ✅ **Vision tools**: `analyze_image`, `capture_screen`, `read_text_from_image` via moondream/LLaVA (Ollama).
- ✅ **Fine-tuning pipeline**: `training/export_history.py` + `training/finetune.py` (unsloth + LoRA, fits 7B in 11 GB).
- ✅ **New API endpoints**: `/api/vision/analyze`, `/api/vision/screen`, `/api/training/export`

### ML Setup Checklist (first-time)

```bash
# 1. Install Python deps
pip install chromadb pillow openai-whisper

# 2. Pull Ollama models (Ollama must be running)
ollama pull nomic-embed-text   # semantic memory
ollama pull moondream           # vision (fast, 1.7 GB)

# 3. Optional: install fine-tuning deps (heavy!)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r training/requirements_training.txt
```

### Known TODOs (Non-Critical)

1. **Optional typing modernization**: Replace `typing.Dict` → `dict` (Python 3.9+ style)
2. **Function length**: `server.py:api_llm_set` has 54 statements (could be refactored)
3. **Intentional lazy imports**: Flask routes use lazy imports to avoid circular deps (keep as-is)

### Next Milestones

**Tyler**: Define your next goals here:
- [ ] Goal 1
- [ ] Goal 2
- [ ] Goal 3

---

## 📝 Quick Reference

### Run Commands

```bash
# CLI
python main.py

# Web UI (Windows)
Launch.bat

# Web UI (Mac/Linux)
python server.py

# Tests
python -m unittest discover tests

# Evals
python tests/evals/run.py

# Code cleanup
black . && isort . && ruff check --fix .
```

### Special CLI Commands

```
help         Show help
tools        List registered tools
status       Show LLM backend, MCP servers, history
memory       View/deduplicate long-term memory
reset        Clear conversation history
exit         Exit
```

### Environment Variables

```bash
# Force specific backend
AI_ASSISTANT_PROVIDER=lmstudio|ollama|anthropic

# LM Studio
LMSTUDIO_HOST=http://192.168.1.198:1234
LMSTUDIO_MODEL=qwen2.5-coder-7b

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Logging
LOG_LEVEL=DEBUG
```

---

## 🎯 Success Criteria

You are doing a good job if:

1. ✅ You read this file before starting work
2. ✅ You understand the architecture diagram
3. ✅ You checked tests before and after changes
4. ✅ You followed the communication protocol (direct, honest)
5. ✅ You added type hints and docstrings
6. ✅ You considered local-first constraints (GPU memory, offline capability)
7. ✅ You created downloadable artifacts (files in `/mnt/user-data/outputs`)

---

## 📚 Additional Resources

- **Model Context Protocol**: https://modelcontextprotocol.io
- **LM Studio**: https://lmstudio.ai
- **Ollama**: https://ollama.ai
- **Flask**: https://flask.palletsprojects.com
- **Testing with unittest**: https://docs.python.org/3/library/unittest.html

---

**End of Configuration**

*This file should be updated as the project evolves. When in doubt, check with Tyler first.*
