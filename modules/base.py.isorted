"""Module base classes and protocol.

A Module is a pluggable agent configuration with its own:
- System prompt
- Tool set
- Memory namespace
- Optional settings

Modules are discovered from the modules/ directory and loaded on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tools.registry import ToolRegistry


@dataclass
class ModuleManifest:
    """Module metadata.

    Attributes:
        id: Unique identifier (snake_case, matches folder name)
        name: Human-readable display name
        description: One-line description for help text
        version: Semantic version string
        category: Module category (file|code|network|system|custom)
        default_enabled: Whether this module loads by default
    """

    id: str
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "custom"
    default_enabled: bool = False


@dataclass
class ModuleTools:
    """Tool definitions for a module.

    Attributes:
        tools: Map of {tool_name: {"func": callable, "description": str, "args": list}}
        dependencies: List of tool names from the global registry this module needs
    """

    tools: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)


class Module(Protocol):
    """Protocol for all modules.

    A module must provide:
    - manifest: metadata about the module
    - system_prompt: the agent system instructions for this module
    - get_tools: method that returns the module's tool set

    Optional hooks:
    - on_load: called when module becomes active
    - on_unload: called when switching away from this module
    """

    manifest: ModuleManifest
    system_prompt: str

    def get_tools(self, registry: ToolRegistry) -> ModuleTools:
        """Return this module's tools.

        Args:
            registry: The global tool registry (for dependencies)

        Returns:
            ModuleTools with module-specific tools and dependencies
        """
        ...

    def on_load(self) -> None:
        """Called when this module becomes active."""
        ...

    def on_unload(self) -> None:
        """Called when switching away from this module."""
        ...


class BaseModule:
    """Base implementation with sensible defaults.

    Subclass this instead of implementing Module from scratch.
    """

    def __init__(self, manifest: ModuleManifest, system_prompt: str):
        self.manifest = manifest
        self.system_prompt = system_prompt

    def get_tools(self, registry: ToolRegistry) -> ModuleTools:
        """Default: no module-specific tools, just declare dependencies."""
        return ModuleTools(tools={}, dependencies=[])

    def on_load(self) -> None:
        """Default: no-op."""

    def on_unload(self) -> None:
        """Default: no-op."""
