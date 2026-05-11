"""Core module - Project Iceberg's default general-purpose assistant.

This module provides access to all base tools (file ops, web search, scanning).
It's the default when no other module is selected.
"""

from modules.base import BaseModule, ModuleManifest, ModuleTools

SYSTEM_PROMPT = """\
You are Project Iceberg, a local-first AI assistant running on the user's machine.

You can:
- Manage files and directories
- Search the web for information
- Scan directories for analysis
- Execute safe, user-approved commands

When the user asks you to do something:
1. Use the available tools to accomplish it
2. Be concise and direct
3. Confirm before destructive operations

Available tools will be listed separately. Use them proactively when helpful."""


class CoreModule(BaseModule):
    """Core general-purpose module."""

    def __init__(self):
        manifest = ModuleManifest(
            id="core",
            name="Core Assistant",
            description="General-purpose file and web assistant",
            version="1.0.0",
            category="system",
            default_enabled=True,
        )
        super().__init__(manifest, SYSTEM_PROMPT)

    def get_tools(self, registry):
        """Core module uses all base tools from the registry."""
        return ModuleTools(
            tools={},
            dependencies=[
                "list_dir",
                "create_file",
                "delete_file",
                "move_file",
                "read_file",
                "append_file",
                "scan",
                "web_search",
            ],
        )


# Export the module instance
MODULE = CoreModule()
