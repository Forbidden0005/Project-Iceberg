"""
MCP (Model Context Protocol) server loader.

Connects to configured MCP servers at startup, discovers their tools, and
registers them into Project Iceberg's tool registry. The planner and dispatcher then
see MCP tools the same way they see built-in tools — no special-casing needed
anywhere downstream.

Config block in config.json:
  {
    "mcp_servers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "env": {}
      },
      "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "your-token-here"}
      }
    }
  }

Tool names registered as: "{server_name}__{tool_name}"
  e.g.  filesystem__read_file,  github__search_repositories

The namespace prefix prevents collisions with built-in tools and makes it
clear to the LLM which server owns each tool.

Install MCP support:
  pip install mcp
"""

import asyncio
import json
import logging
import os
import threading
from contextlib import AsyncExitStack
from typing import Any

from agent_core.constants import (MCP_CALL_TIMEOUT_SECONDS,
                                  MCP_CONNECT_TIMEOUT_SECONDS)
from tools.registry import register

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import guard — CLI mode works fine without the mcp package.
# ---------------------------------------------------------------------------

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


# ---------------------------------------------------------------------------
# MCPServerManager
# ---------------------------------------------------------------------------


class MCPServerManager:
    """
    Manages persistent async connections to one or more MCP servers.

    Runs a dedicated asyncio event loop in a daemon thread so the
    synchronous Project Iceberg runtime can issue tool calls without spawning a
    new subprocess per call or blocking the main thread.

    Usage:
        manager = MCPServerManager()
        tool_names = manager.connect("github", {"command": "npx", "args": [...]})
        result     = manager.call("github", "search_repositories", {"query": "..."})
        manager.shutdown()
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="mcp-event-loop",
        )
        self._thread.start()

        self._sessions: dict[str, ClientSession] = {}
        self._stacks: dict[str, AsyncExitStack] = {}

    # ------------------------------------------------------------------
    # Public synchronous API
    # ------------------------------------------------------------------

    def connect(self, server_name: str, server_config: dict) -> list[str]:
        """
        Connect to an MCP server and return the list of tool names it exposes.
        Blocks until the handshake is complete or MCP_CONNECT_TIMEOUT_SECONDS elapses.
        """
        future = asyncio.run_coroutine_threadsafe(
            self._connect_async(server_name, server_config),
            self._loop,
        )
        return future.result(timeout=MCP_CONNECT_TIMEOUT_SECONDS)

    def list_tools(self, server_name: str) -> list:
        """Return the raw MCP Tool objects for an already-connected server."""
        future = asyncio.run_coroutine_threadsafe(
            self._list_tools_async(server_name),
            self._loop,
        )
        return future.result(timeout=MCP_CONNECT_TIMEOUT_SECONDS)

    def call(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """
        Call a tool on the named server. Returns the result as a plain string.
        Blocks until the server replies or MCP_CALL_TIMEOUT_SECONDS elapses.
        """
        future = asyncio.run_coroutine_threadsafe(
            self._call_async(server_name, tool_name, arguments),
            self._loop,
        )
        return future.result(timeout=MCP_CALL_TIMEOUT_SECONDS)

    def shutdown(self) -> None:
        """Close all server connections and stop the background loop."""
        for name, stack in list(self._stacks.items()):
            try:
                asyncio.run_coroutine_threadsafe(stack.aclose(), self._loop).result(timeout=5)
            except Exception as exc:
                logger.warning("[mcp] error closing '%s': %s", name, exc)
        self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Private async implementations (run on the background loop)
    # ------------------------------------------------------------------

    async def _connect_async(self, server_name: str, server_config: dict) -> list[str]:
        command = server_config.get("command")
        if not command:
            raise ValueError(f"MCP server '{server_name}' missing 'command'")

        args = server_config.get("args") or []
        env_overrides = server_config.get("env") or {}

        # Merge server-specific env vars on top of the current process
        # environment so the subprocess inherits PATH and other essentials.
        merged_env = {**os.environ, **env_overrides} if env_overrides else None

        params = StdioServerParameters(command=command, args=args, env=merged_env)

        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        self._sessions[server_name] = session
        self._stacks[server_name] = stack

        result = await session.list_tools()
        return [t.name for t in result.tools]

    async def _list_tools_async(self, server_name: str) -> list:
        session = self._sessions[server_name]
        result = await session.list_tools()
        return result.tools

    async def _call_async(self, server_name: str, tool_name: str, arguments: dict) -> str:
        session = self._sessions[server_name]
        result = await session.call_tool(tool_name, arguments)

        # result.content is a list of typed blocks (TextContent, ImageContent, etc.)
        parts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))

        return "\n".join(parts) if parts else "(no output)"


# ---------------------------------------------------------------------------
# Schema conversion helper
# ---------------------------------------------------------------------------


def _schema_to_args(input_schema: dict) -> list[dict[str, Any]]:
    """
    Convert an MCP JSON Schema inputSchema to Project Iceberg's args format.

    MCP:           {"type": "object", "properties": {...}, "required": [...]}
    Project Iceberg: [{"name": str, "required": bool, "description": str}]
    """
    if not isinstance(input_schema, dict):
        return []

    properties = input_schema.get("properties") or {}
    required_set = set(input_schema.get("required") or [])

    return [
        {
            "name": prop_name,
            "required": prop_name in required_set,
            "description": prop_schema.get("description", ""),
        }
        for prop_name, prop_schema in properties.items()
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_mcp_servers(mcp_config: dict) -> "MCPServerManager | None":
    """
    Connect to every server in mcp_config and register their tools.

    Called once at startup, before the Planner and Dispatcher are built,
    so that MCP tools appear in describe_for_llm() and the LLM knows about them.

    Args:
        mcp_config: mapping of server_name -> server_config dict
                    (the "mcp_servers" value from config.json)

    Returns:
        MCPServerManager if at least one server connected, else None.
        Caller must keep the return value alive for the duration of the process
        so the background loop and connections stay open.
    """
    if not mcp_config:
        return None

    if not _MCP_AVAILABLE:
        logger.warning(
            "[mcp] servers are configured but the 'mcp' package is not installed. "
            "Run: pip install mcp"
        )
        return None

    manager = MCPServerManager()
    total_registered = 0

    for server_name, server_config in mcp_config.items():
        try:
            logger.info("[mcp] connecting to '%s'...", server_name)
            tool_names = manager.connect(server_name, server_config)

            # Re-fetch full Tool objects to get schema + description.
            mcp_tools = manager.list_tools(server_name)
            tool_map = {t.name: t for t in mcp_tools}

            for name in tool_names:
                mcp_tool = tool_map.get(name)
                description = getattr(mcp_tool, "description", "") or ""
                input_schema = getattr(mcp_tool, "inputSchema", {}) or {}
                args = _schema_to_args(input_schema)

                # Namespace the registry key to avoid collisions with builtins.
                registry_name = f"{server_name}__{name}"

                # Build a closure that captures the correct server/tool pair.
                def _make_caller(srv: str, tname: str):
                    def _call(**kwargs: Any) -> str:
                        return manager.call(srv, tname, kwargs)

                    return _call

                register(
                    name=registry_name,
                    func=_make_caller(server_name, name),
                    description=f"[{server_name}] {description}",
                    category="mcp",
                    args=args,
                )
                total_registered += 1

            logger.info("[mcp] '%s': %d tool(s) registered", server_name, len(tool_names))

        except Exception as exc:
            # A single unreachable server must not block startup for the others.
            logger.error("[mcp] failed to connect to '%s': %s", server_name, exc)

    if total_registered > 0:
        logger.info("[mcp] %d total MCP tool(s) available", total_registered)
        return manager

    # Nothing connected — clean up.
    manager.shutdown()
    return None


# ---------------------------------------------------------------------------
# Config reader
# ---------------------------------------------------------------------------


def read_mcp_config(config_path: str = "config.json") -> dict:
    """Extract the 'mcp_servers' block from config.json, or return {}."""
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mcp_servers") or {}
    except Exception:
        return {}
