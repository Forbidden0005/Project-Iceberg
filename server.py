"""
Project Iceberg web server — bridges the CLI agent to the browser UI.

Serves ui/index.html at / and exposes a JSON REST API at /api/*.

Usage:
    python server.py [--port 5000] [--host 127.0.0.1]
"""

import argparse
import json
import os
import threading
from typing import Optional

import requests as _requests
from flask import Flask, jsonify, request, send_from_directory
from flask.wrappers import Response

from agents.orchestrator_agent import OrchestratorAgent
from tools.registry import TOOL_REGISTRY

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(_BASE_DIR, "ui")
CONFIG_PATH = os.path.join(_BASE_DIR, "config.json")
app = Flask(__name__, static_folder=None)

# ---------------------------------------------------------------------------
# Agent lifecycle — initialised once in a background thread so the server
# can accept requests (and return 503 / retry hints) while MCP servers spin up.
# ---------------------------------------------------------------------------

_agent: Optional[OrchestratorAgent] = None
_agent_lock = threading.Lock()
_agent_ready = threading.Event()
_agent_error: Optional[str] = None


def _boot_agent() -> None:
    global _agent, _agent_error
    try:
        print("[server] booting agent…")
        _agent = OrchestratorAgent(interactive=False)
        print(f"[server] agent ready — LLM: {_agent.llm_info()} | MCP: {_agent.mcp_info()}")
    except Exception as exc:
        _agent_error = str(exc)
        print(f"[server] agent boot failed: {exc}")
    finally:
        _agent_ready.set()


def _require_agent() -> OrchestratorAgent:
    """Block until agent is ready; raise if boot failed."""
    _agent_ready.wait(timeout=90)
    if _agent is None:
        raise RuntimeError(_agent_error or "Agent failed to initialise.")
    return _agent


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


