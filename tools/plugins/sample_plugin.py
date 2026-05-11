"""
Sample plugin - shows the plugin contract.

Every plugin module must define:
    def register(registry):
        registry.register(name, func, description, category, args)
"""

import platform


def sysinfo() -> str:
    return (
        f"OS:       {platform.system()} {platform.release()}\n"
        f"Machine:  {platform.machine()}\n"
        f"Python:   {platform.python_version()}\n"
        f"Node:     {platform.node()}"
    )


def register(registry):
    registry.register(
        "sysinfo",
        sysinfo,
        description="Show basic system info (OS, arch, Python, hostname).",
        category="system",
        args=[],
    )