@app.route("/")
def index() -> Response:
    return send_from_directory(UI_DIR, "index.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@app.route("/api/ready")
def api_ready() -> Response:
    """Non-blocking readiness probe for the UI loader."""
    return jsonify({"ready": _agent_ready.is_set(), "error": _agent_error})


@app.route("/api/status")
def api_status() -> Response:
    agent = _require_agent()
    mcp_servers = list(agent.mcp_manager.connected_servers) if agent.mcp_manager else []
    return jsonify(
        {
            "llm": agent.llm_info(),
            "llm_active": agent.llm_active,
            "mcp_servers": mcp_servers,
            "tools_count": len(TOOL_REGISTRY),
            "memory_count": len(agent.long_memory.data),
            "history_depth": agent.history_depth(),
        }
    )


@app.route("/api/tools")
def api_tools() -> Response:
    tools = [
        {
            "name": name,
            "description": entry.get("description", ""),
            "category": entry.get("category", "custom"),
        }
        for name, entry in sorted(TOOL_REGISTRY.items())
    ]
    return jsonify(tools)


@app.route("/api/servers")
def api_servers() -> Response:
    agent = _require_agent()
    if not agent.mcp_manager:
        return jsonify([])
    result = []
    for server_name in agent.mcp_manager.connected_servers:
        try:
            raw_tools = agent.mcp_manager.list_tools(server_name)
            tool_names = [t.name for t in raw_tools]
        except Exception:
            tool_names = []
        result.append(
            {
                "name": server_name,
                "connected": True,
                "tools": tool_names,
            }
        )
    return jsonify(result)


@app.route("/api/chat", methods=["POST"])
def api_chat() -> Response:
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400

    with _agent_lock:
        agent = _require_agent()
        responses = agent.run(message)

    return jsonify({"responses": responses})


@app.route("/api/reset", methods=["POST"])
def api_reset() -> Response:
    with _agent_lock:
        agent = _require_agent()
        agent.reset_history()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# LLM management
# ---------------------------------------------------------------------------


def _read_config() -> dict:
    """Read config.json, returning {} on missing / bad JSON."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[server] config.json parse error: {exc}")
        return {}


def _write_config(updates: dict) -> None:
    """Merge updates into config.json (creates it if missing)."""
    cfg = _read_config()
    cfg.update(updates)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


@app.route("/api/llm/models")
def api_llm_models() -> Response:
    """Return Ollama models installed locally."""
    models = []
    try:
        r = _requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.ok:
            for m in r.json().get("models", []):
                size_b = m.get("size", 0)
                size_str = f"{size_b / 1e9:.1f} GB" if size_b else "?"
                models.append(
                    {
                        "name": m["name"],
                        "size": size_str,
                        "provider": "ollama",
                    }
                )
    except Exception:
        pass
    return jsonify({"models": models})


@app.route("/api/llm/set", methods=["POST"])
def api_llm_set() -> Response:
    """Hot-swap the active LLM and persist the choice to config.json."""
    from agent_core.dispatcher import Dispatcher
    from agent_core.llm import AnthropicProvider, LMStudioProvider, OllamaProvider
    from planner.planner import Planner
    from tools.registry import describe_for_llm

    data = request.get_json(force=True, silent=True) or {}
    provider = (data.get("provider") or "ollama").lower()
    model = (data.get("model") or "").strip()
    host = (data.get("host") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    # Build new provider object
    try:
        if provider == "ollama":
            h = host or "http://localhost:11434"
            new_llm = OllamaProvider(h, model)
        elif provider == "lmstudio":
            h = host or "http://localhost:1234"
            new_llm = LMStudioProvider(h, model)
        elif provider == "anthropic":
            if not api_key:
                api_key = _read_config().get("anthropic_api_key") or ""
            new_llm = AnthropicProvider(api_key, model)
        else:
            return jsonify({"error": f"Unknown provider: {provider}"}), 400
    except Exception as exc:
        return jsonify({"error": str(exc), "needs_restart": True}), 500

    # Hot-swap — replace llm, planner, and dispatcher in-place
    try:
        with _agent_lock:
            agent = _require_agent()
            agent.llm = new_llm
            agent.llm_active = True
            tools_desc = describe_for_llm()
            agent.planner = Planner(llm=new_llm, tools_description=tools_desc)
            agent.dispatcher = Dispatcher(new_llm, tools_description=tools_desc)
        swapped = True
    except Exception as exc:
        print(f"[server] hot-swap failed: {exc}")
        swapped = False

    # Persist to config.json regardless of hot-swap result
    updates: dict = {"llm_provider": provider}
    if provider == "ollama":
        updates["ollama_model"] = model
        if host:
            updates["ollama_host"] = host
    elif provider == "lmstudio":
        updates["lmstudio_model"] = model
        if host:
            updates["lmstudio_host"] = host
    elif provider == "anthropic":
        updates["anthropic_model"] = model
        if api_key:
            updates["anthropic_api_key"] = api_key
    try:
        _write_config(updates)
    except Exception as exc:
        print(f"[server] config write error: {exc}")

    if swapped:
        agent = _require_agent()
        return jsonify({"ok": True, "llm": agent.llm_info(), "needs_restart": False})
    return jsonify(
        {"ok": False, "needs_restart": True, "error": "Hot-swap failed — restart Project Iceberg to apply."}
    )


# ---------------------------------------------------------------------------
# MCP management
# ---------------------------------------------------------------------------


@app.route("/api/mcp/catalog")
def api_mcp_catalog() -> Response:
    """Return the catalog of available MCP servers."""
    from tools.mcp_catalog import get_catalog

    return jsonify({"servers": get_catalog()})


@app.route("/api/mcp/check-npx")
def api_mcp_check_npx() -> Response:
    """
    Check if npx is installed and accessible.

    Returns:
      {
        "installed": true/false,
        "version": "11.12.1" or null
      }
    """
    import subprocess

    try:
        # On Windows, shell=True is needed to resolve .cmd files
        result = subprocess.run(
            ["npx", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=True,  # Required on Windows for .cmd files
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            return jsonify({"installed": True, "version": version})
        else:
            return jsonify({"installed": False, "version": None})

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return jsonify({"installed": False, "version": None})


@app.route("/api/mcp/add", methods=["POST"])
def api_mcp_add() -> Response:
    """
    Add an MCP server to config.json.

    Request body:
      {
        "server_name": "github",
        "api_key": "optional-key-value"  // For servers that need API keys
      }
    """
    from tools.mcp_catalog import get_server_config

    data = request.get_json(force=True, silent=True) or {}
    server_name = (data.get("server_name") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not server_name:
        return jsonify({"error": "server_name required"}), 400

    # Get server config from catalog
    server_entry = get_server_config(server_name)
    if not server_entry:
        return jsonify({"error": f"Unknown server: {server_name}"}), 404

    # Build the MCP server config
    server_config = {
        "command": server_entry["command"],
        "args": server_entry["args"],
        "env": server_entry["env"].copy(),
    }

    # If API key provided and server needs it, replace the placeholder
    if api_key and server_entry.get("requires_api_key"):
        key_field = server_entry.get("api_key_field")
        if key_field:
            server_config["env"][key_field] = api_key

    # Read current config
    cfg = _read_config()

    # Initialize mcp_servers if it doesn't exist
    if "mcp_servers" not in cfg:
        cfg["mcp_servers"] = {}

    # Check if server already exists
    if server_name in cfg["mcp_servers"]:
        return jsonify({"error": f"Server '{server_name}' already exists in config"}), 409

    # Add the server
    cfg["mcp_servers"][server_name] = server_config

    # Write back to config.json
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return jsonify({"ok": True, "server_name": server_name})
    except Exception as exc:
        return jsonify({"error": f"Failed to write config: {exc}"}), 500


@app.route("/api/restart", methods=["POST"])
def api_restart() -> Response:
    """
    Restart Project Iceberg server.

    This endpoint triggers a clean shutdown and restart of the Flask app.
    """
    import os
    import sys

    def restart_server():
        """Restart the server by re-executing the current script."""
        import time

        time.sleep(0.5)  # Give time for response to send
        python = sys.executable
        os.execl(python, python, *sys.argv)

    # Trigger restart in background thread
    threading.Thread(target=restart_server, daemon=True).start()

    return jsonify({"ok": True, "message": "Restarting Project Iceberg..."})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Iceberg web server")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    # Boot the agent in the background so Flask can start accepting requests.
    threading.Thread(target=_boot_agent, daemon=True).start()

    print(f"\n  Project Iceberg → http://{args.host}:{args.port}")
    print("  Ctrl+C to stop.\n")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
